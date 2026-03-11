from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import discord
    from discord.ext import commands

logger = logging.getLogger(__name__)


def make_discord_tools(bot: "commands.Bot", guild_id: str) -> list[dict]:
    """Create Discord-context-aware tools bound to the current guild."""

    async def get_server_info() -> str:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return "Could not access server information."

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = len(guild.roles) - 1  # exclude @everyone
        owner = guild.owner.display_name if guild.owner else "Unknown"

        return (
            f"**Server: {guild.name}**\n"
            f"Members: {guild.member_count}\n"
            f"Text channels: {text_channels} | Voice channels: {voice_channels}\n"
            f"Roles: {roles}\n"
            f"Owner: {owner}\n"
            f"Created: {guild.created_at.strftime('%Y-%m-%d')}"
        )

    async def get_user_info(username_or_id: str) -> str:
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return "Could not access server."

        member = None
        query = username_or_id.strip()

        # By ID (plain number)
        if query.isdigit():
            member = guild.get_member(int(query))

        # By mention format <@123> or <@!123>
        if not member and query.startswith("<@") and query.endswith(">"):
            uid = query.strip("<@!>")
            if uid.isdigit():
                member = guild.get_member(int(uid))

        # Exact display name or username
        if not member:
            q_lower = query.lower()
            for m in guild.members:
                if m.display_name.lower() == q_lower or m.name.lower() == q_lower:
                    member = m
                    break

        # Partial match fallback
        if not member:
            q_lower = query.lower()
            for m in guild.members:
                if q_lower in m.display_name.lower() or q_lower in m.name.lower():
                    member = m
                    break

        if not member:
            return f"Could not find user '{username_or_id}' in this server (they may not be in my cache)."

        roles = [r.name for r in member.roles if r.name != "@everyone"]
        joined = member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown"

        return (
            f"**{member.display_name}** (`{member.name}`)\n"
            f"ID: `{member.id}` | Mention: <@{member.id}>\n"
            f"Bot: {'Yes' if member.bot else 'No'}\n"
            f"Joined server: {joined}\n"
            f"Account created: {member.created_at.strftime('%Y-%m-%d')}\n"
            f"Roles: {', '.join(roles) if roles else 'None'}"
        )

    return [
        {"name": "get_server_info", "fn": get_server_info},
        {"name": "get_user_info", "fn": get_user_info},
    ]
