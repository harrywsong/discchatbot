from __future__ import annotations

import logging
from pathlib import Path

import aiohttp
import discord

from config import get_settings

logger = logging.getLogger(__name__)


async def download_attachment(
    attachment: discord.Attachment,
    guild_id: str,
    channel_id: str,
) -> Path:
    settings = get_settings()
    max_size = settings.max_file_size_bytes

    if attachment.size > max_size:
        raise ValueError(
            f"File '{attachment.filename}' is {attachment.size / 1_048_576:.1f} MB, "
            f"exceeds the {settings.max_file_size_mb} MB limit."
        )

    dest_dir = settings.temp_path / guild_id / channel_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / attachment.filename

    async with aiohttp.ClientSession() as session:
        async with session.get(attachment.url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(65536):
                    f.write(chunk)

    logger.info("Downloaded %s (%d bytes) to %s", attachment.filename, attachment.size, dest)
    return dest
