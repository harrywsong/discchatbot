from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from database import Database, MessageRow
from llm.base import Message
from llm.router import get_router

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = (
    "You are a conversation summarizer. "
    "Produce a concise summary (500 words max) of the conversation below, "
    "preserving key facts, decisions, and any important context that would be "
    "needed to continue the conversation naturally. "
    "Write in third person, e.g. 'The user asked about X. The assistant explained Y.'"
)


async def summarize_history(
    db: Database,
    guild_id: str,
    channel_id: str,
    rows: list[MessageRow],
) -> None:
    if len(rows) < 10:
        return  # Not worth summarizing very short histories

    # Format the conversation for summarization
    lines = []
    for row in rows:
        name = row.author_name or row.role
        lines.append(f"{name}: {row.content}")
    conversation_text = "\n".join(lines)

    router = get_router()
    try:
        summary = await router.complete(
            messages=[
                Message(role="user", content=f"Summarize this conversation:\n\n{conversation_text}")
            ],
            system_prompt=SUMMARY_SYSTEM_PROMPT,
        )
        await db.replace_history_with_summary(
            guild_id, channel_id, f"[Conversation summary]\n{summary}", keep_recent=10
        )
        logger.info("Summarized history for %s/%s", guild_id, channel_id)
    except Exception as e:
        logger.error("Failed to summarize history: %s", e)
