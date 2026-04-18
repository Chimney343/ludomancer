from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ludomancer.cache.db import get_connection
from ludomancer.cache.repository import GameRepository
from ludomancer.models import GameMetadata, OwnedGame
from ludomancer.services.library_sync import LibrarySyncService


def _sample_games() -> list[OwnedGame]:
    return [
        OwnedGame(
            appid=10,
            name="Counter-Strike",
            playtime_forever_minutes=120,
            playtime_2weeks_minutes=25,
            icon_url=None,
        )
    ]


class _FakeOwnedGamesFetcher:
    def __init__(self, games: list[OwnedGame]) -> None:
        self._games = games
        self.calls = 0
        self.last_steam_id64: str | None = None

    def get_owned_games(self, steam_id64: str) -> list[OwnedGame]:
        self.calls += 1
        self.last_steam_id64 = steam_id64
        return list(self._games)


class _FakeMetadataFetcher:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_metadata(self, appid: int) -> GameMetadata:
        self.calls.append(appid)
        return GameMetadata(
            appid=appid,
            genres=["Action"],
            categories=["Single-player"],
            developers=["Valve"],
            publishers=["Valve"],
            fetched_at=datetime.now(UTC),
        )


class _FakeTagsFetcher:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def get_tags(self, appid: int) -> dict[str, int]:
        self.calls.append(appid)
        return {"Action": 100}


class _FailingMetadataFetcher:
    def get_metadata(self, appid: int) -> GameMetadata:
        raise RuntimeError(f"metadata unavailable for {appid}")


def test_sync_skips_all_stages_when_cache_is_fresh(tmp_path) -> None:
    conn = get_connection(tmp_path / "cache.db")
    try:
        repository = GameRepository(conn)
        repository.upsert_owned_games(_sample_games())
        repository.upsert_metadata(
            GameMetadata(
                appid=10,
                genres=["Action"],
                categories=["Single-player"],
                developers=["Valve"],
                publishers=["Valve"],
                fetched_at=datetime.now(UTC),
            )
        )
        repository.upsert_tags(10, {"Action": 100})

        owned_fetcher = _FakeOwnedGamesFetcher(_sample_games())
        metadata_fetcher = _FakeMetadataFetcher()
        tags_fetcher = _FakeTagsFetcher()
        service = LibrarySyncService(
            repository,
            owned_fetcher,
            metadata_fetcher,
            tags_fetcher,
            "76561198000000000",
        )

        result = service.sync(force=False)

        assert owned_fetcher.calls == 0
        assert metadata_fetcher.calls == []
        assert tags_fetcher.calls == []
        assert result.owned_games_fetched == 0
        assert result.owned_games_skipped == 1
        assert result.owned_games_failed == 0
        assert result.metadata_fetched == 0
        assert result.metadata_skipped == 1
        assert result.metadata_failed == 0
        assert result.tags_fetched == 0
        assert result.tags_skipped == 1
        assert result.tags_failed == 0
    finally:
        conn.close()


def test_sync_force_refresh_fetches_all_stages_even_when_cache_is_fresh(tmp_path) -> None:
    conn = get_connection(tmp_path / "cache.db")
    try:
        repository = GameRepository(conn)
        repository.upsert_owned_games(
            [
                OwnedGame(
                    appid=730,
                    name="Counter-Strike 2",
                    playtime_forever_minutes=300,
                    playtime_2weeks_minutes=60,
                    icon_url=None,
                )
            ]
        )
        repository.upsert_metadata(
            GameMetadata(
                appid=730,
                genres=["Shooter"],
                categories=["Multi-player"],
                developers=["Valve"],
                publishers=["Valve"],
                fetched_at=datetime.now(UTC),
            )
        )
        repository.upsert_tags(730, {"Shooter": 25})

        refreshed_games = [
            OwnedGame(
                appid=730,
                name="Counter-Strike 2",
                playtime_forever_minutes=300,
                playtime_2weeks_minutes=60,
                icon_url=None,
            )
        ]
        owned_fetcher = _FakeOwnedGamesFetcher(refreshed_games)
        metadata_fetcher = _FakeMetadataFetcher()
        tags_fetcher = _FakeTagsFetcher()
        service = LibrarySyncService(
            repository,
            owned_fetcher,
            metadata_fetcher,
            tags_fetcher,
            "76561198000000000",
        )

        result = service.sync(force=True)

        assert owned_fetcher.calls == 1
        assert owned_fetcher.last_steam_id64 == "76561198000000000"
        assert metadata_fetcher.calls == [730]
        assert tags_fetcher.calls == [730]
        assert result.owned_games_fetched == 1
        assert result.owned_games_skipped == 0
        assert result.owned_games_failed == 0
        assert result.metadata_fetched == 1
        assert result.metadata_skipped == 0
        assert result.metadata_failed == 0
        assert result.tags_fetched == 1
        assert result.tags_skipped == 0
        assert result.tags_failed == 0
        assert repository.get_metadata(730) is not None
        assert repository.get_tags(730) == {"Action": 100}
    finally:
        conn.close()


def test_sync_refetches_metadata_and_tags_when_cache_is_stale(tmp_path) -> None:
    conn = get_connection(tmp_path / "cache.db")
    try:
        repository = GameRepository(conn)
        repository.upsert_owned_games(
            [
                OwnedGame(
                    appid=440,
                    name="Team Fortress 2",
                    playtime_forever_minutes=90,
                    playtime_2weeks_minutes=30,
                    icon_url=None,
                )
            ]
        )
        stale_time = datetime.now(UTC) - timedelta(days=31)
        repository.upsert_metadata(
            GameMetadata(
                appid=440,
                genres=["Action"],
                categories=["Multi-player"],
                developers=["Valve"],
                publishers=["Valve"],
                fetched_at=stale_time,
            )
        )
        repository.upsert_tags(440, {"Action": 10})
        conn.execute("UPDATE steamspy_tags SET fetched_at = ? WHERE appid = ?", (stale_time.isoformat(), 440))
        conn.commit()

        owned_fetcher = _FakeOwnedGamesFetcher(
            [
                OwnedGame(
                    appid=440,
                    name="Team Fortress 2",
                    playtime_forever_minutes=90,
                    playtime_2weeks_minutes=30,
                    icon_url=None,
                )
            ]
        )
        metadata_fetcher = _FakeMetadataFetcher()
        tags_fetcher = _FakeTagsFetcher()
        service = LibrarySyncService(
            repository,
            owned_fetcher,
            metadata_fetcher,
            tags_fetcher,
            "76561198000000000",
        )

        result = service.sync(force=False)

        assert owned_fetcher.calls == 0
        assert result.owned_games_fetched == 0
        assert result.owned_games_skipped == 1
        assert result.owned_games_failed == 0
        assert metadata_fetcher.calls == [440]
        assert tags_fetcher.calls == [440]
        assert result.metadata_fetched == 1
        assert result.metadata_skipped == 0
        assert result.metadata_failed == 0
        assert result.tags_fetched == 1
        assert result.tags_skipped == 0
        assert result.tags_failed == 0
        assert repository.get_tags(440) == {"Action": 100}
    finally:
        conn.close()


def test_sync_continues_when_metadata_fetch_fails(tmp_path) -> None:
    conn = get_connection(tmp_path / "cache.db")
    try:
        repository = GameRepository(conn)
        repository.upsert_owned_games(_sample_games())

        owned_fetcher = _FakeOwnedGamesFetcher(_sample_games())
        metadata_fetcher = _FailingMetadataFetcher()
        tags_fetcher = _FakeTagsFetcher()
        service = LibrarySyncService(
            repository,
            owned_fetcher,
            metadata_fetcher,
            tags_fetcher,
            "76561198000000000",
        )

        result = service.sync(force=False)

        assert owned_fetcher.calls == 0
        assert result.owned_games_skipped == 1
        assert result.metadata_failed == 1
        assert result.tags_fetched == 1
        assert result.tags_failed == 0
    finally:
        conn.close()
