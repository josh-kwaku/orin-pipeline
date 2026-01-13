"""
Search/recommendation endpoints.
"""

from fastapi import APIRouter, HTTPException

from ..schemas.search import SearchRequest, SearchResponse, SearchResultItem
from src.embedder import embed_text
from src.indexer import search_snippets

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Search for similar song snippets using semantic search.

    The query text is embedded and compared against indexed snippets.
    """
    # Embed the query
    embed_result = embed_text(request.query)

    if not embed_result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to embed query: {embed_result.error}",
        )

    # Search Qdrant
    try:
        results = await search_snippets(
            query_vector=embed_result.vector.tolist(),
            limit=request.limit,
            genre_filter=request.genre,
            emotion_filter=request.emotion,
            energy_filter=request.energy,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )

    # Transform results
    items = [
        SearchResultItem(
            snippet_id=r.snippet_id,
            score=r.score,
            song_title=r.payload.get("song_title", ""),
            artist=r.payload.get("artist", ""),
            album=r.payload.get("album"),
            lyrics=r.payload.get("lyrics", ""),
            ai_description=r.payload.get("ai_description", ""),
            snippet_url=r.payload.get("snippet_url", ""),
            start_time=r.payload.get("start_time", 0),
            end_time=r.payload.get("end_time", 0),
            primary_emotion=r.payload.get("primary_emotion", ""),
            secondary_emotion=r.payload.get("secondary_emotion"),
            energy=r.payload.get("energy", ""),
            genre=r.payload.get("genre", ""),
        )
        for r in results
    ]

    return SearchResponse(
        query=request.query,
        results=items,
        total=len(items),
    )
