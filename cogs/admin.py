from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import ChannelSettings
from memory.history import HistoryManager

if TYPE_CHECKING:
    from bot import DiscordBot

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot
        self.history = HistoryManager(bot.db)

    @app_commands.command(
        name="clear", description="Clear the bot's conversation memory for this channel"
    )
    @app_commands.describe(count="Clear only the last N messages (omit for all)")
    async def clear_command(
        self, interaction: discord.Interaction, count: Optional[int] = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        if count:
            deleted = await self.history.delete_recent(guild_id, channel_id, count * 2)
            await interaction.followup.send(
                f"Cleared the last ~{count} exchange(s) from memory.", ephemeral=True
            )
        else:
            await self.history.clear(guild_id, channel_id)
            await interaction.followup.send("Cleared all conversation memory for this channel.", ephemeral=True)

    @app_commands.command(name="history", description="View recent conversation history")
    async def history_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        rows = await self.bot.db.get_history(guild_id, channel_id, limit=10)
        if not rows:
            await interaction.followup.send("No conversation history found.", ephemeral=True)
            return

        embed = discord.Embed(title="Recent Conversation History", color=discord.Color.greyple())
        for row in rows[-10:]:
            label = f"[{row.role.upper()}]"
            if row.author_name:
                label += f" {row.author_name}"
            content = row.content[:200] + "..." if len(row.content) > 200 else row.content
            embed.add_field(name=label, value=content or "(empty)", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Settings subgroup ──────────────────────────────────────────────────────

    settings_group = app_commands.Group(
        name="settings", description="Configure bot settings for this channel"
    )

    @settings_group.command(
        name="system_prompt",
        description="Set a custom system prompt for this channel",
    )
    @app_commands.describe(prompt="The system prompt text (leave empty to clear)")
    async def set_system_prompt(
        self, interaction: discord.Interaction, prompt: Optional[str] = None
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        ch_settings = await self.bot.db.get_channel_settings(guild_id, channel_id)
        ch_settings.system_prompt = prompt or None
        await self.bot.db.upsert_channel_settings(ch_settings)

        if prompt:
            await interaction.followup.send(
                f"System prompt set:\n```\n{prompt[:500]}\n```", ephemeral=True
            )
        else:
            await interaction.followup.send("System prompt cleared.", ephemeral=True)

    @settings_group.command(
        name="history_limit",
        description="Set how many messages to include in conversation context",
    )
    @app_commands.describe(limit="Number of messages (5-100)")
    async def set_history_limit(
        self, interaction: discord.Interaction, limit: int
    ) -> None:
        limit = max(5, min(100, limit))
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        ch_settings = await self.bot.db.get_channel_settings(guild_id, channel_id)
        ch_settings.history_limit = limit
        await self.bot.db.upsert_channel_settings(ch_settings)
        await interaction.followup.send(
            f"History limit set to {limit} messages.", ephemeral=True
        )

    @settings_group.command(
        name="view",
        description="View current settings for this channel",
    )
    async def view_settings(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)

        ch_settings = await self.bot.db.get_channel_settings(guild_id, channel_id)
        embed = discord.Embed(title="Channel Settings", color=discord.Color.gold())
        embed.add_field(name="History Limit", value=str(ch_settings.history_limit), inline=True)
        embed.add_field(name="File Upload Mode", value="On" if ch_settings.file_upload_mode else "Off", inline=True)
        embed.add_field(
            name="System Prompt",
            value=ch_settings.system_prompt[:200] if ch_settings.system_prompt else "None",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: "DiscordBot") -> None:
    cog = AdminCog(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.settings_group)
