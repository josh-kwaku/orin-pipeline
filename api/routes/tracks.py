"""
Track management endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Query

from ..deps import CuratedDbPath, StatusDbPath
from ..schemas.track import (
    TrackSummary,
    TrackListResponse,
    SkippedTrack,
    SkippedTracksResponse,
)
from src.curated import get_curated_tracks, get_curated_track_count, list_skipped
from src.pipeline_status import get_processed_ids

router = APIRouter()


@router.get("/tracks", response_model=TrackListResponse)
async def get_tracks(
    curated_db: CuratedDbPath,
    status_db: StatusDbPath,
    genre: Optional[str] = Query(None, description="Filter by genre"),
    status: Optional[str] = Query(None, description="Filter by status: pending, processed"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List tracks from the curated database.

    Supports filtering by genre and processing status.
    """
    # Determine if we should exclude processed tracks
    exclude_processed = status == "pending" if status else False
    include_only_processed = status == "processed"

    # Get processed IDs for status filtering
    processed_ids = get_processed_ids("curated", db_path=status_db)

    # Get tracks
    tracks_gen = get_curated_tracks(
        db_path=curated_db,
        genre=genre,
        limit=None,  # We'll filter ourselves for status
        offset=0,
        exclude_processed=False,  # We'll handle this
    )

    tracks = []
    skipped = 0

    for track in tracks_gen:
        is_processed = track["id"] in processed_ids

        # Apply status filter
        if exclude_processed and is_processed:
            continue
        if include_only_processed and not is_processed:
            continue

        # Apply offset
        if skipped < offset:
            skipped += 1
            continue

        tracks.append(
            TrackSummary(
                id=track["id"],
                artist_name=track["artist_name"],
                name=track["name"],
                album_name=track.get("album_name"),
                duration=track["duration"],
                genre=track["genre"],
                youtube_video_id=track.get("youtube_video_id"),
                is_processed=is_processed,
            )
        )

        if len(tracks) >= limit:
            break

    # Get total count
    total = get_curated_track_count(db_path=curated_db, genre=genre)

    return TrackListResponse(
        tracks=tracks,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/tracks/skipped", response_model=SkippedTracksResponse)
async def get_skipped_tracks(
    curated_db: CuratedDbPath,
    playlist_id: Optional[int] = Query(None, description="Filter by playlist ID"),
):
    """List tracks that were skipped during import."""
    skipped = list_skipped(db_path=curated_db, playlist_id=playlist_id)

    tracks = [
        SkippedTrack(
            id=s["id"],
            playlist_id=s["playlist_id"],
            youtube_video_id=s["youtube_video_id"],
            youtube_title=s["youtube_title"],
            parsed_artist=s.get("parsed_artist"),
            parsed_title=s.get("parsed_title"),
            reason=s["reason"],
            imported_at=str(s.get("imported_at")) if s.get("imported_at") else None,
        )
        for s in skipped
    ]

    return SkippedTracksResponse(
        tracks=tracks,
        total=len(tracks),
    )
