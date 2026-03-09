from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from database import Database

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_QUERY = 5


def _keyword_score(chunk_text: str, query: str) -> int:
    query_words = query.lower().split()
    text_lower = chunk_text.lower()
    return sum(1 for word in query_words if word in text_lower)


async def _semantic_ranked(chunks, query: str):
    try:
        from tools.embedder import cosine_similarity, embed
        query_vec = await embed(query)
        scored = sorted(
            [(c, cosine_similarity(query_vec, c.embedding) if c.embedding else 0.0) for c in chunks],
            key=lambda x: x[1],
            reverse=True,
        )
        top = [c for c, _ in scored[:MAX_CHUNKS_PER_QUERY]]
        top.sort(key=lambda c: c.chunk_index)
        return top
    except Exception as e:
        logger.warning("Semantic search failed, falling back to keywords: %s", e)
        return _keyword_ranked(chunks, query)


def _keyword_ranked(chunks, query: str):
    scored = sorted(
        [(c, _keyword_score(c.content_text or "", query)) for c in chunks],
        key=lambda x: x[1],
        reverse=True,
    )
    top = [c for c, _ in scored[:MAX_CHUNKS_PER_QUERY]]
    top.sort(key=lambda c: c.chunk_index)
    return top


async def read_file(
    db: "Database",
    guild_id: str,
    channel_id: str,
    filename: str,
    query: Optional[str] = None,
) -> str:
    chunks = await db.get_file_chunks(guild_id, channel_id, filename)
    if not chunks:
        all_files = await db.get_channel_files(guild_id, channel_id)
        available = [f["filename"] for f in all_files]
        if available:
            return f"File '{filename}' not found. Available files: {', '.join(available)}"
        return f"File '{filename}' not found. No files are indexed in this channel."

    if len(chunks) == 1:
        return chunks[0].content_text or "[Image file - no text content]"

    if not query:
        top_chunks = chunks[:MAX_CHUNKS_PER_QUERY]
    elif any(c.embedding for c in chunks):
        top_chunks = await _semantic_ranked(chunks, query)
    else:
        # Old chunks indexed before embeddings were added — keyword fallback
        top_chunks = _keyword_ranked(chunks, query)

    total = chunks[0].chunk_total
    result_parts = [f"[{filename} - showing {len(top_chunks)}/{total} chunk(s)]\n"]
    for chunk in top_chunks:
        result_parts.append(
            f"\n--- Chunk {chunk.chunk_index + 1}/{total} ---\n{chunk.content_text}"
        )
    return "\n".join(result_parts)


def make_file_reader_tool(db: "Database", guild_id: str, channel_id: str) -> dict:
    async def _fn(filename: str, query: Optional[str] = None) -> str:
        return await read_file(db, guild_id, channel_id, filename, query)

    return {"name": "read_file", "fn": _fn}


def make_web_search_tool() -> dict:
    from tools.web_search import tool_web_search
    return {"name": "web_search", "fn": tool_web_search}
