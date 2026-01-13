"""
Search-related schemas.
"""

from typing import Optional

from pydantic import BaseModel


class SearchRequest(BaseModel):
    """Request to search for similar snippets."""
    query: str
    limit: int = 10
    genre: Optional[str] = None
    emotion: Optional[str] = None
    energy: Optional[str] = None


class SearchResultItem(BaseModel):
    """A single search result."""
    snippet_id: str
    score: float
    song_title: str
    artist: str
    album: Optional[str]
    lyrics: str
    ai_description: str
    snippet_url: str
    start_time: float
    end_time: float
    primary_emotion: str
    secondary_emotion: Optional[str]
    energy: str
    genre: str


class SearchResponse(BaseModel):
    """Response containing search results."""
    query: str
    results: list[SearchResultItem]
    total: int
