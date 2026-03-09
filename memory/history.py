from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from database import Database, MessageRow
from llm.base import Message

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Rough chars-per-token estimate
CHARS_PER_TOKEN = 4
# If stored history exceeds this many chars, trigger summarization
SUMMARIZE_THRESHOLD_CHARS = 50_000


class HistoryManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(
        self,
        guild_id: str,
        channel_id: str,
        limit: int = 20,
    ) -> list[Message]:
        rows: list[MessageRow] = await self._db.get_history(guild_id, channel_id, limit)
        messages: list[Message] = []
        for row in rows:
            if row.role == "system":
                # Summary messages - keep as system
                messages.append(Message(role="system", content=row.content))
            elif row.role == "user":
                name_prefix = f"[{row.author_name}] " if row.author_name else ""
                messages.append(Message(role="user", content=f"{name_prefix}{row.content}"))
            else:
                messages.append(Message(role="assistant", content=row.content))
        return messages

    async def save_user(
        self,
        guild_id: str,
        channel_id: str,
        content: str,
        author_name: Optional[str] = None,
    ) -> None:
        await self._db.save_message(guild_id, channel_id, "user", content, author_name)
        await self._maybe_summarize(guild_id, channel_id)

    async def save_assistant(
        self,
        guild_id: str,
        channel_id: str,
        content: str,
    ) -> None:
        await self._db.save_message(guild_id, channel_id, "assistant", content)

    async def _maybe_summarize(self, guild_id: str, channel_id: str) -> None:
        rows = await self._db.get_history(guild_id, channel_id, limit=200)
        total_chars = sum(len(r.content) for r in rows)
        if total_chars > SUMMARIZE_THRESHOLD_CHARS:
            logger.info(
                "History for %s/%s exceeds threshold (%d chars), summarizing",
                guild_id, channel_id, total_chars,
            )
            from memory.summarizer import summarize_history
            await summarize_history(self._db, guild_id, channel_id, rows)

    async def clear(self, guild_id: str, channel_id: str) -> int:
        return await self._db.delete_channel_history(guild_id, channel_id)

    async def delete_recent(
        self, guild_id: str, channel_id: str, count: int
    ) -> int:
        return await self._db.delete_recent_messages(guild_id, channel_id, count)
