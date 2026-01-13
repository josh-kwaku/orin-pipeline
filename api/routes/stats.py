"""
Statistics endpoints.
"""

import sqlite3
from pathlib import Path

from fastapi import APIRouter

from ..deps import CuratedDbPath, StatusDbPath
from ..schemas.stats import StatsResponse, GenreCount
from src.curated import get_curated_track_count, list_skipped, CURATED_DB_PATH
from src.pipeline_status import get_processed_count
from src.indexer import get_collection_count

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    curated_db: CuratedDbPath,
    status_db: StatusDbPath,
):
    """Get overall pipeline statistics."""
    # Curated tracks by genre
    curated_by_genre = []
    curated_total = 0

    if curated_db.exists():
        conn = sqlite3.connect(curated_db)
        try:
            cursor = conn.execute(
                "SELECT genre, COUNT(*) as count FROM tracks GROUP BY genre ORDER BY count DESC"
            )
            for row in cursor:
                curated_by_genre.append(GenreCount(genre=row[0], count=row[1]))
                curated_total += row[1]
        finally:
            conn.close()

    # Processed counts by source
    processed_lrclib = get_processed_count(source="lrclib", db_path=status_db)
    processed_curated = get_processed_count(source="curated", db_path=status_db)
    processed_total = processed_lrclib + processed_curated

    # Indexed count (Qdrant)
    try:
        indexed_total = await get_collection_count()
    except Exception:
        indexed_total = 0

    # Skipped count
    skipped_tracks = list_skipped(db_path=curated_db)
    skipped_total = len(skipped_tracks)

    return StatsResponse(
        curated_total=curated_total,
        curated_by_genre=curated_by_genre,
        processed_total=processed_total,
        processed_by_source={
            "lrclib": processed_lrclib,
            "curated": processed_curated,
        },
        indexed_total=indexed_total,
        skipped_total=skipped_total,
    )
