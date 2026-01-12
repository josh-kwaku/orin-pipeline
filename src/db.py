"""
LRCLib database extraction module.

Handles querying the LRCLib SQLite database for tracks with synced lyrics.
"""

import sqlite3
from dataclasses import dataclass
from typing import Generator, Optional

from .config import LRCLIB_DB_PATH, LRCLIB_FILTERS
from .pipeline_status import get_processed_ids


@dataclass
class Track:
    """Represents a track from LRCLib database."""

    id: int
    name: str
    artist_name: str
    album_name: Optional[str]
    duration: float
    synced_lyrics: str

    @property
    def search_query(self) -> str:
        """Generate a search query for yt-dlp."""
        return f"{self.artist_name} {self.name} official audio"


def get_track_count() -> int:
    """
    Get total count of tracks matching our filters.

    Returns:
        Number of tracks that match the filter criteria
    """
    query = """
        SELECT COUNT(*)
        FROM tracks t
        JOIN lyrics l ON t.last_lyrics_id = l.id
        WHERE l.has_synced_lyrics = 1
          AND l.instrumental = 0
          AND t.duration IS NOT NULL
          AND l.source = 'lrclib'
    """

    conn = sqlite3.connect(LRCLIB_DB_PATH)
    try:
        cursor = conn.execute(query)
        count = cursor.fetchone()[0]
        return count
    finally:
        conn.close()


def get_tracks(
    limit: Optional[int] = None,
    offset: int = 0,
    exclude_processed: bool = True,
) -> Generator[Track, None, None]:
    """
    Yield tracks from LRCLib database matching our filters.

    Args:
        limit: Maximum number of tracks to return (None for all)
        offset: Number of tracks to skip
        exclude_processed: If True, skip tracks already processed through pipeline

    Yields:
        Track objects with synced lyrics
    """
    # Load processed IDs for filtering (O(1) lookup)
    processed_ids = get_processed_ids("lrclib") if exclude_processed else set()

    # Note: No ORDER BY - allows SQLite to return rows as soon as filters match
    # This is much faster with LIMIT since it avoids full table scan + sort
    query = """
        SELECT
            t.id,
            t.name,
            t.artist_name,
            t.album_name,
            t.duration,
            l.synced_lyrics
        FROM tracks t
        JOIN lyrics l ON t.last_lyrics_id = l.id
        WHERE l.has_synced_lyrics = 1
          AND l.instrumental = 0
          AND t.duration IS NOT NULL
          AND l.source = 'lrclib'
    """

    # When filtering processed, we need to fetch more to hit limit after filtering
    # Use a larger fetch limit, then filter in Python
    fetch_limit = None
    if limit is not None and exclude_processed and processed_ids:
        # Fetch extra to account for filtered-out tracks
        fetch_limit = limit * 3 + len(processed_ids)
    elif limit is not None:
        fetch_limit = limit

    if fetch_limit is not None:
        query += f" LIMIT {fetch_limit}"
    if offset > 0:
        query += f" OFFSET {offset}"

    conn = sqlite3.connect(LRCLIB_DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(query)
        yielded = 0

        for row in cursor:
            # Skip if already processed
            if exclude_processed and row["id"] in processed_ids:
                continue

            yield Track(
                id=row["id"],
                name=row["name"],
                artist_name=row["artist_name"],
                album_name=row["album_name"],
                duration=row["duration"],
                synced_lyrics=row["synced_lyrics"],
            )

            yielded += 1
            if limit is not None and yielded >= limit:
                break
    finally:
        conn.close()


def get_track_by_id(track_id: int) -> Optional[Track]:
    """
    Get a specific track by ID.

    Args:
        track_id: The track ID to look up

    Returns:
        Track object or None if not found
    """
    query = """
        SELECT
            t.id,
            t.name,
            t.artist_name,
            t.album_name,
            t.duration,
            l.synced_lyrics
        FROM tracks t
        JOIN lyrics l ON t.last_lyrics_id = l.id
        WHERE t.id = ?
    """

    conn = sqlite3.connect(LRCLIB_DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.execute(query, (track_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return Track(
            id=row["id"],
            name=row["name"],
            artist_name=row["artist_name"],
            album_name=row["album_name"],
            duration=row["duration"],
            synced_lyrics=row["synced_lyrics"],
        )
    finally:
        conn.close()


def get_sample_tracks(n: int = 10) -> list[Track]:
    """
    Get a sample of tracks for testing.

    Args:
        n: Number of tracks to return

    Returns:
        List of Track objects
    """
    return list(get_tracks(limit=n))


def create_indexes() -> None:
    """
    Create indexes to speed up queries.

    Run this once on a fresh LRCLib database dump.
    Takes a few minutes but makes queries much faster.
    """
    indexes = [
        # Index for JOIN condition
        "CREATE INDEX IF NOT EXISTS idx_tracks_last_lyrics_id ON tracks(last_lyrics_id)",
        # Index for filter conditions on lyrics table
        "CREATE INDEX IF NOT EXISTS idx_lyrics_filters ON lyrics(has_synced_lyrics, instrumental, source)",
        # Index for duration filter
        "CREATE INDEX IF NOT EXISTS idx_tracks_duration ON tracks(duration) WHERE duration IS NOT NULL",
    ]

    conn = sqlite3.connect(LRCLIB_DB_PATH)
    try:
        for idx_sql in indexes:
            print(f"Creating index: {idx_sql[:60]}...")
            conn.execute(idx_sql)
        conn.commit()
        print("Indexes created successfully.")
    finally:
        conn.close()
