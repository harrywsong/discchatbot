from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import get_settings
from llm.base import ImageContent, Message
from llm.router import get_router
from memory.history import HistoryManager
from tools.calculator import make_calculator_tool
from tools.code_runner import make_code_runner_tool
from tools.discord_tools import make_discord_tools
from tools.file_reader import make_file_reader_tool, make_web_search_tool
from tools.reminder_tool import make_reminder_tool
from tools.time_tool import make_time_tool
from tools.url_fetcher import make_url_fetcher_tool
from tools.weather import make_weather_tool

if TYPE_CHECKING:
    from bot import DiscordBot

logger = logging.getLogger(__name__)

MAX_DISCORD_MSG = 1990  # Leave room for formatting


def _chunk_message(text: str) -> list[str]:
    """Split a long message into Discord-safe chunks."""
    if len(text) <= MAX_DISCORD_MSG:
        return [text]
    chunks = []
    while text:
        if len(text) <= MAX_DISCORD_MSG:
            chunks.append(text)
            break
        # Try to break at a newline
        split_at = text.rfind("\n", 0, MAX_DISCORD_MSG)
        if split_at <= 0:
            split_at = MAX_DISCORD_MSG
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def _build_system_prompt(
    channel_name: str,
    files_summary: str,
    custom_prompt: Optional[str],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"You are a helpful AI assistant in a Discord server. "
        f"Current date/time: {now}. Channel: #{channel_name}.",
        "",
        "Be concise and conversational. Use markdown formatting when helpful.",
        "You can mention users with <@user_id> syntax — use get_user_info first to find their ID.",
        "",
        "You have tools available. Use them proactively when relevant:",
        "- `web_search`: Current/live info — news, prices, recent events, anything post-training.",
        "- `get_weather`: Weather for any location.",
        "- `calculate`: Any math. Always use this instead of computing mentally.",
        "- `get_current_time`: Current time in any timezone.",
        "- `fetch_webpage`: Read the content of any URL the user shares.",
        "- `run_python`: Execute Python for complex logic, data processing, or algorithms.",
        "- `get_server_info`: Discord server stats.",
        "- `get_user_info`: Look up a user by name or ID; also use before mentioning someone.",
        "- `set_reminder`: Remind the user about something after a delay.",
        "- `read_file`: Read an uploaded/indexed file in this channel.",
        "When you use web_search, cite your sources.",
    ]
    if files_summary and files_summary != "No files indexed in this channel.":
        parts += ["", "Files available in this channel:", files_summary]
    if custom_prompt:
        parts += ["", "Additional instructions:", custom_prompt]
    return "\n".join(parts)


class ChatCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot
        self.history = HistoryManager(bot.db)
        self.settings = get_settings()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore bots and DMs
        if message.author.bot:
            return
        if not message.guild:
            return

        # Respond when @mentioned or when in a designated bot channel
        bot_mentioned = self.bot.user in message.mentions
        # Strip the mention from the message content
        content = message.content
        if bot_mentioned:
            content = content.replace(f"<@{self.bot.user.id}>", "").replace(
                f"<@!{self.bot.user.id}>", ""
            ).strip()
            if not content and not message.attachments:
                await message.reply("Yes? Ask me anything!")
                return
        else:
            return  # Only respond to mentions (not all messages)

        await self._handle_message(message, content)

    @app_commands.command(name="chat", description="Chat with the AI assistant")
    @app_commands.describe(message="Your message")
    async def chat_command(
        self, interaction: discord.Interaction, message: str
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            response = await self._generate_response(
                guild_id=str(interaction.guild_id),
                channel_id=str(interaction.channel_id),
                channel_name=interaction.channel.name,
                user_id=str(interaction.user.id),
                content=message,
                author_name=interaction.user.display_name,
                images=[],
            )
            for chunk in _chunk_message(response):
                await interaction.followup.send(chunk)
        except Exception as e:
            logger.error("Chat command error: %s", e, exc_info=True)
            await interaction.followup.send(f"Error: {e}")

    async def _handle_message(
        self, message: discord.Message, content: str
    ) -> None:
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        channel_name = message.channel.name

        # Collect images from attachments
        images: list[ImageContent] = []
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext)
                   for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(attachment.url) as resp:
                            data = await resp.read()
                    import mimetypes
                    mime, _ = mimetypes.guess_type(attachment.filename)
                    images.append(ImageContent(data=data, mime_type=mime or "image/png"))
                except Exception as e:
                    logger.warning("Failed to download image attachment: %s", e)

        if not content and not images:
            return

        async with message.channel.typing():
            try:
                response = await self._generate_response(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    user_id=str(message.author.id),
                    content=content,
                    author_name=message.author.display_name,
                    images=images,
                )
            except Exception as e:
                logger.error("Chat error: %s", e, exc_info=True)
                response = f"Sorry, I encountered an error: {e}"

        chunks = _chunk_message(response)
        for i, chunk in enumerate(chunks):
            if i == 0:
                await message.reply(chunk)
            else:
                await message.channel.send(chunk)

    async def _generate_response(
        self,
        guild_id: str,
        channel_id: str,
        channel_name: str,
        user_id: str,
        content: str,
        author_name: str,
        images: list[ImageContent],
    ) -> str:
        # Load channel settings and history
        ch_settings = await self.bot.db.get_channel_settings(guild_id, channel_id)
        files_summary = await self.bot.db.get_all_files_summary(guild_id, channel_id)
        system_prompt = _build_system_prompt(channel_name, files_summary, ch_settings.system_prompt)

        history = await self.history.load(guild_id, channel_id, limit=ch_settings.history_limit)

        # Save user message to history
        await self.history.save_user(guild_id, channel_id, content, author_name)

        # Build current user message (with images if any)
        current_msg = Message(role="user", content=content, images=images)
        messages = history + [current_msg]

        # Build tools
        tools = [
            make_web_search_tool(),
            make_file_reader_tool(self.bot.db, guild_id, channel_id),
            make_weather_tool(),
            make_calculator_tool(),
            make_time_tool(),
            make_url_fetcher_tool(),
            make_code_runner_tool(),
            make_reminder_tool(self.bot.db, channel_id, user_id),
            *make_discord_tools(self.bot, guild_id),
        ]

        router = get_router()
        need_vision = bool(images)

        response, _ = await router.complete_with_tools(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            need_vision=need_vision,
        )

        # Save assistant response
        await self.history.save_assistant(guild_id, channel_id, response)
        return response


async def setup(bot: "DiscordBot") -> None:
    await bot.add_cog(ChatCog(bot))
