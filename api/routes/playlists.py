"""
Playlist management endpoints.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from ..deps import CuratedDbPath
from ..schemas.playlist import (
    PlaylistImportRequest,
    PlaylistImportResponse,
    PlaylistSummary,
    PlaylistListResponse,
)
from src.curated import import_playlist, list_playlists

router = APIRouter()


@router.get("/playlists", response_model=PlaylistListResponse)
async def get_playlists(curated_db: CuratedDbPath):
    """List all imported playlists."""
    playlists = list_playlists(db_path=curated_db)

    summaries = [
        PlaylistSummary(
            id=p["id"],
            youtube_url=p["youtube_url"],
            genre=p["genre"],
            name=p.get("name"),
            track_count=p.get("track_count", 0),
            imported_at=str(p.get("imported_at")) if p.get("imported_at") else None,
        )
        for p in playlists
    ]

    return PlaylistListResponse(
        playlists=summaries,
        total=len(summaries),
    )


@router.post("/playlists/import", response_model=PlaylistImportResponse)
async def import_youtube_playlist(
    request: PlaylistImportRequest,
    curated_db: CuratedDbPath,
):
    """
    Import a YouTube playlist.

    This is a synchronous operation that may take a while for large playlists.
    Consider using background tasks for production use.
    """
    try:
        result = import_playlist(
            playlist_url=request.url,
            genre=request.genre,
            db_path=curated_db,
            dry_run=request.dry_run,
            verbose=False,  # Don't print to console
        )

        return PlaylistImportResponse(
            playlist_id=result.playlist_id,
            total_videos=result.total_videos,
            imported=result.imported,
            skipped=result.skipped,
            errors=result.errors,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
