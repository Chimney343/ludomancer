from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

from ludomancer.cache.db import ensure_schema
from ludomancer.models import GameMetadata, OwnedGame


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _to_iso8601(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


class GameRepository:
    """Read/write API for all cache tables."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        ensure_schema(self._conn)

    def upsert_owned_games(self, games: list[OwnedGame]) -> None:
        fetched_at = _to_iso8601(_utc_now())
        rows = [
            (
                game.appid,
                game.name,
                game.playtime_forever_minutes,
                game.playtime_2weeks_minutes,
                game.icon_url,
                fetched_at,
            )
            for game in games
        ]

        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO owned_games (
                    appid,
                    name,
                    playtime_forever_minutes,
                    playtime_2weeks_minutes,
                    icon_url,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    name=excluded.name,
                    playtime_forever_minutes=excluded.playtime_forever_minutes,
                    playtime_2weeks_minutes=excluded.playtime_2weeks_minutes,
                    icon_url=excluded.icon_url,
                    fetched_at=excluded.fetched_at
                """,
                rows,
            )

    def upsert_metadata(self, metadata: GameMetadata) -> None:
        fetched_at = _to_iso8601(metadata.fetched_at)
        release_date = metadata.release_date.isoformat() if metadata.release_date else None

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO game_metadata (
                    appid,
                    genres_json,
                    categories_json,
                    release_date,
                    developers_json,
                    publishers_json,
                    header_image_url,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    genres_json=excluded.genres_json,
                    categories_json=excluded.categories_json,
                    release_date=excluded.release_date,
                    developers_json=excluded.developers_json,
                    publishers_json=excluded.publishers_json,
                    header_image_url=excluded.header_image_url,
                    fetched_at=excluded.fetched_at
                """,
                (
                    metadata.appid,
                    json.dumps(metadata.genres),
                    json.dumps(metadata.categories),
                    release_date,
                    json.dumps(metadata.developers),
                    json.dumps(metadata.publishers),
                    metadata.header_image_url,
                    fetched_at,
                ),
            )

    def upsert_tags(self, appid: int, tags: dict[str, int]) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO steamspy_tags (appid, tags_json, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(appid) DO UPDATE SET
                    tags_json=excluded.tags_json,
                    fetched_at=excluded.fetched_at
                """,
                (appid, json.dumps(tags), _to_iso8601(_utc_now())),
            )

    def get_owned_games(self) -> list[OwnedGame]:
        rows = self._conn.execute(
            """
            SELECT appid, name, playtime_forever_minutes, playtime_2weeks_minutes, icon_url
            FROM owned_games
            ORDER BY name COLLATE NOCASE ASC
            """
        ).fetchall()
        return [OwnedGame.model_validate(dict(row)) for row in rows]

    def get_metadata(self, appid: int) -> GameMetadata | None:
        row = self._conn.execute(
            """
            SELECT appid, genres_json, categories_json, release_date,
                   developers_json, publishers_json, header_image_url, fetched_at
            FROM game_metadata
            WHERE appid = ?
            """,
            (appid,),
        ).fetchone()
        if row is None:
            return None

        return self._metadata_from_row(row)

    def get_all_metadata(self) -> list[GameMetadata]:
        rows = self._conn.execute(
            """
            SELECT appid, genres_json, categories_json, release_date,
                   developers_json, publishers_json, header_image_url, fetched_at
            FROM game_metadata
            """
        ).fetchall()
        return [self._metadata_from_row(row) for row in rows]

    def owned_fetched_at(self) -> datetime | None:
        row = self._conn.execute("SELECT MAX(fetched_at) AS fetched_at FROM owned_games").fetchone()
        if row is None:
            return None
        return _from_iso8601(row["fetched_at"])

    def metadata_fetched_at(self, appid: int) -> datetime | None:
        row = self._conn.execute(
            "SELECT fetched_at FROM game_metadata WHERE appid = ?",
            (appid,),
        ).fetchone()
        if row is None:
            return None
        return _from_iso8601(row["fetched_at"])

    def tags_fetched_at(self, appid: int) -> datetime | None:
        row = self._conn.execute(
            "SELECT fetched_at FROM steamspy_tags WHERE appid = ?",
            (appid,),
        ).fetchone()
        if row is None:
            return None
        return _from_iso8601(row["fetched_at"])

    def get_tags(self, appid: int) -> dict[str, int]:
        row = self._conn.execute(
            "SELECT tags_json FROM steamspy_tags WHERE appid = ?",
            (appid,),
        ).fetchone()
        if row is None:
            return {}

        parsed = json.loads(row["tags_json"])
        if not isinstance(parsed, dict):
            return {}

        tags: dict[str, int] = {}
        for raw_name, raw_votes in parsed.items():
            if not isinstance(raw_name, str):
                continue
            try:
                tags[raw_name] = int(raw_votes)
            except (TypeError, ValueError):
                continue
        return tags

    def _metadata_from_row(self, row: sqlite3.Row) -> GameMetadata:
        release_date = date.fromisoformat(row["release_date"]) if row["release_date"] else None
        fetched_at = _from_iso8601(row["fetched_at"]) or _utc_now()

        return GameMetadata(
            appid=row["appid"],
            genres=json.loads(row["genres_json"]),
            categories=json.loads(row["categories_json"]),
            release_date=release_date,
            developers=json.loads(row["developers_json"]),
            publishers=json.loads(row["publishers_json"]),
            header_image_url=row["header_image_url"],
            fetched_at=fetched_at,
        )
