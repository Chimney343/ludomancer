from __future__ import annotations

from ludomancer.cache.db import SCHEMA_VERSION, ensure_schema, get_connection

EXPECTED_TABLES = {
    "owned_games",
    "game_metadata",
    "steamspy_tags",
    "llm_responses",
    "schema_version",
}


def test_ensure_schema_creates_expected_tables(tmp_path) -> None:
    db_path = tmp_path / "cache.db"
    conn = get_connection(db_path)
    try:
        ensure_schema(conn)

        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {row["name"] for row in table_rows}
        assert EXPECTED_TABLES.issubset(tables)

        version_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert version_row is not None
        assert version_row["version"] == SCHEMA_VERSION
    finally:
        conn.close()


def test_ensure_schema_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "cache.db"
    conn = get_connection(db_path)
    try:
        ensure_schema(conn)
        ensure_schema(conn)

        version_row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        assert version_row is not None
        assert version_row["version"] == SCHEMA_VERSION
    finally:
        conn.close()
