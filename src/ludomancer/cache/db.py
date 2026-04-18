from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_APPLICATION_TABLES = (
    "owned_games",
    "game_metadata",
    "steamspy_tags",
    "llm_responses",
)


def get_connection(path: Path) -> sqlite3.Connection:
    """Create a SQLite connection configured for desktop-app workloads."""

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create or rebuild schema if the version differs from SCHEMA_VERSION."""

    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")

    version_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    current_version = int(version_row["version"]) if version_row else None

    if current_version == SCHEMA_VERSION:
        return

    _rebuild_schema(conn)


def _rebuild_schema(conn: sqlite3.Connection) -> None:
    for table_name in _APPLICATION_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")

    conn.execute(
        """
        CREATE TABLE owned_games (
            appid INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            playtime_forever_minutes INTEGER NOT NULL,
            playtime_2weeks_minutes INTEGER NOT NULL DEFAULT 0,
            icon_url TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE game_metadata (
            appid INTEGER PRIMARY KEY,
            genres_json TEXT NOT NULL,
            categories_json TEXT NOT NULL,
            release_date TEXT,
            developers_json TEXT NOT NULL,
            publishers_json TEXT NOT NULL,
            header_image_url TEXT,
            fetched_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE steamspy_tags (
            appid INTEGER PRIMARY KEY,
            tags_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE llm_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute("DELETE FROM schema_version")
    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
