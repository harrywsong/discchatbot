from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class RateLimitError(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass
class ImageContent:
    data: bytes
    mime_type: str  # e.g. "image/png", "image/jpeg"


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    images: list[ImageContent] = field(default_factory=list)


class LLMProvider(ABC):
    name: str = "base"
    supports_vision: bool = False
    supports_tools: bool = False

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        """Return the assistant's text response."""
        ...

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
        system_prompt: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        """
        Return (final_text, tool_calls_made).
        tool_calls_made is a list of {"name": str, "args": dict, "result": str} dicts.
        Implementations should handle the full tool-call loop internally.
        """
        ...
