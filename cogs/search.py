from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from tools.web_search import search

if TYPE_CHECKING:
    from bot import DiscordBot

logger = logging.getLogger(__name__)


class SearchCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot

    @app_commands.command(name="search", description="Search the web and show raw results")
    @app_commands.describe(
        query="What to search for",
        num_results="Number of results (1-10, default 5)",
    )
    async def search_command(
        self,
        interaction: discord.Interaction,
        query: str,
        num_results: int = 5,
    ) -> None:
        await interaction.response.defer()
        results = await search(query, num_results=num_results)

        if not results:
            await interaction.followup.send("No results found.")
            return

        embed = discord.Embed(
            title=f"Search: {query[:100]}",
            color=discord.Color.blue(),
        )
        for r in results[:5]:
            snippet = r.snippet[:200] + "..." if len(r.snippet) > 200 else r.snippet
            embed.add_field(
                name=r.title[:256] or "Result",
                value=f"{snippet}\n[{r.url}]({r.url})",
                inline=False,
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: "DiscordBot") -> None:
    await bot.add_cog(SearchCog(bot))
