"""
Audio processing module.

Handles:
- Downloading audio via yt-dlp with multi-result validation
- Getting audio duration via ffprobe
- Slicing audio segments via ffmpeg
- Version matching (duration comparison)
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .config import (
    AUDIO_BITRATE,
    AUDIO_CODEC,
    AUDIO_DIR,
    DURATION_TOLERANCE,
    MATCH_THRESHOLD,
    SKIPPED_SONGS_LOG,
    SNIPPET_FORMAT,
    SNIPPETS_DIR,
    YTDLP_FORMAT,
    YTDLP_SEARCH_PREFIX,
    ensure_directories,
)


@dataclass
class DownloadResult:
    """Result of audio download attempt."""

    success: bool
    file_path: Optional[Path]
    duration: Optional[float]
    yt_url: Optional[str]
    yt_title: Optional[str] = None  # Video title for logging
    error: Optional[str] = None


@dataclass
class SearchCandidate:
    """A YouTube search result candidate."""

    video_id: str
    title: str
    uploader: str
    duration: float
    url: str
    score: float = 0.0


@dataclass
class SliceResult:
    """Result of audio slice operation."""

    success: bool
    file_path: Optional[Path]
    duration: Optional[float]
    error: Optional[str] = None


def get_audio_duration(file_path: Path) -> Optional[float]:
    """
    Get duration of audio file using ffprobe.

    Args:
        file_path: Path to audio file

    Returns:
        Duration in seconds, or None if failed
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "json",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ValueError):
        return None


def check_version_match(
    lrc_duration: float,
    audio_duration: float,
    tolerance: float = DURATION_TOLERANCE,
) -> tuple[bool, float]:
    """
    Check if audio duration matches LRC duration within tolerance.

    Args:
        lrc_duration: Expected duration from LRCLib
        audio_duration: Actual duration of downloaded audio
        tolerance: Maximum allowed difference in seconds

    Returns:
        Tuple of (is_match, drift_seconds)
    """
    drift = abs(lrc_duration - audio_duration)
    return drift <= tolerance, drift


def fuzzy_contains(haystack: str, needle: str, threshold: float = 0.7) -> bool:
    """
    Check if needle is approximately contained in haystack.

    Uses word-level fuzzy matching to handle:
    - Typos and misspellings
    - Special characters in titles
    - Partial matches

    Args:
        haystack: String to search in
        needle: String to find
        threshold: Minimum similarity ratio (0-1)

    Returns:
        True if needle is approximately contained in haystack
    """
    haystack_lower = haystack.lower()
    needle_lower = needle.lower()

    # Exact substring match
    if needle_lower in haystack_lower:
        return True

    # Word-level fuzzy match
    needle_words = needle_lower.split()
    haystack_words = haystack_lower.split()

    if not needle_words:
        return False

    matched = 0
    for needle_word in needle_words:
        # Check if this word fuzzy-matches any haystack word
        for hay_word in haystack_words:
            ratio = SequenceMatcher(None, needle_word, hay_word).ratio()
            if ratio > threshold:
                matched += 1
                break

    # Require most words to match
    return matched / len(needle_words) >= 0.7


def score_candidate(
    candidate: SearchCandidate,
    expected_title: str,
    expected_artist: str,
    expected_duration: float,
) -> float:
    """
    Score how well a YouTube candidate matches the expected track.

    Scoring breakdown:
    - Title contains song name: +50 points
    - Title/uploader contains artist: +40/+30 points
    - NO artist match: -30 points (prevents covers from winning)
    - Duration within tolerance: +20 to -20 points
    - Official channel: +10 points

    Args:
        candidate: YouTube search result
        expected_title: Expected song title from LRCLib
        expected_artist: Expected artist name from LRCLib
        expected_duration: Expected duration in seconds

    Returns:
        Score (higher is better, 50+ is acceptable)
    """
    score = 0.0
    title_matched = False
    artist_matched = False

    # Title match
    if fuzzy_contains(candidate.title, expected_title):
        score += 50
        title_matched = True

    # Artist match (in video title or uploader name)
    if fuzzy_contains(candidate.title, expected_artist):
        score += 40
        artist_matched = True
    elif fuzzy_contains(candidate.uploader, expected_artist):
        score += 30
        artist_matched = True

    # CRITICAL: Penalize if title matches but artist doesn't
    # This prevents cover versions by other artists from winning
    if title_matched and not artist_matched:
        score -= 30

    # Duration match
    drift = abs(candidate.duration - expected_duration)
    if drift <= 1.0:
        score += 20
    elif drift <= 2.0:
        score += 10
    elif drift <= 5.0:
        score += 5
    else:
        score -= 20  # Penalty for wrong duration

    # Official channel bonus
    official_keywords = ["official", "vevo", "records", "music", "topic"]
    if any(kw in candidate.uploader.lower() for kw in official_keywords):
        score += 10

    return score


def download_audio(
    artist: str,
    title: str,
    expected_duration: float,
    output_dir: Optional[Path] = None,
) -> DownloadResult:
    """
    Download audio for a track using yt-dlp with multi-result validation.

    Searches for multiple candidates, scores each against expected track
    metadata, and downloads the best match above threshold.

    Args:
        artist: Artist name
        title: Song title
        expected_duration: Expected duration in seconds from LRCLib
        output_dir: Directory to save audio (defaults to AUDIO_DIR)

    Returns:
        DownloadResult with file path and metadata
    """
    ensure_directories()
    output_dir = output_dir or AUDIO_DIR

    # Generate unique filename
    safe_name = f"{artist} - {title}".replace("/", "_").replace("\\", "_")[:100]
    output_template = str(output_dir / f"{safe_name}.%(ext)s")

    # Try multiple search strategies in order of specificity
    # "official audio" can bias results toward popular songs
    search_queries = [
        f"{YTDLP_SEARCH_PREFIX}{artist} {title}",  # Simple, no bias
        f"{YTDLP_SEARCH_PREFIX}{artist} - {title}",  # With separator
        f"{YTDLP_SEARCH_PREFIX}{title} {artist}",  # Reversed order
    ]

    all_candidates: list[SearchCandidate] = []

    try:
        for search_query in search_queries:
            print(f"Searching: {search_query}")

            # Get metadata for multiple candidates
            info_result = subprocess.run(
                [
                    "yt-dlp",
                    "--dump-json",
                    "--no-download",
                    "-f", YTDLP_FORMAT,
                    search_query,
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )

            if info_result.returncode != 0:
                continue  # Try next search strategy

            # Parse candidates from JSON lines
            for line in info_result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    info = json.loads(line)
                    video_duration = info.get("duration", 0)
                    if video_duration == 0:
                        video_duration = expected_duration  # Assume match for scoring

                    candidate = SearchCandidate(
                        video_id=info.get("id", ""),
                        title=info.get("title", ""),
                        uploader=info.get("uploader", info.get("channel", "")),
                        duration=video_duration,
                        url=info.get("webpage_url", info.get("url", "")),
                    )

                    # Avoid duplicates by video_id
                    if not any(c.video_id == candidate.video_id for c in all_candidates):
                        all_candidates.append(candidate)
                except json.JSONDecodeError:
                    continue

            # Score all candidates collected so far
            for c in all_candidates:
                if c.score == 0:  # Not yet scored
                    c.score = score_candidate(c, title, artist, expected_duration)

            # If we found a good match, stop searching
            all_candidates.sort(key=lambda c: c.score, reverse=True)
            if all_candidates and all_candidates[0].score >= MATCH_THRESHOLD:
                break

        candidates = all_candidates

        if not candidates:
            return DownloadResult(
                success=False,
                file_path=None,
                duration=None,
                yt_url=None,
                error="No search results found",
            )

        # Step 3: Score candidates and find best match
        for c in candidates:
            c.score = score_candidate(c, title, artist, expected_duration)

        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0]

        print(f"  Best match: \"{best.title}\" (score: {best.score:.0f})")

        # Step 4: Check if best match passes threshold
        if best.score < MATCH_THRESHOLD:
            alternatives = ", ".join(
                f"\"{c.title}\" ({c.score:.0f})" for c in candidates[:3]
            )
            return DownloadResult(
                success=False,
                file_path=None,
                duration=None,
                yt_url=best.url,
                yt_title=best.title,
                error=f"No good match (best score: {best.score:.0f} < {MATCH_THRESHOLD}). Candidates: {alternatives}",
            )

        # Step 5: Download the best match using its specific URL
        print(f"  Downloading: {best.url}")
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", YTDLP_FORMAT,
                "-x",  # Extract audio
                "--audio-format", "mp3",
                "--audio-quality", "0",  # Best quality
                "-o", output_template,
                "--no-playlist",
                "--no-warnings",
                best.url,  # Use specific URL, not search query
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes max
        )

        if result.returncode != 0:
            return DownloadResult(
                success=False,
                file_path=None,
                duration=None,
                yt_url=best.url,
                yt_title=best.title,
                error=f"yt-dlp download failed: {result.stderr[:200]}",
            )

        # Step 6: Find and verify the downloaded file
        downloaded_files = list(output_dir.glob(f"{safe_name}.*"))
        if not downloaded_files:
            return DownloadResult(
                success=False,
                file_path=None,
                duration=None,
                yt_url=best.url,
                yt_title=best.title,
                error="Download completed but file not found",
            )

        file_path = downloaded_files[0]
        duration = get_audio_duration(file_path)

        return DownloadResult(
            success=True,
            file_path=file_path,
            duration=duration,
            yt_url=best.url,
            yt_title=best.title,
        )

    except subprocess.TimeoutExpired:
        return DownloadResult(
            success=False,
            file_path=None,
            duration=None,
            yt_url=None,
            error="Download timed out",
        )
    except Exception as e:
        return DownloadResult(
            success=False,
            file_path=None,
            duration=None,
            yt_url=None,
            error=str(e),
        )


def slice_audio(
    input_file: Path,
    start_time: float,
    end_time: float,
    output_name: str,
    output_dir: Optional[Path] = None,
) -> SliceResult:
    """
    Extract a segment from an audio file.

    Args:
        input_file: Path to source audio file
        start_time: Start timestamp in seconds
        end_time: End timestamp in seconds
        output_name: Name for output file (without extension)
        output_dir: Directory to save snippet (defaults to SNIPPETS_DIR)

    Returns:
        SliceResult with output file path
    """
    ensure_directories()
    output_dir = output_dir or SNIPPETS_DIR

    output_file = output_dir / f"{output_name}.{SNIPPET_FORMAT}"

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",  # Overwrite output
                "-i", str(input_file),
                "-ss", str(start_time),
                "-to", str(end_time),
                "-c:a", AUDIO_CODEC,
                "-b:a", AUDIO_BITRATE,
                "-vn",  # No video
                str(output_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            return SliceResult(
                success=False,
                file_path=None,
                duration=None,
                error=f"ffmpeg failed: {result.stderr[:200]}",
            )

        # Verify output and get duration
        if not output_file.exists():
            return SliceResult(
                success=False,
                file_path=None,
                duration=None,
                error="Output file not created",
            )

        duration = get_audio_duration(output_file)

        return SliceResult(
            success=True,
            file_path=output_file,
            duration=duration,
        )

    except subprocess.TimeoutExpired:
        return SliceResult(
            success=False,
            file_path=None,
            duration=None,
            error="FFmpeg timed out",
        )
    except Exception as e:
        return SliceResult(
            success=False,
            file_path=None,
            duration=None,
            error=str(e),
        )


def log_skipped_song(
    track_id: int,
    title: str,
    artist: str,
    lrc_duration: float,
    audio_duration: Optional[float],
    drift: Optional[float],
    reason: str,
    yt_url: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Log a skipped song to the skipped songs JSONL file.

    Args:
        track_id: LRCLib track ID
        title: Song title
        artist: Artist name
        lrc_duration: Duration from LRCLib
        audio_duration: Duration of downloaded audio (if available)
        drift: Difference between durations (if applicable)
        reason: Why the song was skipped
        yt_url: YouTube URL (if available)
        error: Error message (if applicable)
    """
    ensure_directories()

    entry = {
        "track_id": track_id,
        "title": title,
        "artist": artist,
        "lrc_duration": lrc_duration,
        "audio_duration": audio_duration,
        "drift": drift,
        "reason": reason,
        "yt_url": yt_url,
        "error": error,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    with open(SKIPPED_SONGS_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def cleanup_audio_file(file_path: Path) -> None:
    """
    Delete a temporary audio file.

    Args:
        file_path: Path to file to delete
    """
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass  # Best effort cleanup
