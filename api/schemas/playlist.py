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
    """Response from playlist import."""
    playlist_id: int
    total_videos: int
    imported: int
    skipped: int
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
