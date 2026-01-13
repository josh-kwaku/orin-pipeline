"""
Playlist management endpoints.
"""

from fastapi import APIRouter, HTTPException

from ..deps import CuratedDbPath
from ..schemas.playlist import (
    PlaylistImportRequest,
    PlaylistImportResponse,
    PlaylistSummary,
    PlaylistListResponse,
    ImportStatusResponse,
)
from ..services.import_runner import import_runner
from src.curated import list_playlists

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
    Start importing a YouTube playlist.

    Returns immediately with a task ID. Connect to /pipeline/events for real-time updates.

    Events emitted:
    - import_fetching: Starting to fetch playlist metadata
    - import_started: Playlist fetched, processing tracks
    - import_track_processing: Processing a track (parsing, searching lyrics)
    - import_track_imported: Track successfully imported
    - import_track_skipped: Track skipped (no lyrics, duplicate, etc.)
    - import_complete: Import finished
    - import_error: Fatal error during import
    - import_stopped: Import was stopped by user
    """
    try:
        task_id, _ = await import_runner.start(
            playlist_url=request.url,
            genre=request.genre,
            db_path=curated_db,
            dry_run=request.dry_run,
        )

        return PlaylistImportResponse(
            task_id=task_id,
            message="Import started. Connect to /pipeline/events for progress updates.",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import/status", response_model=ImportStatusResponse)
async def get_import_status():
    """Get current import status."""
    status = import_runner.get_status()

    return ImportStatusResponse(
        running=status["running"],
        task_id=status["task_id"],
        playlist_name=status["playlist_name"],
        current_track=status["current_track"],
        progress=status["progress"],
        errors=status["errors"],
    )


@router.post("/import/stop")
async def stop_import():
    """Stop the currently running import."""
    stopped = await import_runner.stop()

    if stopped:
        return {"stopped": True, "message": "Stop requested. Import will stop after current track."}
    else:
        return {"stopped": False, "message": "No import is currently running."}
