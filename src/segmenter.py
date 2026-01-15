"""
LLM-based lyrics segmentation module.

Uses Groq or Together.ai to analyze lyrics and identify emotionally
meaningful segments suitable for conversational use.

All API calls are async for efficient network IO.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Optional

from groq import RateLimitError as GroqRateLimitError

from .config import (
    LLM_MODEL_GROQ,
    LLM_MODEL_TOGETHER,
    LLM_PROVIDERS,
    MAX_RETRIES,
    RETRY_DELAY,
    get_api_key,
)


@dataclass
class Segment:
    """A meaningful segment of lyrics identified by the LLM."""

    start_line: int
    end_line: int
    lyrics: str
    ai_description: str
    primary_emotion: str
    secondary_emotion: Optional[str]
    energy: str  # low, medium, high, very-high
    tone: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "lyrics": self.lyrics,
            "ai_description": self.ai_description,
            "primary_emotion": self.primary_emotion,
            "secondary_emotion": self.secondary_emotion,
            "energy": self.energy,
            "tone": self.tone,
        }


@dataclass
class SegmentationResult:
    """Result of lyrics segmentation."""

    success: bool
    segments: list[Segment]
    genre: Optional[str]  # Genre detected by LLM
    provider: Optional[str]  # Which LLM provider was used
    error: Optional[str] = None
    retry_after_seconds: Optional[float] = None  # Set when rate limited


@dataclass
class BatchedSongResult:
    """Result for a single song in a batch segmentation."""

    track_id: int  # For cache lookup
    song_index: int  # Position in batch (1-indexed)
    title: str
    artist: str
    genre: Optional[str]
    segments: list[Segment]
    error: Optional[str] = None


@dataclass
class BatchSegmentationResult:
    """Result of batched lyrics segmentation."""

    success: bool
    song_results: list[BatchedSongResult]
    provider: Optional[str]
    error: Optional[str] = None
    retry_after_seconds: Optional[float] = None  # Set when rate limited


# Valid genre values for normalization
VALID_GENRES = {
    "afrobeats", "reggaeton", "dancehall", "hip-hop", "r&b", "pop", "rock",
    "country", "latin", "electronic", "folk", "jazz", "classical", "metal",
    "indie", "soul", "funk", "gospel", "blues", "reggae", "punk", "disco",
    "house", "techno", "trap", "drill", "afropop", "amapiano", "kizomba",
    "soca", "calypso", "bachata", "salsa", "cumbia", "merengue", "other"
}

# Prompt template for LLM segmentation
SEGMENTATION_PROMPT = """You are analyzing song lyrics to identify emotionally meaningful segments that could be sent in a conversation as a response.

First, determine the song's genre based on the artist name and lyrical style.

For each segment you identify:
1. It should be 10-20 seconds when sung (roughly 2-6 lines)
2. It should convey a clear emotional message
3. It should work as a standalone snippet in a chat
4. The lyrics should make sense without the rest of the song

Song: {title} by {artist}

Lyrics (with line numbers):
{numbered_lyrics}

Identify 2-5 of the most emotionally resonant segments. Output ONLY valid JSON in this exact format:

{{
  "genre": "<primary genre: afrobeats, reggaeton, dancehall, hip-hop, r&b, pop, rock, country, latin, electronic, folk, jazz, classical, metal, indie, soul, funk, gospel, blues, reggae, punk, disco, house, techno, trap, drill, afropop, amapiano, kizomba, soca, calypso, bachata, salsa, cumbia, merengue, or other>",
  "segments": [
    {{
      "start_line": <line number where segment starts>,
      "end_line": <line number where segment ends>,
      "lyrics": "<exact lyrics from those lines>",
      "ai_description": "<see format below>",
      "primary_emotion": "<main emotion: e.g., triumphant, sad, determined, grateful, playful, nostalgic, etc.>",
      "secondary_emotion": "<supporting emotion or null>",
      "energy": "<low|medium|high|very-high>",
      "tone": "<how the emotion is expressed: e.g., celebratory, bitter, encouraging, wistful, etc.>"
    }}
  ]
}}

Important:
- The genre field is REQUIRED at the top level
- Line numbers must match the numbered lyrics above
- Include the exact lyrics text in the "lyrics" field
- ai_description rules:
  * DO NOT start with "This segment", "This part", "This song", "The lyrics", or any similar phrase
  * Write 2 sentences describing the emotional content and meaning. Write it like you're describing the vibe to a friend.
  * Start directly with the emotion or theme (e.g., "Longing for...", "Triumphant...", "Raw vulnerability...")
  * WRONG: "This segment conveys a sense of longing and desire"
  * WRONG: "This part of the song highlights unity"
  * RIGHT: "Longing and desire for connection, aching to be understood"
  * RIGHT: "Unity and shared purpose, everyone coming together for adventure"
- Output ONLY the JSON, no other text"""


# Prompt template for batched LLM segmentation (multiple songs)
BATCHED_SEGMENTATION_PROMPT = """You are analyzing MULTIPLE songs' lyrics to identify emotionally meaningful segments.

For EACH song:
1. Determine the genre based on artist name and lyrical style
2. Identify 2-5 emotionally resonant segments (10-20 seconds when sung, ~2-6 lines)
3. Each segment should work as a standalone snippet in chat

{songs_section}

Output ONLY valid JSON with this exact structure:

{{
  "songs": [
    {{
      "song_index": <number matching SONG N>,
      "title": "<song title>",
      "artist": "<artist name>",
      "genre": "<primary genre: afrobeats, reggaeton, dancehall, hip-hop, r&b, pop, rock, country, latin, electronic, folk, jazz, classical, metal, indie, soul, funk, gospel, blues, reggae, punk, disco, house, techno, trap, drill, afropop, amapiano, kizomba, soca, calypso, bachata, salsa, cumbia, merengue, or other>",
      "segments": [
        {{
          "start_line": <line number where segment starts>,
          "end_line": <line number where segment ends>,
          "lyrics": "<exact lyrics from those lines>",
          "ai_description": "<2 sentences describing emotional content - start with emotion, not 'This segment'>",
          "primary_emotion": "<main emotion>",
          "secondary_emotion": "<supporting emotion or null>",
          "energy": "<low|medium|high|very-high>",
          "tone": "<how emotion is expressed>"
        }}
      ]
    }}
  ]
}}

Important:
- song_index MUST match the SONG number (1, 2, 3...)
- Include title and artist in each song object for verification
- If a song cannot be segmented, include it with empty segments array and add "error": "<reason>"
- Line numbers must match the numbered lyrics for THAT specific song (each song starts at line 1)
- ai_description: Start with emotion/theme, NOT "This segment" or similar
- Output ONLY the JSON, no other text"""


def _create_numbered_lyrics(lyrics: str) -> str:
    """Add line numbers to lyrics for the prompt."""
    lines = lyrics.strip().split("\n")
    numbered = []
    line_num = 0
    for line in lines:
        if line.strip():  # Skip empty lines in numbering
            line_num += 1
            numbered.append(f"{line_num}. {line}")
    return "\n".join(numbered)


def _build_batched_prompt(
    songs: list[tuple[str, str, str, int]],
) -> str:
    """
    Build prompt for multiple songs.

    Args:
        songs: List of (lyrics, title, artist, track_id) tuples

    Returns:
        Complete prompt string with all songs
    """
    song_sections = []

    for i, (lyrics, title, artist, _track_id) in enumerate(songs, 1):
        numbered_lyrics = _create_numbered_lyrics(lyrics)
        song_section = f"""--- SONG {i}: "{title}" by {artist} ---
Lyrics (with line numbers):
{numbered_lyrics}
"""
        song_sections.append(song_section)

    songs_section = "\n".join(song_sections)
    return BATCHED_SEGMENTATION_PROMPT.format(songs_section=songs_section)


def _normalize_genre(genre: Optional[str]) -> str:
    """Normalize genre to a valid value."""
    if not genre:
        return "other"

    genre_lower = genre.lower().strip()

    # Direct match
    if genre_lower in VALID_GENRES:
        return genre_lower

    # Common aliases
    aliases = {
        "hiphop": "hip-hop",
        "hip hop": "hip-hop",
        "rnb": "r&b",
        "rhythm and blues": "r&b",
        "afro": "afrobeats",
        "afro-beats": "afrobeats",
        "dancehall/reggae": "dancehall",
        "edm": "electronic",
        "dance": "electronic",
        "alternative": "indie",
        "alt rock": "indie",
        "alt-rock": "indie",
        "alternative rock": "indie",
        "urban": "hip-hop",
        "tropical": "latin",
        "world": "other",
    }

    if genre_lower in aliases:
        return aliases[genre_lower]

    # Partial match
    for valid_genre in VALID_GENRES:
        if valid_genre in genre_lower or genre_lower in valid_genre:
            return valid_genre

    return "other"


def _parse_segments_response(response_text: str) -> tuple[str, list[Segment]]:
    """Parse LLM response into genre and Segment objects."""
    # Try to extract JSON from response
    response_text = response_text.strip()

    # Handle case where LLM adds extra text before/after JSON
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()

    # Find JSON object boundaries
    if "{" in response_text:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        response_text = response_text[start:end]

    data = json.loads(response_text)

    # Extract and normalize genre
    raw_genre = data.get("genre")
    genre = _normalize_genre(raw_genre)

    segments = []

    for seg in data.get("segments", []):
        segments.append(Segment(
            start_line=int(seg["start_line"]),
            end_line=int(seg["end_line"]),
            lyrics=seg["lyrics"],
            ai_description=seg["ai_description"],
            primary_emotion=seg["primary_emotion"],
            secondary_emotion=seg.get("secondary_emotion"),
            energy=seg["energy"],
            tone=seg["tone"],
        ))

    return genre, segments


def _parse_batched_response(
    response_text: str,
    expected_songs: list[tuple[str, str, int]],
) -> list[BatchedSongResult]:
    """
    Parse batched LLM response into individual song results.

    Args:
        response_text: Raw JSON response from LLM
        expected_songs: List of (title, artist, track_id) tuples in input order

    Returns:
        List of BatchedSongResult, one per expected song
    """
    # Extract JSON from response
    response_text = response_text.strip()

    # Handle markdown code blocks
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        response_text = response_text[start:end].strip()

    # Find JSON object boundaries
    if "{" in response_text:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        response_text = response_text[start:end]

    data = json.loads(response_text)
    songs_data = data.get("songs", [])

    # Build lookup by song_index
    response_by_index: dict[int, dict] = {}
    for song in songs_data:
        idx = song.get("song_index")
        if idx is not None:
            response_by_index[idx] = song

    # Build results for each expected song
    results: list[BatchedSongResult] = []

    for i, (title, artist, track_id) in enumerate(expected_songs, 1):
        song_data = response_by_index.get(i)

        if song_data is None:
            # Song missing from response
            results.append(BatchedSongResult(
                track_id=track_id,
                song_index=i,
                title=title,
                artist=artist,
                genre=None,
                segments=[],
                error="Not returned in batch response",
            ))
            continue

        # Check for explicit error from LLM
        if song_data.get("error"):
            results.append(BatchedSongResult(
                track_id=track_id,
                song_index=i,
                title=title,
                artist=artist,
                genre=_normalize_genre(song_data.get("genre")),
                segments=[],
                error=song_data["error"],
            ))
            continue

        # Parse segments
        try:
            segments = []
            for seg in song_data.get("segments", []):
                segments.append(Segment(
                    start_line=int(seg["start_line"]),
                    end_line=int(seg["end_line"]),
                    lyrics=seg["lyrics"],
                    ai_description=seg["ai_description"],
                    primary_emotion=seg["primary_emotion"],
                    secondary_emotion=seg.get("secondary_emotion"),
                    energy=seg["energy"],
                    tone=seg["tone"],
                ))

            results.append(BatchedSongResult(
                track_id=track_id,
                song_index=i,
                title=title,
                artist=artist,
                genre=_normalize_genre(song_data.get("genre")),
                segments=segments,
            ))
        except (KeyError, TypeError, ValueError) as e:
            results.append(BatchedSongResult(
                track_id=track_id,
                song_index=i,
                title=title,
                artist=artist,
                genre=None,
                segments=[],
                error=f"Segment parse error: {e}",
            ))

    return results


async def _call_groq(prompt: str, max_tokens: int = 2000) -> str:
    """Call Groq API for segmentation (async)."""
    from groq import AsyncGroq

    api_key = get_api_key("groq")
    client = AsyncGroq(api_key=api_key)

    response = await client.chat.completions.create(
        model=LLM_MODEL_GROQ,
        messages=[
            {
                "role": "system",
                "content": "You are a music analysis expert. Output only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
    )

    content = response.choices[0].message.content
    if content is None:
        raise ValueError("Groq returned empty response")
    return content


async def _call_together(prompt: str, max_tokens: int = 2000) -> str:
    """Call Together.ai API for segmentation (async)."""
    from together import AsyncTogether

    api_key = get_api_key("together")
    client = AsyncTogether(api_key=api_key)

    response = await client.chat.completions.create(
        model=LLM_MODEL_TOGETHER,
        messages=[
            {
                "role": "system",
                "content": "You are a music analysis expert. Output only valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=max_tokens,
        stream=False,
    )

    # Type narrowing: stream=False returns ChatCompletion, not AsyncGenerator
    if response is None:
        raise ValueError("Together.ai returned no response")
    content = response.choices[0].message.content  # type: ignore[union-attr]
    if content is None:
        raise ValueError("Together.ai returned empty response")
    # Todo: come back and fix later
    return content # type: ignore


async def segment_lyrics(
    lyrics: str,
    title: str,
    artist: str,
    providers: Optional[list[str]] = None,
) -> SegmentationResult:
    """
    Analyze lyrics and identify meaningful segments using LLM.

    Args:
        lyrics: Plain lyrics text (without timestamps)
        title: Song title
        artist: Artist name
        providers: List of providers to try in order (defaults to config)

    Returns:
        SegmentationResult with identified segments
    """
    providers_list: list[str] = providers if providers else LLM_PROVIDERS

    # Build prompt
    numbered_lyrics = _create_numbered_lyrics(lyrics)
    prompt = SEGMENTATION_PROMPT.format(
        title=title,
        artist=artist,
        numbered_lyrics=numbered_lyrics,
    )

    last_error: Optional[str] = None

    for provider in providers_list:
        for attempt in range(MAX_RETRIES):
            try:
                # Call appropriate provider
                if provider == "groq":
                    response_text = await _call_groq(prompt)
                elif provider == "together":
                    response_text = await _call_together(prompt)
                else:
                    continue

                # Parse response
                genre, segments = _parse_segments_response(response_text)

                if segments:
                    return SegmentationResult(
                        success=True,
                        segments=segments,
                        genre=genre,
                        provider=provider,
                    )

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
            except ValueError as e:
                # API key not set - skip this provider
                last_error = str(e)
                break  # Don't retry, move to next provider
            except GroqRateLimitError as e:
                # Use exact retry-after time from Groq headers
                retry_after_ms = e.response.headers.get("retry-after-ms")
                if retry_after_ms:
                    wait_time = float(retry_after_ms) / 1000
                else:
                    retry_after = e.response.headers.get("retry-after")
                    wait_time = float(retry_after) if retry_after else 60.0

                # Return immediately with retry info (don't block waiting)
                return SegmentationResult(
                    success=False,
                    segments=[],
                    genre=None,
                    provider=provider,
                    error=f"Rate limited by {provider}",
                    retry_after_seconds=wait_time,
                )
            except Exception as e:
                last_error = f"{provider} error: {e}"

            # Wait before retry (for non-rate-limit errors)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return SegmentationResult(
        success=False,
        segments=[],
        genre=None,
        provider=None,
        error=last_error or "All providers failed",
    )


async def segment_lyrics_batch(
    songs: list[tuple[str, str, str, int]],
    providers: Optional[list[str]] = None,
) -> BatchSegmentationResult:
    """
    Analyze multiple songs' lyrics in a single LLM call.

    Args:
        songs: List of (lyrics, title, artist, track_id) tuples
        providers: List of providers to try in order (defaults to config)

    Returns:
        BatchSegmentationResult with results for each song
    """
    if not songs:
        return BatchSegmentationResult(
            success=True,
            song_results=[],
            provider=None,
        )

    providers_list: list[str] = providers if providers else LLM_PROVIDERS

    # Build batched prompt
    prompt = _build_batched_prompt(songs)

    # Track expected songs for matching (title, artist, track_id)
    expected_songs = [(title, artist, track_id) for (_, title, artist, track_id) in songs]

    # Calculate max_tokens based on batch size (roughly 1500 tokens per song)
    max_tokens = min(15000, len(songs) * 1500)

    last_error: Optional[str] = None

    for provider in providers_list:
        for attempt in range(MAX_RETRIES):
            try:
                # Call appropriate provider
                if provider == "groq":
                    response_text = await _call_groq(prompt, max_tokens=max_tokens)
                elif provider == "together":
                    response_text = await _call_together(prompt, max_tokens=max_tokens)
                else:
                    continue
                # Parse batched response
                song_results = _parse_batched_response(response_text, expected_songs)

                # Check if at least some songs succeeded
                success_count = sum(1 for r in song_results if r.segments)
                if success_count > 0:
                    return BatchSegmentationResult(
                        success=True,
                        song_results=song_results,
                        provider=provider,
                    )

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
            except ValueError as e:
                # API key not set - skip this provider
                last_error = str(e)
                break  # Don't retry, move to next provider
            except GroqRateLimitError as e:
                # Use exact retry-after time from Groq headers
                retry_after_ms = e.response.headers.get("retry-after-ms")
                if retry_after_ms:
                    wait_time = float(retry_after_ms) / 1000
                else:
                    retry_after = e.response.headers.get("retry-after")
                    wait_time = float(retry_after) if retry_after else 60.0

                # Return immediately with retry info (don't block waiting)
                return BatchSegmentationResult(
                    success=False,
                    song_results=[],
                    provider=provider,
                    error=f"Rate limited by {provider}",
                    retry_after_seconds=wait_time,
                )
            except Exception as e:
                last_error = f"{provider} error: {e}"

            # Wait before retry (for non-rate-limit errors)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    # All providers failed - return error for all songs
    return BatchSegmentationResult(
        success=False,
        song_results=[
            BatchedSongResult(
                track_id=track_id,
                song_index=i + 1,
                title=title,
                artist=artist,
                genre=None,
                segments=[],
                error="Batch API call failed",
            )
            for i, (_, title, artist, track_id) in enumerate(songs)
        ],
        provider=None,
        error=last_error or "All providers failed for batch",
    )


def validate_segments(
    segments: list[Segment],
    total_lines: int,
) -> tuple[list[Segment], list[str]]:
    """
    Validate and filter segments.

    Args:
        segments: List of segments from LLM
        total_lines: Total number of lines in lyrics

    Returns:
        Tuple of (valid_segments, error_messages)
    """
    valid = []
    errors = []

    for i, seg in enumerate(segments):
        # Check line numbers are valid
        if seg.start_line < 1:
            errors.append(f"Segment {i}: start_line < 1")
            continue

        if seg.end_line < seg.start_line:
            errors.append(f"Segment {i}: end_line < start_line")
            continue

        if seg.end_line > total_lines:
            errors.append(f"Segment {i}: end_line > total_lines ({total_lines})")
            continue

        # Check required fields
        if not seg.ai_description:
            errors.append(f"Segment {i}: missing ai_description")
            continue

        if not seg.primary_emotion:
            errors.append(f"Segment {i}: missing primary_emotion")
            continue

        # Validate energy level
        if seg.energy not in ("low", "medium", "high", "very-high"):
            seg.energy = "medium"  # Default to medium

        valid.append(seg)

    return valid, errors
