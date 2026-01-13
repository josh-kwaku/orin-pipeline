"""
Statistics-related schemas.
"""

from typing import Optional

from pydantic import BaseModel


class GenreCount(BaseModel):
    """Count of tracks by genre."""
    genre: str
    count: int


class StatsResponse(BaseModel):
    """Overall pipeline statistics."""
    curated_total: int
    curated_by_genre: list[GenreCount]
    processed_total: int
    processed_by_source: dict[str, int]
    indexed_total: int
    skipped_total: int
