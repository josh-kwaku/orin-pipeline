"""
Curated YouTube playlist import module.

Handles:
- Extracting video metadata from YouTube playlists
- Parsing artist/title from video titles
- Storing tracks with synced lyrics in curated database
"""

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .lrclib_api import search_lyrics, LRCLibResult
from .pipeline_status import get_processed_ids

# Default database path
CURATED_DB_PATH = Path(__file__).parent.parent / "data" / "curated_tracks.sqlite"


@dataclass
class YouTubeVideo:
    """Metadata for a YouTube video."""

    video_id: str
    title: str
    uploader: str
    duration: float
    url: str


@dataclass
class ImportResult:
    """Result of playlist import operation."""

    playlist_id: int
    total_videos: int
    imported: int
    skipped: int
    errors: list[str]


def normalize_song_key(artist: str, title: str) -> str:
    """
    Create normalized key for song deduplication.

    Same song from different YouTube videos (official video, lyric video, etc.)
    will produce the same key.

    Args:
        artist: Artist name
        title: Song title

    Returns:
        Normalized key in format "artist|title"
    """
    def normalize(s: str) -> str:
        s = s.lower().strip()
        # Remove featuring artists (they vary between sources)
        for pat in [' ft.', ' feat.', ' featuring', ' ft ', ' feat ', '(ft.', '(feat.']:
            idx = s.find(pat)
            if idx != -1:
                s = s[:idx]
        # Remove common suffixes
        for suffix in ['(official)', '(lyrics)', '(audio)', '(video)',
                       '(official video)', '(official audio)', '(lyric video)']:
            s = s.replace(suffix, '')
        # Remove non-alphanumeric (keep spaces)
        s = ''.join(c for c in s if c.isalnum() or c.isspace())
        # Normalize whitespace
        return ' '.join(s.split())

    return f"{normalize(artist)}|{normalize(title)}"


# SQL schema for curated database
SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    youtube_url TEXT UNIQUE NOT NULL,
    genre TEXT NOT NULL,
    name TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER REFERENCES playlists(id),
    youtube_video_id TEXT UNIQUE NOT NULL,
    youtube_title TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    name TEXT NOT NULL,
    album_name TEXT,
    duration FLOAT NOT NULL,
    synced_lyrics TEXT NOT NULL,
    genre TEXT NOT NULL,
    lrclib_id INTEGER,
    song_key TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skipped_tracks (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER REFERENCES playlists(id),
    youtube_video_id TEXT NOT NULL,
    youtube_title TEXT NOT NULL,
    parsed_artist TEXT,
    parsed_title TEXT,
    reason TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_playlist ON tracks(playlist_id);
"""

# Separate index for song_key - created after migration ensures column exists
SONG_KEY_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_song_key ON tracks(song_key);
"""


def init_database(db_path: Path = CURATED_DB_PATH) -> None:
    """Initialize the curated database with schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()

        # Migration: add song_key column if missing (for existing databases)
        cursor = conn.execute("PRAGMA table_info(tracks)")
        columns = [row[1] for row in cursor.fetchall()]

        if "song_key" not in columns:
            conn.execute("ALTER TABLE tracks ADD COLUMN song_key TEXT")
            conn.commit()

        # Backfill song_key for any rows that don't have it
        cursor = conn.execute(
            "SELECT id, artist_name, name FROM tracks WHERE song_key IS NULL"
        )
        rows_to_update = cursor.fetchall()

        if rows_to_update:
            for row_id, artist, title in rows_to_update:
                key = normalize_song_key(artist, title)
                conn.execute(
                    "UPDATE tracks SET song_key = ? WHERE id = ?",
                    (key, row_id),
                )
            conn.commit()

        # Create the unique index (after column exists and is populated)
        try:
            conn.executescript(SONG_KEY_INDEX)
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicates exist - need manual resolution
            print("Warning: Duplicate songs detected in database. Run dedup command to resolve.")
    finally:
        conn.close()


def extract_playlist_videos(playlist_url: str) -> list[YouTubeVideo]:
    """
    Extract video metadata from a YouTube playlist using yt-dlp.

    Args:
        playlist_url: YouTube playlist URL

    Returns:
        List of YouTubeVideo objects
    """
    result = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            playlist_url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[:200]}")

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            videos.append(
                YouTubeVideo(
                    video_id=data.get("id", ""),
                    title=data.get("title", ""),
                    uploader=data.get("uploader", data.get("channel", "")),
                    duration=data.get("duration", 0) or 0,
                    url=data.get("url", f"https://www.youtube.com/watch?v={data.get('id', '')}"),
                )
            )
        except json.JSONDecodeError:
            continue

    return videos


def get_playlist_title(playlist_url: str) -> Optional[str]:
    """Get the title of a YouTube playlist."""
    result = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--print", "%(playlist_title)s",
            "--playlist-items", "1",
            playlist_url,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def clean_title(title: str) -> str:
    """
    Remove common suffixes from video titles.

    Removes things like:
    - (Official Video)
    - [Official Audio]
    - (Lyrics)
    - (Audio)
    - [HD]
    - ft. Artist
    """
    patterns = [
        r"\s*\(Official\s*(Video|Audio|Music Video|Lyric Video|Visualizer)?\s*\)",
        r"\s*\[Official\s*(Video|Audio|Music Video|Lyric Video|Visualizer)?\s*\]",
        r"\s*\(Lyric[s]?\s*(Video)?\s*\)",
        r"\s*\[Lyric[s]?\s*(Video)?\s*\]",
        r"\s*\(Audio\s*(Only)?\s*\)",
        r"\s*\[Audio\s*(Only)?\s*\]",
        r"\s*\(Video\s*(Oficial|Officiel)?\s*\)",
        r"\s*\[Video\s*(Oficial|Officiel)?\s*\]",
        r"\s*\(Performance\s*(Video)?\s*\)",
        r"\s*\[Performance\s*(Video)?\s*\]",
        r"\s*\(Live\s*(Video|Performance|Session|at\s+.*)?\s*\)",
        r"\s*\[Live\s*(Video|Performance|Session|at\s+.*)?\s*\]",
        r"\s*\(Acoustic\s*(Version|Video|Session)?\s*\)",
        r"\s*\[Acoustic\s*(Version|Video|Session)?\s*\]",
        r"\s*\[HD\]",
        r"\s*\[HQ\]",
        r"\s*\(HD\)",
        r"\s*\(HQ\)",
        r"\s*\(Prod\..*?\)",
        r"\s*\[Prod\..*?\]",
    ]

    result = title
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result.strip()


def parse_video_title(title: str) -> tuple[str, str]:
    """
    Parse artist and song name from YouTube video title.

    Common formats:
    - "Artist - Song Title"
    - "Artist - Song Title (Official Video)"
    - "Song Title - Artist"
    - "Artist: Song Title"
    - "Artist | Song Title"

    Args:
        title: YouTube video title

    Returns:
        Tuple of (artist, song_name)
    """
    # Clean the title first
    cleaned = clean_title(title)

    # Try common separators
    separators = [" - ", " – ", " — ", " | ", ": "]

    for sep in separators:
        if sep in cleaned:
            parts = cleaned.split(sep, 1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()

                # Heuristic: if right side has "ft." or "feat.", left is likely artist
                # Otherwise, shorter side is usually the artist
                if "ft." in right.lower() or "feat." in right.lower():
                    return left, right
                elif "ft." in left.lower() or "feat." in left.lower():
                    return right, left

                # Default: left is artist, right is song
                return left, right

    # No separator found - return empty artist, whole title as song
    return "", cleaned


def import_playlist(
    playlist_url: str,
    genre: str,
    db_path: Path = CURATED_DB_PATH,
    dry_run: bool = False,
    verbose: bool = True,
) -> ImportResult:
    """
    Import a YouTube playlist into the curated database.

    Args:
        playlist_url: YouTube playlist URL
        genre: Genre tag for all tracks in this playlist
        db_path: Path to curated database
        dry_run: If True, don't write to database
        verbose: If True, print progress

    Returns:
        ImportResult with statistics
    """
    # Initialize database
    if not dry_run:
        init_database(db_path)

    # Get playlist info
    if verbose:
        print(f"Fetching playlist: {playlist_url}")

    playlist_title = get_playlist_title(playlist_url)
    videos = extract_playlist_videos(playlist_url)

    if verbose:
        print(f"Found {len(videos)} videos in playlist: {playlist_title or 'Unknown'}")

    # Insert playlist record
    playlist_id = 0
    if not dry_run:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO playlists (youtube_url, genre, name)
                VALUES (?, ?, ?)
                """,
                (playlist_url, genre, playlist_title),
            )
            conn.commit()

            # Get the playlist ID
            cursor = conn.execute(
                "SELECT id FROM playlists WHERE youtube_url = ?",
                (playlist_url,),
            )
            playlist_id = cursor.fetchone()[0]
        finally:
            conn.close()

    imported = 0
    skipped = 0
    errors = []

    for i, video in enumerate(videos, 1):
        if verbose:
            print(f"\n[{i}/{len(videos)}] {video.title[:60]}...")

        # Parse artist and title
        artist, song_name = parse_video_title(video.title)

        # If no artist from title, try using channel/uploader name
        if not artist and song_name:
            artist = video.uploader or ""
            # Clean up YouTube auto-generated channel suffixes
            if artist.endswith(" - Topic"):
                artist = artist[:-8]  # Remove " - Topic"
            if verbose and artist:
                print(f"  Using channel as artist: {artist}")

        if not artist or not song_name:
            if verbose:
                print(f"  ✗ Could not parse artist/title")
            skipped += 1
            if not dry_run:
                _insert_skipped(db_path, playlist_id, video, artist, song_name, "parse_failed")
            continue

        if verbose:
            print(f"  Parsed: {artist} - {song_name}")

        # Search LRCLib for synced lyrics
        if verbose:
            print(f"  Searching LRCLib...")

        result = search_lyrics(artist, song_name, video.duration)

        if not result:
            if verbose:
                print(f"  ✗ No synced lyrics found")
            skipped += 1
            if not dry_run:
                _insert_skipped(db_path, playlist_id, video, artist, song_name, "no_lyrics")
            continue

        if verbose:
            print(f"  ✓ Found lyrics ({len(result.synced_lyrics)} chars)")

        # Insert track
        if not dry_run:
            try:
                _insert_track(db_path, playlist_id, video, result, genre)
                imported += 1
            except DuplicateVideoError:
                if verbose:
                    print(f"  ✗ Already imported (same video)")
                skipped += 1
            except DuplicateSongError:
                if verbose:
                    print(f"  ✗ Already curated (different video, same song)")
                skipped += 1
        else:
            imported += 1

    return ImportResult(
        playlist_id=playlist_id,
        total_videos=len(videos),
        imported=imported,
        skipped=skipped,
        errors=errors,
    )


class DuplicateSongError(Exception):
    """Raised when trying to insert a song that already exists (by song_key)."""
    pass


class DuplicateVideoError(Exception):
    """Raised when trying to insert a video that already exists (by video_id)."""
    pass


def _insert_track(
    db_path: Path,
    playlist_id: int,
    video: YouTubeVideo,
    lyrics: LRCLibResult,
    genre: str,
) -> None:
    """Insert a track into the curated database.

    Raises:
        DuplicateVideoError: If this YouTube video was already imported
        DuplicateSongError: If this song already exists (different video, same song)
    """
    song_key = normalize_song_key(lyrics.artist_name, lyrics.track_name)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO tracks (
                playlist_id, youtube_video_id, youtube_title,
                artist_name, name, album_name, duration,
                synced_lyrics, genre, lrclib_id, song_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                playlist_id,
                video.video_id,
                video.title,
                lyrics.artist_name,
                lyrics.track_name,
                lyrics.album_name,
                lyrics.duration,
                lyrics.synced_lyrics,
                genre,
                lyrics.id,
                song_key,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        # Determine which constraint was violated
        error_msg = str(e).lower()
        if "youtube_video_id" in error_msg:
            raise DuplicateVideoError(f"Video {video.video_id} already imported")
        elif "song_key" in error_msg:
            raise DuplicateSongError(f"Song '{lyrics.artist_name} - {lyrics.track_name}' already curated")
        else:
            # Generic integrity error - re-raise original
            raise
    finally:
        conn.close()


def _insert_skipped(
    db_path: Path,
    playlist_id: int,
    video: YouTubeVideo,
    parsed_artist: str,
    parsed_title: str,
    reason: str,
) -> None:
    """Insert a skipped track record."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO skipped_tracks (
                playlist_id, youtube_video_id, youtube_title,
                parsed_artist, parsed_title, reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                playlist_id,
                video.video_id,
                video.title,
                parsed_artist,
                parsed_title,
                reason,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_curated_track_count(
    db_path: Path = CURATED_DB_PATH,
    genre: Optional[str] = None,
) -> int:
    """Get count of curated tracks."""
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        if genre:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM tracks WHERE genre = ?",
                (genre,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM tracks")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_curated_tracks(
    db_path: Path = CURATED_DB_PATH,
    genre: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    exclude_processed: bool = True,
) -> Generator[dict, None, None]:
    """
    Yield curated tracks from the database.

    Args:
        db_path: Path to curated database
        genre: Filter by genre (optional)
        limit: Maximum tracks to return
        offset: Skip first N tracks
        exclude_processed: If True, skip tracks already processed through pipeline

    Yields:
        Dict with track data compatible with pipeline
    """
    if not db_path.exists():
        return

    # Load processed IDs for filtering (O(1) lookup)
    processed_ids = get_processed_ids("curated") if exclude_processed else set()

    query = """
        SELECT
            id, youtube_video_id, youtube_title,
            artist_name, name, album_name, duration,
            synced_lyrics, genre, lrclib_id
        FROM tracks
    """

    params = []
    if genre:
        query += " WHERE genre = ?"
        params.append(genre)

    # When filtering processed, fetch extra to account for filtered-out tracks
    fetch_limit = None
    if limit is not None and exclude_processed and processed_ids:
        fetch_limit = limit * 3 + len(processed_ids)
    elif limit is not None:
        fetch_limit = limit

    if fetch_limit is not None:
        query += f" LIMIT {fetch_limit}"
    if offset:
        query += f" OFFSET {offset}"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query, params)
        yielded = 0

        for row in cursor:
            # Skip if already processed
            if exclude_processed and row["id"] in processed_ids:
                continue
            yield {
                "id": row["id"],
                "youtube_video_id": row["youtube_video_id"],
                "youtube_title": row["youtube_title"],
                "artist_name": row["artist_name"],
                "name": row["name"],
                "album_name": row["album_name"],
                "duration": row["duration"],
                "synced_lyrics": row["synced_lyrics"],
                "genre": row["genre"],
                "lrclib_id": row["lrclib_id"],
            }

            yielded += 1
            if limit is not None and yielded >= limit:
                break
    finally:
        conn.close()


def list_playlists(db_path: Path = CURATED_DB_PATH) -> list[dict]:
    """List all imported playlists."""
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT
                p.id, p.youtube_url, p.genre, p.name, p.imported_at,
                COUNT(t.id) as track_count
            FROM playlists p
            LEFT JOIN tracks t ON t.playlist_id = p.id
            GROUP BY p.id
            ORDER BY p.imported_at DESC
            """
        )
        return [dict(row) for row in cursor]
    finally:
        conn.close()


def list_skipped(
    db_path: Path = CURATED_DB_PATH,
    playlist_id: Optional[int] = None,
) -> list[dict]:
    """List skipped tracks for review."""
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if playlist_id:
            cursor = conn.execute(
                "SELECT * FROM skipped_tracks WHERE playlist_id = ?",
                (playlist_id,),
            )
        else:
            cursor = conn.execute("SELECT * FROM skipped_tracks")
        return [dict(row) for row in cursor]
    finally:
        conn.close()
