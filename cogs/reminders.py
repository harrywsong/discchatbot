from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands, tasks

if TYPE_CHECKING:
    from bot import DiscordBot

logger = logging.getLogger(__name__)


class RemindersCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self) -> None:
        self.check_reminders.cancel()

    @tasks.loop(seconds=30)
    async def check_reminders(self) -> None:
        try:
            reminders = await self.bot.db.get_due_reminders()
            for reminder in reminders:
                try:
                    channel = self.bot.get_channel(int(reminder.channel_id))
                    if channel:
                        await channel.send(
                            f"<@{reminder.user_id}> ⏰ Reminder: {reminder.message}"
                        )
                    await self.bot.db.mark_reminder_sent(reminder.id)
                except Exception as e:
                    logger.error("Failed to send reminder %d: %s", reminder.id, e)
        except Exception as e:
            logger.error("Reminder check loop failed: %s", e)

    @check_reminders.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: "DiscordBot") -> None:
    await bot.add_cog(RemindersCog(bot))
