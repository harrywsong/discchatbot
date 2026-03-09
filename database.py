from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    TEXT NOT NULL,
    channel_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    author_name TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_channel
    ON messages(guild_id, channel_id, created_at);

CREATE TABLE IF NOT EXISTS file_index (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    filename     TEXT NOT NULL,
    file_type    TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    chunk_total  INTEGER NOT NULL,
    content_text TEXT,
    embedding    BLOB,
    is_image     BOOLEAN DEFAULT FALSE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_files_channel
    ON file_index(guild_id, channel_id, filename);

CREATE TABLE IF NOT EXISTS channel_settings (
    guild_id          TEXT NOT NULL,
    channel_id        TEXT NOT NULL,
    history_limit     INTEGER DEFAULT 20,
    file_upload_mode  BOOLEAN DEFAULT TRUE,
    system_prompt     TEXT DEFAULT NULL,
    PRIMARY KEY (guild_id, channel_id)
);
"""


@dataclass
class MessageRow:
    id: int
    guild_id: str
    channel_id: str
    role: str
    content: str
    author_name: Optional[str]
    created_at: str


@dataclass
class FileChunkRow:
    id: int
    guild_id: str
    channel_id: str
    filename: str
    file_type: str
    chunk_index: int
    chunk_total: int
    content_text: Optional[str]
    embedding: Optional[bytes]
    is_image: bool
    created_at: str


@dataclass
class ChannelSettings:
    guild_id: str
    channel_id: str
    history_limit: int = 20
    file_upload_mode: bool = True
    system_prompt: Optional[str] = None


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = str(db_path)
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        # Migrate existing DBs that don't have the embedding column yet
        try:
            await self._conn.execute("ALTER TABLE file_index ADD COLUMN embedding BLOB")
            await self._conn.commit()
            logger.info("Migrated file_index: added embedding column")
        except Exception:
            pass  # Column already exists
        logger.info("Database connected: %s", self._path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    # ── Messages ──────────────────────────────────────────────────────────────

    async def save_message(
        self,
        guild_id: str,
        channel_id: str,
        role: str,
        content: str,
        author_name: Optional[str] = None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO messages (guild_id, channel_id, role, content, author_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, channel_id, role, content, author_name),
        )
        await self._conn.commit()

    async def get_history(
        self, guild_id: str, channel_id: str, limit: int = 20
    ) -> list[MessageRow]:
        async with self._conn.execute(
            "SELECT * FROM ("
            "  SELECT * FROM messages WHERE guild_id=? AND channel_id=? "
            "  ORDER BY created_at DESC LIMIT ?"
            ") ORDER BY created_at ASC",
            (guild_id, channel_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [MessageRow(**dict(row)) for row in rows]

    async def delete_channel_history(self, guild_id: str, channel_id: str) -> int:
        async with self._conn.execute(
            "DELETE FROM messages WHERE guild_id=? AND channel_id=?",
            (guild_id, channel_id),
        ) as cursor:
            count = cursor.rowcount
        await self._conn.commit()
        return count

    async def delete_recent_messages(
        self, guild_id: str, channel_id: str, count: int
    ) -> int:
        async with self._conn.execute(
            "DELETE FROM messages WHERE id IN ("
            "  SELECT id FROM messages WHERE guild_id=? AND channel_id=? "
            "  ORDER BY created_at DESC LIMIT ?"
            ")",
            (guild_id, channel_id, count),
        ) as cursor:
            deleted = cursor.rowcount
        await self._conn.commit()
        return deleted

    async def replace_history_with_summary(
        self,
        guild_id: str,
        channel_id: str,
        summary: str,
        keep_recent: int = 10,
    ) -> None:
        async with self._conn.execute(
            "SELECT id FROM messages WHERE guild_id=? AND channel_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (guild_id, channel_id, keep_recent),
        ) as cursor:
            recent_ids = [row[0] for row in await cursor.fetchall()]

        if recent_ids:
            placeholders = ",".join("?" * len(recent_ids))
            await self._conn.execute(
                f"DELETE FROM messages WHERE guild_id=? AND channel_id=? "
                f"AND id NOT IN ({placeholders})",
                (guild_id, channel_id, *recent_ids),
            )
        else:
            await self._conn.execute(
                "DELETE FROM messages WHERE guild_id=? AND channel_id=?",
                (guild_id, channel_id),
            )

        # Insert summary as oldest system message
        await self._conn.execute(
            "INSERT INTO messages (guild_id, channel_id, role, content, author_name, created_at) "
            "VALUES (?, ?, 'system', ?, '[summary]', datetime('now', '-1 second'))",
            (guild_id, channel_id, summary),
        )
        await self._conn.commit()

    # ── File index ────────────────────────────────────────────────────────────

    async def insert_file_chunk(
        self,
        guild_id: str,
        channel_id: str,
        filename: str,
        file_type: str,
        chunk_index: int,
        chunk_total: int,
        content_text: Optional[str] = None,
        is_image: bool = False,
        embedding: Optional[bytes] = None,
    ) -> None:
        await self._conn.execute(
            "INSERT INTO file_index "
            "(guild_id, channel_id, filename, file_type, chunk_index, chunk_total, "
            " content_text, is_image, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, filename, file_type, chunk_index, chunk_total,
             content_text, is_image, embedding),
        )
        await self._conn.commit()

    async def get_file_chunks(
        self, guild_id: str, channel_id: str, filename: str
    ) -> list[FileChunkRow]:
        async with self._conn.execute(
            "SELECT * FROM file_index WHERE guild_id=? AND channel_id=? AND filename=? "
            "ORDER BY chunk_index ASC",
            (guild_id, channel_id, filename),
        ) as cursor:
            rows = await cursor.fetchall()
        return [FileChunkRow(**dict(row)) for row in rows]

    async def get_channel_files(
        self, guild_id: str, channel_id: str
    ) -> list[dict]:
        async with self._conn.execute(
            "SELECT filename, file_type, MAX(chunk_total) as chunks, MIN(created_at) as uploaded_at "
            "FROM file_index WHERE guild_id=? AND channel_id=? "
            "GROUP BY filename, file_type ORDER BY uploaded_at DESC",
            (guild_id, channel_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_file(self, guild_id: str, channel_id: str, filename: str) -> int:
        async with self._conn.execute(
            "DELETE FROM file_index WHERE guild_id=? AND channel_id=? AND filename=?",
            (guild_id, channel_id, filename),
        ) as cursor:
            count = cursor.rowcount
        await self._conn.commit()
        return count

    async def get_all_files_summary(self, guild_id: str, channel_id: str) -> str:
        files = await self.get_channel_files(guild_id, channel_id)
        if not files:
            return "No files indexed in this channel."
        lines = [f"- {f['filename']} ({f['file_type']}, {f['chunks']} chunk(s))" for f in files]
        return "\n".join(lines)

    async def get_db_stats(self) -> dict:
        async with self._conn.execute("SELECT COUNT(*) FROM messages") as c:
            msg_count = (await c.fetchone())[0]
        async with self._conn.execute("SELECT COUNT(DISTINCT filename) FROM file_index") as c:
            file_count = (await c.fetchone())[0]
        import os
        size_bytes = os.path.getsize(self._path)
        return {
            "messages": msg_count,
            "files": file_count,
            "size_kb": round(size_bytes / 1024, 1),
        }

    # ── Channel settings ──────────────────────────────────────────────────────

    async def get_channel_settings(
        self, guild_id: str, channel_id: str
    ) -> ChannelSettings:
        async with self._conn.execute(
            "SELECT * FROM channel_settings WHERE guild_id=? AND channel_id=?",
            (guild_id, channel_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            return ChannelSettings(**dict(row))
        return ChannelSettings(guild_id=guild_id, channel_id=channel_id)

    async def upsert_channel_settings(self, settings: ChannelSettings) -> None:
        await self._conn.execute(
            "INSERT INTO channel_settings "
            "(guild_id, channel_id, history_limit, file_upload_mode, system_prompt) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(guild_id, channel_id) DO UPDATE SET "
            "history_limit=excluded.history_limit, "
            "file_upload_mode=excluded.file_upload_mode, "
            "system_prompt=excluded.system_prompt",
            (settings.guild_id, settings.channel_id, settings.history_limit,
             settings.file_upload_mode, settings.system_prompt),
        )
        await self._conn.commit()
