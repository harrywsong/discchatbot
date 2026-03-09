from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


async def parse(path: Path, groq_api_key: Optional[str] = None) -> str:
    """Transcribe audio using Groq Whisper."""
    if not groq_api_key:
        return "[Audio transcription unavailable: GROQ_API_KEY not set]"

    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=groq_api_key)
        with open(path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                file=(path.name, f),
                model="whisper-large-v3",
            )
        return transcription.text
    except Exception as e:
        logger.error("Audio transcription failed: %s", e)
        return f"[Audio transcription failed: {e}]"
