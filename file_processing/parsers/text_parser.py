from __future__ import annotations

from pathlib import Path


def parse(path: Path) -> str:
    """Parse plain text, CSV, JSON, code files, etc."""
    raw = path.read_bytes()

    # Try to detect encoding
    try:
        import chardet
        detected = chardet.detect(raw)
        encoding = detected.get("encoding") or "utf-8"
    except ImportError:
        encoding = "utf-8"

    try:
        return raw.decode(encoding, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")
