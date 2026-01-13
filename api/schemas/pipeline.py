"""
Pipeline control schemas.
"""

from typing import Optional

from pydantic import BaseModel


class PipelineStartRequest(BaseModel):
    """Request to start pipeline processing."""
    source: str = "curated"  # "lrclib" or "curated"
    genre: Optional[str] = None
    limit: Optional[int] = None
    dry_run: bool = False
    reprocess: bool = False


class PipelineStartResponse(BaseModel):
    """Response after starting pipeline."""
    task_id: str
    total_tracks: int
    message: str


class PipelineStatus(BaseModel):
    """Current pipeline status."""
    running: bool
    task_id: Optional[str] = None
    current_track: Optional[dict] = None
    progress: dict
    errors: list[str]


class PipelineStopResponse(BaseModel):
    """Response after stopping pipeline."""
    stopped: bool
    message: str
