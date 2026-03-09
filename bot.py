from __future__ import annotations

import asyncio
import logging
import sys

import discord
from discord.ext import commands

from config import get_settings
from database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

COGS = [
    "cogs.status",
    "cogs.admin",
    "cogs.search",
    "cogs.files",
    "cogs.chat",  # Load chat last so files cog's on_message runs first
]


class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        settings = get_settings()
        intents = discord.Intents.default()
        intents.message_content = True  # Required for reading message text

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.settings = settings
        self.db: Database = Database(settings.db_path)

    async def setup_hook(self) -> None:
        await self.db.connect()
        logger.info("Database initialized")

        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception as e:
                logger.error("Failed to load cog %s: %s", cog, e, exc_info=True)

        # Sync slash commands to the configured guild for instant availability
        if self.settings.guild_id:
            guild = discord.Object(id=int(self.settings.guild_id))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d slash commands to guild %s", len(synced), self.settings.guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d slash commands globally", len(synced))

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="@mentions | /chat",
            )
        )

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        logger.error("Slash command error: %s", error, exc_info=True)
        msg = f"An error occurred: {error}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def main() -> None:
    settings = get_settings()
    bot = DiscordBot()
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
