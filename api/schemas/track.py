"""
Track-related schemas.
"""

from typing import Optional

from pydantic import BaseModel


class TrackSummary(BaseModel):
    """Summary of a track."""
    id: int
    artist_name: str
    name: str
    album_name: Optional[str]
    duration: float
    genre: str
    youtube_video_id: Optional[str] = None
    is_processed: bool = False


class TrackListResponse(BaseModel):
    """Response containing list of tracks."""
    tracks: list[TrackSummary]
    total: int
    offset: int
    limit: int


class SkippedTrack(BaseModel):
    """A track that was skipped during import."""
    id: int
    playlist_id: int
    youtube_video_id: str
    youtube_title: str
    parsed_artist: Optional[str]
    parsed_title: Optional[str]
    reason: str
    imported_at: Optional[str]


class SkippedTracksResponse(BaseModel):
    """Response containing list of skipped tracks."""
    tracks: list[SkippedTrack]
    total: int
