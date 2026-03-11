from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import Database

logger = logging.getLogger(__name__)


def make_reminder_tool(db: "Database", channel_id: str, user_id: str) -> dict:
    """Create a set_reminder tool bound to the current channel and user."""

    async def set_reminder(message: str, delay_minutes: float) -> str:
        if delay_minutes <= 0:
            return "Delay must be greater than 0 minutes."
        if delay_minutes > 10080:  # 1 week
            return "Maximum reminder delay is 1 week (10080 minutes)."

        due_at = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        await db.add_reminder(
            channel_id=channel_id,
            user_id=user_id,
            message=message,
            due_at=due_at,
        )

        # Human-readable time string
        if delay_minutes < 1:
            time_str = f"{int(delay_minutes * 60)} second(s)"
        elif delay_minutes < 60:
            time_str = f"{int(delay_minutes)} minute(s)"
        elif delay_minutes < 1440:
            hours = delay_minutes / 60
            time_str = f"{hours:.1f} hour(s)"
        else:
            days = delay_minutes / 1440
            time_str = f"{days:.1f} day(s)"

        return f"Reminder set! I'll ping <@{user_id}> in {time_str}: \"{message}\""

    return {"name": "set_reminder", "fn": set_reminder}
