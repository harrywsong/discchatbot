from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


async def search(query: str, num_results: int = 5) -> list[SearchResult]:
    """Search the web. Uses DuckDuckGo (free/keyless) with Tavily as fallback."""
    num_results = max(1, min(10, num_results))

    try:
        results = await _ddg_search(query, num_results)
        if results:
            return results
    except Exception as e:
        logger.warning("DDG search failed: %s", e)

    # Fallback to Tavily if configured
    settings = get_settings()
    if settings.tavily_api_key:
        try:
            return await _tavily_search(query, num_results, settings.tavily_api_key)
        except Exception as e:
            logger.warning("Tavily search failed: %s", e)

    return []


async def _ddg_search(query: str, num_results: int) -> list[SearchResult]:
    def _sync_search():
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                ))
        return results

    return await asyncio.to_thread(_sync_search)


async def _tavily_search(query: str, num_results: int, api_key: str) -> list[SearchResult]:
    from tavily import TavilyClient

    def _sync():
        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=num_results)
        results = []
        for r in response.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            ))
        return results

    return await asyncio.to_thread(_sync)


def format_results(results: list[SearchResult]) -> str:
    """Format search results as a string for the LLM."""
    if not results:
        return "No search results found."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. **{r.title}**")
        lines.append(f"   URL: {r.url}")
        lines.append(f"   {r.snippet}")
        lines.append("")
    return "\n".join(lines)


async def search_and_format(query: str, num_results: int = 5) -> str:
    results = await search(query, num_results)
    return format_results(results)


# Tool callable for LLM integration
async def tool_web_search(query: str, num_results: int = 5) -> str:
    return await search_and_format(query, num_results)
