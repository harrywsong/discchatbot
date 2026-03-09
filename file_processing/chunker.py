from __future__ import annotations

# Target chunk size in characters (~1000 tokens at 4 chars/token)
CHUNK_SIZE = 4000
OVERLAP = 200


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to break at a paragraph or sentence boundary
        break_at = text.rfind("\n\n", start, end)
        if break_at == -1 or break_at <= start:
            break_at = text.rfind(". ", start, end)
        if break_at == -1 or break_at <= start:
            break_at = end

        chunks.append(text[start:break_at])
        start = max(start + 1, break_at - OVERLAP)

    return [c for c in chunks if c.strip()]
