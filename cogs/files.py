from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from config import get_settings
from file_processing import chunker, downloader, extractor

if TYPE_CHECKING:
    from bot import DiscordBot

logger = logging.getLogger(__name__)


class FilesCog(commands.Cog):
    def __init__(self, bot: "DiscordBot") -> None:
        self.bot = bot
        self.settings = get_settings()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if not message.attachments:
            return

        # Only auto-index in designated channels
        channel_id = message.channel.id
        if channel_id not in self.settings.file_upload_channel_ids:
            return

        await self._index_attachments(message)

    async def _index_one(
        self, attachment: discord.Attachment, guild_id: str, channel_id: str
    ) -> str:
        path = await downloader.download_attachment(attachment, guild_id, channel_id)
        extracted = await extractor.extract(
            path,
            groq_api_key=self.settings.groq_api_key,
            gemini_api_key=self.settings.gemini_api_key,
            gemini_model=self.settings.gemini_model,
        )
        if extracted.error:
            return f"- `{attachment.filename}`: Error - {extracted.error}"

        await self.bot.db.delete_file(guild_id, channel_id, attachment.filename)

        if extracted.is_image:
            await self.bot.db.insert_file_chunk(
                guild_id=guild_id, channel_id=channel_id,
                filename=attachment.filename, file_type=extracted.file_type,
                chunk_index=0, chunk_total=1,
                content_text="[Image file - analyzed via vision when referenced]",
                is_image=True,
            )
            return f"- `{attachment.filename}`: Indexed as image (vision-ready)"

        if extracted.text:
            return await self._store_text_chunks(attachment, guild_id, channel_id, extracted)

        return f"- `{attachment.filename}`: No content extracted"

    async def _store_text_chunks(self, attachment, guild_id, channel_id, extracted) -> str:
        from tools.embedder import embed, is_available
        chunks = chunker.chunk_text(extracted.text)
        use_embeddings = is_available()
        for i, chunk_text in enumerate(chunks):
            embedding = await embed(chunk_text) if use_embeddings else None
            await self.bot.db.insert_file_chunk(
                guild_id=guild_id, channel_id=channel_id,
                filename=attachment.filename, file_type=extracted.file_type,
                chunk_index=i, chunk_total=len(chunks),
                content_text=chunk_text, is_image=False, embedding=embedding,
            )
        return (
            f"- `{attachment.filename}`: Indexed ({len(chunks)} chunk(s), "
            f"~{len(extracted.text):,} chars)"
        )

    async def _index_attachments(
        self,
        message: discord.Message,
        reply_target: discord.Message | discord.Interaction | None = None,
    ) -> None:
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        results = []

        for attachment in message.attachments:
            try:
                results.append(await self._index_one(attachment, guild_id, channel_id))
            except ValueError as e:
                results.append(f"- `{attachment.filename}`: {e}")
            except Exception as e:
                logger.error("Failed to index %s: %s", attachment.filename, e, exc_info=True)
                results.append(f"- `{attachment.filename}`: Unexpected error - {e}")

        if results:
            summary = "**File indexing results:**\n" + "\n".join(results)
            if isinstance(reply_target, discord.Interaction):
                await reply_target.followup.send(summary)
            else:
                await message.reply(summary)

    # ── Slash commands ─────────────────────────────────────────────────────────

    files_group = app_commands.Group(name="files", description="Manage indexed files")

    @files_group.command(name="upload", description="Upload and index files in this channel")
    async def files_upload(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Please upload your file(s) as an attachment in this channel. "
            "I'll index them automatically if this is a file upload channel, "
            "or use `/files index` after uploading.",
            ephemeral=True,
        )

    @files_group.command(name="list", description="List all indexed files in this channel")
    async def files_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)
        files = await self.bot.db.get_channel_files(guild_id, channel_id)

        if not files:
            await interaction.followup.send("No files indexed in this channel.", ephemeral=True)
            return

        lines = ["**Indexed files in this channel:**"]
        for f in files:
            lines.append(
                f"- `{f['filename']}` ({f['file_type']}, {f['chunks']} chunk(s)) "
                f"— uploaded {f['uploaded_at'][:10]}"
            )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @files_group.command(name="clear", description="Remove an indexed file from this channel")
    @app_commands.describe(filename="The filename to remove")
    async def files_clear(self, interaction: discord.Interaction, filename: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        channel_id = str(interaction.channel_id)
        count = await self.bot.db.delete_file(guild_id, channel_id, filename)
        if count:
            await interaction.followup.send(
                f"Removed `{filename}` ({count} chunk(s) deleted).", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"File `{filename}` not found in this channel.", ephemeral=True
            )

    @files_group.command(name="index", description="Index the most recently uploaded file in this channel")
    async def files_index(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        # Find the most recent message with attachments in this channel
        async for msg in interaction.channel.history(limit=50):
            if msg.attachments and not msg.author.bot:
                await self._index_attachments(msg, reply_target=interaction)
                return
        await interaction.followup.send("No recent file uploads found in this channel.")


async def setup(bot: "DiscordBot") -> None:
    await bot.add_cog(FilesCog(bot))
