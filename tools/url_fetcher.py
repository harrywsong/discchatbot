from __future__ import annotations

import html
import logging
import re
from html.parser import HTMLParser

import aiohttp

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 3000


class _TextExtractor(HTMLParser):
    """Extracts readable text from HTML using the stdlib parser."""

    _SKIP_TAGS = frozenset({"script", "style", "head", "nav", "footer", "aside", "noscript"})

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)


async def fetch_webpage(url: str) -> str:
    """Fetch and extract readable text content from a URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; bot/1.0)",
            "Accept": "text/html,application/xhtml+xml,text/plain",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return f"Could not fetch '{url}' (HTTP {resp.status})."
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "html" not in content_type:
                    return f"URL returned non-text content ({content_type}), cannot extract text."
                raw = await resp.text(errors="replace")

        parser = _TextExtractor()
        parser.feed(raw)
        text = " ".join(parser.text_parts)
        text = re.sub(r"\s+", " ", text).strip()
        text = html.unescape(text)

        if not text:
            return f"No readable text content found at '{url}'."

        if len(text) > MAX_CONTENT_CHARS:
            text = text[:MAX_CONTENT_CHARS] + f"\n\n[Truncated — showing first {MAX_CONTENT_CHARS} chars]"

        return f"**Content from {url}:**\n\n{text}"

    except aiohttp.InvalidURL:
        return f"Invalid URL: '{url}'"
    except Exception as e:
        logger.warning("URL fetch failed for %s: %s", url, e)
        return f"Could not fetch '{url}': {e}"


def make_url_fetcher_tool() -> dict:
    return {"name": "fetch_webpage", "fn": fetch_webpage}
