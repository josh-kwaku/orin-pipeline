"""
Embedding module using BGE-M3.

Runs locally on GPU - no network IO, synchronous operations.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .config import EMBEDDING_DIMENSION, EMBEDDING_MODEL


# Global model instance (lazy loaded)
_model = None


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""

    success: bool
    vector: Optional[np.ndarray]  # Shape: (EMBEDDING_DIMENSION,)
    error: Optional[str] = None


def _get_device() -> str:
    """Determine the best available device."""
    import torch

    if torch.cuda.is_available():
        return "cuda"

    # MPS for Apple Silicon (PyTorch 1.12+)
    try:
        if torch.backends.mps.is_available():
            return "mps"
    except AttributeError:
        pass

    return "cpu"


def _get_model():
    """Lazy load the embedding model."""
    global _model

    if _model is None:
        from sentence_transformers import SentenceTransformer

        device = _get_device()
        _model = SentenceTransformer(EMBEDDING_MODEL, device=device)

    return _model


def get_device_info() -> dict[str, object]:
    """
    Get information about the device being used for embeddings.

    Returns:
        Dictionary with device info
    """
    import torch

    # Check MPS availability safely
    try:
        mps_available = torch.backends.mps.is_available()
    except AttributeError:
        mps_available = False

    info = {
        "device": _get_device(),
        "cuda_available": torch.cuda.is_available(),
        "mps_available": mps_available,
    }

    if torch.cuda.is_available():
        info["cuda_device_name"] = torch.cuda.get_device_name(0)
        info["cuda_memory_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)

    return info


def embed_text(text: str) -> EmbeddingResult:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed (e.g., ai_description)

    Returns:
        EmbeddingResult with vector
    """
    try:
        model = _get_model()

        # Generate embedding with proper truncation via truncate_dim
        # BGE-M3 outputs 1024D, truncate_dim handles reduction to 768D
        # normalize_embeddings=True ensures unit vectors after truncation
        embedding = model.encode(
            text,
            truncate_dim=EMBEDDING_DIMENSION,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return EmbeddingResult(
            success=True,
            vector=np.array(embedding, dtype=np.float32),
        )

    except Exception as e:
        return EmbeddingResult(
            success=False,
            vector=None,
            error=str(e),
        )


def embed_texts(texts: list[str]) -> list[EmbeddingResult]:
    """
    Generate embeddings for multiple texts.

    More efficient than calling embed_text() in a loop
    as it batches the GPU operations.

    Args:
        texts: List of texts to embed

    Returns:
        List of EmbeddingResult in same order as input
    """
    if not texts:
        return []

    try:
        model = _get_model()

        # Batch encode with proper truncation via truncate_dim
        # BGE-M3 outputs 1024D, truncate_dim handles reduction to 768D
        # normalize_embeddings=True ensures unit vectors after truncation
        embeddings = model.encode(
            texts,
            truncate_dim=EMBEDDING_DIMENSION,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,  # Adjust based on GPU memory
        )

        results = []
        for embedding in embeddings:
            results.append(EmbeddingResult(
                success=True,
                vector=np.array(embedding, dtype=np.float32),
            ))

        return results

    except Exception as e:
        # Return error for all texts
        return [
            EmbeddingResult(success=False, vector=None, error=str(e))
            for _ in texts
        ]


def unload_model():
    """
    Unload model from GPU memory.

    Call this when done embedding to free up VRAM for other operations.
    """
    global _model

    if _model is not None:
        del _model
        _model = None

        # Force garbage collection to release GPU memory
        import gc
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
