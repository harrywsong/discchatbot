from __future__ import annotations

from pathlib import Path


def parse(path: Path) -> dict:
    """Return image bytes for direct use with vision-capable LLMs."""
    import mimetypes
    data = path.read_bytes()
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png"
    return {"type": "image", "bytes": data, "mime_type": mime_type}
