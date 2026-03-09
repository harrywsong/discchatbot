from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# BAAI/bge-small-en-v1.5: ~130MB on disk, ~150-200MB RAM, 384 dimensions
# Good quality for semantic search, fast CPU inference via ONNX
EMBED_MODEL = "BAAI/bge-small-en-v1.5"

_model = None


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model %s (first-time download may take a moment)...", EMBED_MODEL)
        from fastembed import TextEmbedding
        _model = TextEmbedding(EMBED_MODEL)
        logger.info("Embedding model loaded")
    return _model


def _embed_sync(text: str) -> bytes:
    model = _get_model()
    vectors = list(model.embed([text]))
    return vectors[0].astype(np.float32).tobytes()


async def embed(text: str) -> bytes:
    """Return embedding as raw bytes for SQLite BLOB storage."""
    return await asyncio.to_thread(_embed_sync, text)


def cosine_similarity(a: bytes, b: bytes) -> float:
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(np.dot(va, vb) / norm)


def is_available() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False
