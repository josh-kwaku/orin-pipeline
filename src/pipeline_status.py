"""
Pipeline status tracking module.

Tracks which tracks have been successfully processed through the pipeline.
Works for both LRCLib and curated sources.
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Database path
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PIPELINE_STATUS_DB = DATA_DIR / "pipeline_status.sqlite"

# Schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_tracks (
    source TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, track_id)
);
"""


def init_status_db(db_path: Path = PIPELINE_STATUS_DB) -> None:
    """Initialize the pipeline status database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def mark_processed(
    source: str,
    track_id: int,
    db_path: Path = PIPELINE_STATUS_DB,
) -> None:
    """
    Mark a track as successfully processed.

    Args:
        source: "lrclib" or "curated"
        track_id: The track ID from the source database
        db_path: Path to status database
    """
    init_status_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO processed_tracks (source, track_id) VALUES (?, ?)",
            (source, track_id),
        )
        conn.commit()
    finally:
        conn.close()


def is_processed(
    source: str,
    track_id: int,
    db_path: Path = PIPELINE_STATUS_DB,
) -> bool:
    """
    Check if a track has been processed.

    Args:
        source: "lrclib" or "curated"
        track_id: The track ID to check
        db_path: Path to status database

    Returns:
        True if track has been processed
    """
    if not db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT 1 FROM processed_tracks WHERE source = ? AND track_id = ?",
            (source, track_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def get_processed_ids(
    source: str,
    db_path: Path = PIPELINE_STATUS_DB,
) -> set[int]:
    """
    Get all processed track IDs for a source.

    Args:
        source: "lrclib" or "curated"
        db_path: Path to status database

    Returns:
        Set of processed track IDs for O(1) lookup
    """
    if not db_path.exists():
        return set()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT track_id FROM processed_tracks WHERE source = ?",
            (source,),
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def get_processed_count(
    source: Optional[str] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> int:
    """
    Get count of processed tracks.

    Args:
        source: Filter by source (optional)
        db_path: Path to status database

    Returns:
        Number of processed tracks
    """
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        if source:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM processed_tracks WHERE source = ?",
                (source,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM processed_tracks")
        return cursor.fetchone()[0]
    finally:
        conn.close()


def clear_processed(
    source: Optional[str] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> int:
    """
    Clear processed status.

    Args:
        source: Clear only this source, or all if None
        db_path: Path to status database

    Returns:
        Number of records deleted
    """
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        if source:
            cursor = conn.execute(
                "DELETE FROM processed_tracks WHERE source = ?",
                (source,),
            )
        else:
            cursor = conn.execute("DELETE FROM processed_tracks")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
