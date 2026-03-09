from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# If a PDF averages fewer than this many chars per page, treat it as scanned
MIN_CHARS_PER_PAGE = 50


async def parse(
    path: Path,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash-lite",
) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        pages.append((i, text))

    total_chars = sum(len(t) for _, t in pages)
    avg_chars_per_page = total_chars / max(len(pages), 1)

    if avg_chars_per_page >= MIN_CHARS_PER_PAGE:
        # Normal text-based PDF
        result = [f"[Page {i}]\n{text}" for i, text in pages if text]
        return "\n\n---PAGE BREAK---\n\n".join(result)

    # Scanned PDF — no usable embedded text
    logger.info(
        "%s looks scanned (%.1f chars/page avg), attempting vision OCR",
        path.name, avg_chars_per_page,
    )

    if not gemini_api_key:
        return (
            f"[Scanned PDF — {len(pages)} page(s), no embedded text. "
            "GEMINI_API_KEY is required to OCR scanned documents.]"
        )

    return await _ocr_with_gemini(path, gemini_api_key, gemini_model, len(pages))


async def _ocr_with_gemini(
    path: Path, api_key: str, model: str, page_count: int
) -> str:
    import google.genai as genai
    import google.genai.types as gtypes

    def _render_pages():
        from pdf2image import convert_from_path
        return convert_from_path(str(path), dpi=150)

    logger.info("Rendering %s to images for OCR (%d pages)...", path.name, page_count)
    images = await asyncio.to_thread(_render_pages)

    client = genai.Client(api_key=api_key)
    page_texts = []

    for i, img in enumerate(images, 1):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        logger.info("OCR page %d/%d of %s", i, len(images), path.name)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=[
                gtypes.Content(role="user", parts=[
                    gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    gtypes.Part.from_text(
                        text="Extract all text from this document page exactly as it appears. "
                             "Preserve structure, headings, tables, and lists. "
                             "Output only the extracted text, nothing else."
                    ),
                ])
            ],
        )
        page_texts.append(f"[Page {i} — OCR]\n{response.text or ''}")

    logger.info("OCR complete for %s (%d pages)", path.name, len(images))
    return "\n\n---PAGE BREAK---\n\n".join(page_texts)
