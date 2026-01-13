"""
Playlist-related schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl


class PlaylistImportRequest(BaseModel):
    """Request to import a YouTube playlist."""
    url: str
    genre: str
    dry_run: bool = False


class PlaylistImportResponse(BaseModel):
    """Response from starting playlist import."""
    task_id: str
    message: str


class ImportStatusResponse(BaseModel):
    """Current import status."""
    running: bool
    task_id: Optional[str] = None
    playlist_name: Optional[str] = None
    current_track: Optional[dict] = None
    progress: dict
    errors: list[str]


class PlaylistSummary(BaseModel):
    """Summary of a playlist."""
    id: int
    youtube_url: str
    genre: str
    name: Optional[str]
    track_count: int
    imported_at: Optional[str]


class PlaylistListResponse(BaseModel):
    """Response containing list of playlists."""
    playlists: list[PlaylistSummary]
    total: int
