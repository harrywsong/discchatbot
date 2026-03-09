from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# If a PDF averages fewer than this many chars per page, treat it as scanned
MIN_CHARS_PER_PAGE = 50

# Send pages in batches to stay within Gemini's image-per-request limit
# and keep token usage reasonable. 5 pages per call is a good balance.
PAGES_PER_BATCH = 5


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
        result = [f"[Page {i}]\n{text}" for i, text in pages if text]
        return "\n\n---PAGE BREAK---\n\n".join(result)

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
    all_page_texts = []

    # Process in batches — each batch = 1 API call
    for batch_start in range(0, len(images), PAGES_PER_BATCH):
        batch = images[batch_start: batch_start + PAGES_PER_BATCH]
        batch_num = batch_start // PAGES_PER_BATCH + 1
        total_batches = (len(images) + PAGES_PER_BATCH - 1) // PAGES_PER_BATCH
        logger.info(
            "OCR batch %d/%d (%d pages) of %s",
            batch_num, total_batches, len(batch), path.name,
        )

        parts = []
        for local_i, img in enumerate(batch):
            page_num = batch_start + local_i + 1
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            parts.append(gtypes.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"))
            parts.append(gtypes.Part.from_text(text=f"[Page {page_num}]"))

        parts.append(gtypes.Part.from_text(
            text=(
                "Extract all text from each of these document pages exactly as it appears. "
                "For each page, start with a header like [Page N] then the extracted text. "
                "Preserve structure, headings, tables, and lists. "
                "Output only the extracted text, nothing else."
            )
        ))

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=[gtypes.Content(role="user", parts=parts)],
        )
        all_page_texts.append(response.text or "")

    logger.info("OCR complete for %s (%d pages, %d API call(s))", path.name, len(images), total_batches)
    return "\n\n---PAGE BREAK---\n\n".join(all_page_texts)
