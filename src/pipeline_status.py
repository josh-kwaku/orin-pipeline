"""
Pipeline status tracking module.

Tracks which tracks have been processed through the pipeline (success or failure).
Works for both LRCLib and curated sources.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Literal

# Database path
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
PIPELINE_STATUS_DB = DATA_DIR / "pipeline_status.sqlite"

# Status types
TrackStatus = Literal["success", "failed", "skipped"]

# Schema with status column
SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_tracks (
    source TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    error_message TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, track_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_source_status
ON processed_tracks(source, status);
"""

# Migration to add status column if missing
MIGRATION = """
ALTER TABLE processed_tracks ADD COLUMN status TEXT NOT NULL DEFAULT 'success';
ALTER TABLE processed_tracks ADD COLUMN error_message TEXT;
"""


def init_status_db(db_path: Path = PIPELINE_STATUS_DB) -> None:
    """Initialize the pipeline status database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()

        # Check if migration needed (status column missing)
        cursor = conn.execute("PRAGMA table_info(processed_tracks)")
        columns = {row[1] for row in cursor.fetchall()}

        if "status" not in columns:
            # Run migration
            for stmt in MIGRATION.strip().split(";"):
                if stmt.strip():
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError:
                        pass  # Column already exists
            conn.commit()
    finally:
        conn.close()


def mark_processed(
    source: str,
    track_id: int,
    status: TrackStatus = "success",
    error_message: Optional[str] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> None:
    """
    Mark a track as processed (success or failure).

    Args:
        source: "lrclib" or "curated"
        track_id: The track ID from the source database
        status: "success", "failed", or "skipped"
        error_message: Error details if failed/skipped
        db_path: Path to status database
    """
    init_status_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO processed_tracks (source, track_id, status, error_message)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source, track_id) DO UPDATE SET
                status = excluded.status,
                error_message = excluded.error_message,
                processed_at = CURRENT_TIMESTAMP
            """,
            (source, track_id, status, error_message),
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
    Check if a track has been processed (success or failure).

    Args:
        source: "lrclib" or "curated"
        track_id: The track ID to check
        db_path: Path to status database

    Returns:
        True if track has been processed (any status)
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
    include_failed: bool = True,
    db_path: Path = PIPELINE_STATUS_DB,
) -> set[int]:
    """
    Get all processed track IDs for a source.

    Args:
        source: "lrclib" or "curated"
        include_failed: Include failed/skipped tracks (default True)
        db_path: Path to status database

    Returns:
        Set of processed track IDs for O(1) lookup
    """
    if not db_path.exists():
        return set()

    conn = sqlite3.connect(db_path)
    try:
        if include_failed:
            cursor = conn.execute(
                "SELECT track_id FROM processed_tracks WHERE source = ?",
                (source,),
            )
        else:
            cursor = conn.execute(
                "SELECT track_id FROM processed_tracks WHERE source = ? AND status = 'success'",
                (source,),
            )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def get_failed_ids(
    source: str,
    db_path: Path = PIPELINE_STATUS_DB,
) -> set[int]:
    """
    Get track IDs that failed processing.

    Args:
        source: "lrclib" or "curated"
        db_path: Path to status database

    Returns:
        Set of failed track IDs
    """
    if not db_path.exists():
        return set()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT track_id FROM processed_tracks WHERE source = ? AND status IN ('failed', 'skipped')",
            (source,),
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def get_processed_count(
    source: Optional[str] = None,
    status: Optional[TrackStatus] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> int:
    """
    Get count of processed tracks.

    Args:
        source: Filter by source (optional)
        status: Filter by status (optional)
        db_path: Path to status database

    Returns:
        Number of processed tracks
    """
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)
    try:
        conditions = []
        params = []

        if source:
            conditions.append("source = ?")
            params.append(source)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        cursor = conn.execute(
            f"SELECT COUNT(*) FROM processed_tracks WHERE {where_clause}",
            params,
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def clear_failed(
    source: Optional[str] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> int:
    """
    Clear failed/skipped status to allow retry.

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
                "DELETE FROM processed_tracks WHERE source = ? AND status IN ('failed', 'skipped')",
                (source,),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM processed_tracks WHERE status IN ('failed', 'skipped')"
            )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def clear_processed(
    source: Optional[str] = None,
    db_path: Path = PIPELINE_STATUS_DB,
) -> int:
    """
    Clear all processed status.

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
