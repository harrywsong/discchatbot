from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from llm.router import get_router

if TYPE_CHECKING:
    from bot import DiscordBot


class StatusCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency and uptime")
    async def ping_command(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        router = get_router()
        uptime_s = int(router.uptime_seconds)
        h, remainder = divmod(uptime_s, 3600)
        m, s = divmod(remainder, 60)
        uptime_str = f"{h}h {m}m {s}s"
        await interaction.response.send_message(
            f"Pong! Latency: **{latency_ms}ms** | Uptime: **{uptime_str}**",
            ephemeral=True,
        )

    @app_commands.command(name="status", description="Show bot and LLM provider status")
    async def status_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        router = get_router()
        llm_status = router.status()
        db_stats = await self.bot.db.get_db_stats()

        embed = discord.Embed(title="Bot Status", color=discord.Color.green())
        embed.add_field(name="Active LLM", value=llm_status["active"], inline=True)
        embed.add_field(
            name="Gemini",
            value="Available" if llm_status["gemini_available"] else "Rate limited",
            inline=True,
        )
        embed.add_field(
            name="Groq",
            value="Available" if llm_status["groq_available"] else "Unavailable/Rate limited",
            inline=True,
        )
        embed.add_field(name="Messages in DB", value=str(db_stats["messages"]), inline=True)
        embed.add_field(name="Indexed Files", value=str(db_stats["files"]), inline=True)
        embed.add_field(name="DB Size", value=f"{db_stats['size_kb']} KB", inline=True)

        uptime_s = int(llm_status["uptime_seconds"])
        h, remainder = divmod(uptime_s, 3600)
        m, s = divmod(remainder, 60)
        embed.set_footer(text=f"Uptime: {h}h {m}m {s}s")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: "DiscordBot") -> None:
    await bot.add_cog(StatusCog(bot))
