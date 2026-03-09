from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from database import Database

logger = logging.getLogger(__name__)

# How many chunks to return when querying a file
MAX_CHUNKS_PER_QUERY = 3


def _simple_relevance_score(chunk_text: str, query: str) -> int:
    """Very basic keyword relevance scoring."""
    if not query:
        return 0
    query_words = query.lower().split()
    text_lower = chunk_text.lower()
    return sum(1 for word in query_words if word in text_lower)


async def read_file(
    db: "Database",
    guild_id: str,
    channel_id: str,
    filename: str,
    query: Optional[str] = None,
) -> str:
    chunks = await db.get_file_chunks(guild_id, channel_id, filename)
    if not chunks:
        # Try fuzzy match - find files with similar names
        all_files = await db.get_channel_files(guild_id, channel_id)
        available = [f["filename"] for f in all_files]
        if available:
            return (
                f"File '{filename}' not found. "
                f"Available files: {', '.join(available)}"
            )
        return f"File '{filename}' not found. No files are indexed in this channel."

    if len(chunks) == 1:
        return chunks[0].content_text or "[Image file - no text content]"

    # With a query, score chunks by relevance
    if query:
        scored = sorted(
            [(chunk, _simple_relevance_score(chunk.content_text or "", query)) for chunk in chunks],
            key=lambda x: x[1],
            reverse=True,
        )
        top_chunks = [c for c, _ in scored[:MAX_CHUNKS_PER_QUERY]]
        top_chunks.sort(key=lambda c: c.chunk_index)
    else:
        # Return first N chunks
        top_chunks = chunks[:MAX_CHUNKS_PER_QUERY]

    total = chunks[0].chunk_total
    result_parts = [
        f"[{filename} - showing {len(top_chunks)}/{total} chunk(s)]\n"
    ]
    for chunk in top_chunks:
        result_parts.append(
            f"\n--- Chunk {chunk.chunk_index + 1}/{total} ---\n{chunk.content_text}"
        )

    return "\n".join(result_parts)


def make_file_reader_tool(db: "Database", guild_id: str, channel_id: str) -> dict:
    """Return a tool dict with a bound file reader for the given channel."""
    async def _fn(filename: str, query: Optional[str] = None) -> str:
        return await read_file(db, guild_id, channel_id, filename, query)

    return {
        "name": "read_file",
        "fn": _fn,
    }


def make_web_search_tool() -> dict:
    from tools.web_search import tool_web_search
    return {
        "name": "web_search",
        "fn": tool_web_search,
    }
