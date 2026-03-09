from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required
    discord_token: str
    gemini_api_key: str

    # Optional LLM fallback
    groq_api_key: Optional[str] = None

    # Optional web search
    tavily_api_key: Optional[str] = None

    # Bot behavior
    database_path: str = "data/bot.db"
    max_history_messages: int = 20
    max_file_size_mb: int = 10
    temp_dir: str = "/tmp/discchatbot"

    # Channel IDs where uploads are auto-indexed (empty = disabled)
    file_upload_channels: str = ""

    # LLM model names
    # Free tier options (no billing required), as of March 2026:
    #   gemini-3.1-flash-lite-preview  15 RPM, 500 RPD — best overall for personal use
    #   gemini-2.5-flash                5 RPM,  20 RPD
    #   gemini-2.5-flash-lite          10 RPM,  20 RPD
    gemini_model: str = "gemini-3.1-flash-lite-preview"
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Guild ID for instant slash command sync
    guild_id: Optional[str] = None

    @property
    def file_upload_channel_ids(self) -> set[int]:
        if not self.file_upload_channels.strip():
            return set()
        return {int(cid.strip()) for cid in self.file_upload_channels.split(",") if cid.strip()}

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def db_path(self) -> Path:
        p = Path(self.database_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def temp_path(self) -> Path:
        p = Path(self.temp_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
