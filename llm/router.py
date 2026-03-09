from __future__ import annotations

import logging
import time
from typing import Optional

from config import get_settings
from .base import LLMError, LLMProvider, Message, RateLimitError
from .gemini import GeminiProvider
from .groq_provider import GroqProvider

logger = logging.getLogger(__name__)

# How long to avoid a provider after it rate-limits us (seconds)
COOLDOWN_SECONDS = 60


class LLMRouter:
    """Selects between Gemini (primary) and Groq (fallback), tracking rate limits."""

    def __init__(self) -> None:
        settings = get_settings()
        self._gemini = GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
        self._groq: Optional[GroqProvider] = None
        if settings.groq_api_key:
            self._groq = GroqProvider(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
            )

        self._rate_limited_until: dict[str, float] = {}
        self._start_time = time.monotonic()

    def _is_available(self, provider: LLMProvider) -> bool:
        until = self._rate_limited_until.get(provider.name, 0)
        return time.monotonic() >= until

    def _mark_rate_limited(self, provider: LLMProvider) -> None:
        self._rate_limited_until[provider.name] = time.monotonic() + COOLDOWN_SECONDS
        logger.warning("%s rate limited - cooling down for %ds", provider.name, COOLDOWN_SECONDS)

    def get_provider(self, need_vision: bool = False) -> LLMProvider:
        """Return the best available provider."""
        if need_vision:
            # Only Gemini supports vision
            if self._is_available(self._gemini):
                return self._gemini
            raise LLMError("Gemini is rate limited and no vision-capable fallback is available.")

        if self._is_available(self._gemini):
            return self._gemini
        if self._groq and self._is_available(self._groq):
            logger.info("Gemini rate limited, falling back to Groq")
            return self._groq
        raise LLMError("All LLM providers are currently rate limited. Please wait and try again.")

    async def complete(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
        need_vision: bool = False,
    ) -> str:
        provider = self.get_provider(need_vision=need_vision)
        try:
            return await provider.complete(messages, system_prompt=system_prompt)
        except RateLimitError:
            self._mark_rate_limited(provider)
            # Try fallback
            if provider.name == "gemini" and self._groq and not need_vision:
                return await self._groq.complete(messages, system_prompt=system_prompt)
            raise

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        need_vision: bool = False,
    ) -> tuple[str, list[dict]]:
        provider = self.get_provider(need_vision=need_vision)
        try:
            return await provider.complete_with_tools(
                messages, tools, system_prompt=system_prompt
            )
        except RateLimitError:
            self._mark_rate_limited(provider)
            if provider.name == "gemini" and self._groq and not need_vision:
                logger.info("Retrying with Groq after Gemini rate limit")
                return await self._groq.complete_with_tools(
                    messages, tools, system_prompt=system_prompt
                )
            raise

    @property
    def active_provider_name(self) -> str:
        try:
            return self.get_provider().name
        except LLMError:
            return "none (all rate limited)"

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    def status(self) -> dict:
        return {
            "active": self.active_provider_name,
            "gemini_available": self._is_available(self._gemini),
            "groq_available": bool(self._groq) and self._is_available(self._groq),
            "uptime_seconds": int(self.uptime_seconds),
        }


# Singleton
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
