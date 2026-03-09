from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from llm.base import ImageContent

logger = logging.getLogger(__name__)

IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif",
    "image/webp", "image/bmp", "image/tiff",
}
AUDIO_MIMES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg",
    "audio/flac", "audio/m4a", "audio/webm",
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go",
    ".rs", ".rb", ".php", ".html", ".css", ".sh", ".bash",
    ".log", ".ini", ".toml", ".env",
}


@dataclass
class ExtractedContent:
    filename: str
    file_type: str
    text: Optional[str] = None
    images: list[ImageContent] = field(default_factory=list)
    is_image: bool = False
    error: Optional[str] = None


def _detect_mime(path: Path) -> str:
    # Try python-magic first for accuracy
    try:
        import magic
        return magic.from_file(str(path), mime=True)
    except (ImportError, Exception):
        pass
    # Fall back to extension-based detection
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


async def extract(
    path: Path,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash-lite",
) -> ExtractedContent:
    mime = _detect_mime(path)
    filename = path.name
    logger.info("Extracting %s (MIME: %s)", filename, mime)

    # PDF
    if mime == "application/pdf":
        try:
            from file_processing.parsers import pdf_parser
            text = await pdf_parser.parse(path, gemini_api_key=gemini_api_key, gemini_model=gemini_model)
            return ExtractedContent(filename=filename, file_type="pdf", text=text)
        except Exception as e:
            return ExtractedContent(filename=filename, file_type="pdf", error=str(e))

    # Images
    if mime in IMAGE_MIMES or any(filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
        try:
            from file_processing.parsers import image_parser
            result = image_parser.parse(path)
            img = ImageContent(data=result["bytes"], mime_type=result["mime_type"])
            return ExtractedContent(
                filename=filename,
                file_type="image",
                images=[img],
                is_image=True,
            )
        except Exception as e:
            return ExtractedContent(filename=filename, file_type="image", error=str(e))

    # DOCX
    if mime in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",) \
            or filename.lower().endswith(".docx"):
        try:
            from file_processing.parsers import docx_parser
            text = docx_parser.parse(path)
            return ExtractedContent(filename=filename, file_type="docx", text=text)
        except Exception as e:
            return ExtractedContent(filename=filename, file_type="docx", error=str(e))

    # Audio
    if mime in AUDIO_MIMES or any(filename.lower().endswith(ext) for ext in [".mp3", ".wav", ".ogg", ".flac", ".m4a"]):
        try:
            from file_processing.parsers import audio_parser
            text = await audio_parser.parse(path, groq_api_key=groq_api_key)
            return ExtractedContent(filename=filename, file_type="audio", text=text)
        except Exception as e:
            return ExtractedContent(filename=filename, file_type="audio", error=str(e))

    # Plain text / code / data
    if mime.startswith("text/") or path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            from file_processing.parsers import text_parser
            text = text_parser.parse(path)
            return ExtractedContent(filename=filename, file_type="text", text=text)
        except Exception as e:
            return ExtractedContent(filename=filename, file_type="text", error=str(e))

    return ExtractedContent(
        filename=filename,
        file_type="unknown",
        error=f"Unsupported file type: {mime}",
    )
