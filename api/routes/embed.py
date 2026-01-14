"""
Embedding endpoint for external services.

Exposes BGE-M3 embeddings to the chat API.
"""

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.embedder import embed_text

router = APIRouter()
logger = logging.getLogger(__name__)


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[float]


@router.post("/embed", response_model=EmbedResponse)
async def create_embedding(request: EmbedRequest):
    """
    Generate an embedding for the given text.

    Used by orin-chat-api to embed context descriptions
    before querying Qdrant.
    """
    text = request.text.strip()

    if not text:
        logger.warning("Embed request with empty text")
        raise HTTPException(status_code=400, detail="text cannot be empty")

    # Truncate for logging (avoid flooding logs with long text)
    text_preview = text[:100] + "..." if len(text) > 100 else text
    logger.info(f"Embed request: {len(text)} chars - \"{text_preview}\"")

    start_time = time.perf_counter()
    result = embed_text(text)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if not result.success:
        logger.error(f"Embed failed after {elapsed_ms:.0f}ms: {result.error}")
        raise HTTPException(status_code=500, detail=result.error or "Embedding failed")

    logger.info(f"Embed success: {elapsed_ms:.0f}ms, {len(result.vector)} dimensions")
    return EmbedResponse(embedding=result.vector.tolist())
