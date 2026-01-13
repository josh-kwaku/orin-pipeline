"""
Pipeline control endpoints with SSE support.
"""

import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..schemas.pipeline import (
    PipelineStartRequest,
    PipelineStartResponse,
    PipelineStatus,
    PipelineStopResponse,
)
from ..services.pipeline_runner import pipeline_runner
from ..services.event_manager import event_manager

router = APIRouter()


@router.post("/pipeline/start", response_model=PipelineStartResponse)
async def start_pipeline(request: PipelineStartRequest):
    """
    Start pipeline processing.

    Returns immediately with a task ID. Connect to /pipeline/events for real-time updates.
    """
    try:
        task_id, total_tracks = await pipeline_runner.start(
            source=request.source,
            genre=request.genre,
            limit=request.limit,
            dry_run=request.dry_run,
            reprocess=request.reprocess,
        )

        return PipelineStartResponse(
            task_id=task_id,
            total_tracks=total_tracks,
            message=f"Pipeline started. Processing {total_tracks} tracks.",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/stop", response_model=PipelineStopResponse)
async def stop_pipeline():
    """Stop the currently running pipeline."""
    stopped = await pipeline_runner.stop()

    if stopped:
        return PipelineStopResponse(
            stopped=True,
            message="Stop requested. Pipeline will stop after current track.",
        )
    else:
        return PipelineStopResponse(
            stopped=False,
            message="No pipeline is currently running.",
        )


@router.get("/pipeline/status", response_model=PipelineStatus)
async def get_pipeline_status():
    """Get current pipeline status."""
    status = pipeline_runner.get_status()

    return PipelineStatus(
        running=status["running"],
        task_id=status["task_id"],
        current_track=status["current_track"],
        progress=status["progress"],
        errors=status["errors"],
    )


@router.get("/pipeline/events")
async def pipeline_events(request: Request):
    """
    SSE endpoint for real-time events (pipeline and import).

    Pipeline Events:
    - pipeline_started: Pipeline started processing
    - track_start: New track being processed
    - track_complete: Track finished successfully
    - track_error: Track processing failed
    - pipeline_complete: All tracks processed
    - pipeline_stopped: Pipeline was stopped
    - pipeline_error: Fatal pipeline error

    Import Events:
    - import_fetching: Fetching playlist metadata
    - import_started: Playlist fetched, processing tracks
    - import_track_processing: Processing a track
    - import_track_imported: Track successfully imported
    - import_track_skipped: Track skipped
    - import_complete: Import finished
    - import_stopped: Import was stopped
    - import_error: Fatal import error
    """

    async def event_generator():
        queue = await event_manager.subscribe()

        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break

                try:
                    # Wait for event with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)

                    yield {
                        "event": event["type"],
                        "data": json.dumps(event["data"]),
                    }
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {
                        "event": "keepalive",
                        "data": json.dumps({"status": "connected"}),
                    }

        finally:
            await event_manager.unsubscribe(queue)

    import asyncio
    return EventSourceResponse(event_generator())
