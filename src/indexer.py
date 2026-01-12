"""
Qdrant vector database indexing module.

Handles:
- Collection management
- Vector upserts
- Semantic search

All operations are async for efficient network IO.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from .config import (
    EMBEDDING_DIMENSION,
    QDRANT_COLLECTION,
    QDRANT_HOST,
    QDRANT_PORT,
)


@dataclass
class SnippetPayload:
    """Payload data stored with each vector in Qdrant."""

    snippet_id: str
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
    tone: str
    genre: str  # Genre detected by LLM (required)
    track_id: int  # LRCLib track ID

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Qdrant payload."""
        return {
            "snippet_id": self.snippet_id,
            "song_title": self.song_title,
            "artist": self.artist,
            "album": self.album,
            "lyrics": self.lyrics,
            "ai_description": self.ai_description,
            "snippet_url": self.snippet_url,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "primary_emotion": self.primary_emotion,
            "secondary_emotion": self.secondary_emotion,
            "energy": self.energy,
            "tone": self.tone,
            "genre": self.genre,
            "track_id": self.track_id,
        }


@dataclass
class SearchResult:
    """Result from vector search."""

    snippet_id: str
    score: float
    payload: dict[str, Any]


@dataclass
class IndexResult:
    """Result of indexing operation."""

    success: bool
    indexed_count: int
    error: Optional[str] = None


def generate_snippet_id() -> str:
    """Generate a unique snippet ID."""
    return str(uuid.uuid4())


async def get_client() -> AsyncQdrantClient:
    """
    Get async Qdrant client.

    Note: For cloud Qdrant, set QDRANT_API_KEY environment variable.
    """
    import os

    api_key = os.environ.get("QDRANT_API_KEY")

    # If API key is set, assume cloud deployment
    if api_key:
        url = os.environ.get("QDRANT_URL")
        if url:
            return AsyncQdrantClient(url=url, api_key=api_key)

    # Local deployment
    return AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


async def ensure_collection(client: Optional[AsyncQdrantClient] = None) -> bool:
    """
    Ensure the collection exists with correct configuration.

    Creates collection if it doesn't exist.

    Returns:
        True if collection exists or was created successfully
    """
    close_client = client is None
    if client is None:
        client = await get_client()

    try:
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if QDRANT_COLLECTION not in collection_names:
            await client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )

        return True

    finally:
        if close_client:
            await client.close()


async def clear_collection(client: Optional[AsyncQdrantClient] = None) -> bool:
    """
    Delete and recreate the collection (clear all vectors).

    Returns:
        True if collection was cleared successfully
    """
    close_client = client is None
    if client is None:
        client = await get_client()

    try:
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if QDRANT_COLLECTION in collection_names:
            await client.delete_collection(collection_name=QDRANT_COLLECTION)

        # Recreate empty collection
        await client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )

        return True

    finally:
        if close_client:
            await client.close()


async def get_collection_count(client: Optional[AsyncQdrantClient] = None) -> int:
    """
    Get the number of vectors in the collection.

    Returns:
        Number of vectors, or 0 if collection doesn't exist
    """
    close_client = client is None
    if client is None:
        client = await get_client()

    try:
        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if QDRANT_COLLECTION not in collection_names:
            return 0

        info = await client.get_collection(collection_name=QDRANT_COLLECTION)
        return info.points_count or 0

    finally:
        if close_client:
            await client.close()


async def upsert_snippets(
    vectors: list[list[float]],
    payloads: list[SnippetPayload],
    client: Optional[AsyncQdrantClient] = None,
) -> IndexResult:
    """
    Upsert snippet vectors to Qdrant.

    Args:
        vectors: List of embedding vectors (768D each)
        payloads: List of SnippetPayload objects (same length as vectors)
        client: Optional existing client (will create one if not provided)

    Returns:
        IndexResult with success status and count
    """
    if len(vectors) != len(payloads):
        return IndexResult(
            success=False,
            indexed_count=0,
            error=f"Vector count ({len(vectors)}) != payload count ({len(payloads)})",
        )

    if not vectors:
        return IndexResult(success=True, indexed_count=0)

    close_client = client is None
    if client is None:
        client = await get_client()

    try:
        # Ensure collection exists
        await ensure_collection(client)

        # Build points
        points = [
            PointStruct(
                id=payload.snippet_id,
                vector=vector,
                payload=payload.to_dict(),
            )
            for vector, payload in zip(vectors, payloads)
        ]

        # Upsert to Qdrant
        await client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=points,
        )

        return IndexResult(
            success=True,
            indexed_count=len(points),
        )

    except Exception as e:
        return IndexResult(
            success=False,
            indexed_count=0,
            error=str(e),
        )

    finally:
        if close_client:
            await client.close()


async def search_snippets(
    query_vector: list[float],
    limit: int = 10,
    energy_filter: Optional[str] = None,
    emotion_filter: Optional[str] = None,
    genre_filter: Optional[str] = None,
    client: Optional[AsyncQdrantClient] = None,
) -> list[SearchResult]:
    """
    Search for similar snippets.

    Args:
        query_vector: Query embedding vector (768D)
        limit: Maximum number of results
        energy_filter: Optional filter by energy level (low, medium, high, very-high)
        emotion_filter: Optional filter by primary emotion
        genre_filter: Optional filter by genre
        client: Optional existing client

    Returns:
        List of SearchResult objects sorted by similarity
    """
    close_client = client is None
    if client is None:
        client = await get_client()

    try:
        # Build filter conditions
        filter_conditions = []

        if energy_filter:
            filter_conditions.append({
                "key": "energy",
                "match": {"value": energy_filter},
            })

        if emotion_filter:
            filter_conditions.append({
                "key": "primary_emotion",
                "match": {"value": emotion_filter},
            })

        if genre_filter:
            filter_conditions.append({
                "key": "genre",
                "match": {"value": genre_filter},
            })

        query_filter = None
        if filter_conditions:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue

            query_filter = Filter(
                must=[
                    FieldCondition(key=c["key"], match=MatchValue(value=c["match"]["value"]))
                    for c in filter_conditions
                ]
            )

        # Execute search
        from qdrant_client.http.models import SearchRequest

        results = await client.search_batch(
            collection_name=QDRANT_COLLECTION,
            requests=[SearchRequest(
                vector=query_vector,
                limit=limit,
                filter=query_filter,
            )]
        )
        results = results[0] if results else []

        return [
            SearchResult(
                snippet_id=str(r.id),
                score=r.score,
                payload=r.payload or {},
            )
            for r in results
        ]

    finally:
        if close_client:
            await client.close()


async def get_collection_info() -> dict[str, Any]:
    """
    Get information about the collection.

    Returns:
        Dictionary with collection stats
    """
    client = await get_client()

    try:
        info = await client.get_collection(collection_name=QDRANT_COLLECTION)
        return {
            "name": QDRANT_COLLECTION,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status.value if info.status else "unknown",
        }
    except Exception as e:
        return {
            "name": QDRANT_COLLECTION,
            "error": str(e),
        }
    finally:
        await client.close()


async def delete_collection() -> bool:
    """
    Delete the collection (use with caution).

    Returns:
        True if deleted successfully
    """
    client = await get_client()

    try:
        await client.delete_collection(collection_name=QDRANT_COLLECTION)
        return True
    except Exception:
        return False
    finally:
        await client.close()
