from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ludomancer.cache.repository import GameRepository
from ludomancer.cache.ttl import METADATA_TTL, OWNED_GAMES_TTL, TAGS_TTL, is_fresh
from ludomancer.models import GameMetadata, OwnedGame


class OwnedGamesFetcher(Protocol):
    def get_owned_games(self, steam_id64: str) -> list[OwnedGame]:
        ...


class MetadataFetcher(Protocol):
    def get_metadata(self, appid: int) -> GameMetadata:
        ...


class TagsFetcher(Protocol):
    def get_tags(self, appid: int) -> dict[str, int]:
        ...


@dataclass(slots=True)
class SyncResult:
    owned_games_fetched: int = 0
    owned_games_skipped: int = 0
    owned_games_failed: int = 0
    metadata_fetched: int = 0
    metadata_skipped: int = 0
    metadata_failed: int = 0
    tags_fetched: int = 0
    tags_skipped: int = 0
    tags_failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "owned_games_fetched": self.owned_games_fetched,
            "owned_games_skipped": self.owned_games_skipped,
            "owned_games_failed": self.owned_games_failed,
            "metadata_fetched": self.metadata_fetched,
            "metadata_skipped": self.metadata_skipped,
            "metadata_failed": self.metadata_failed,
            "tags_fetched": self.tags_fetched,
            "tags_skipped": self.tags_skipped,
            "tags_failed": self.tags_failed,
        }


class LibrarySyncService:
    """Coordinates cache-aware sync operations for the user's library."""

    def __init__(
        self,
        repository: GameRepository,
        owned_games_fetcher: OwnedGamesFetcher,
        metadata_fetcher: MetadataFetcher,
        tags_fetcher: TagsFetcher,
        steam_id64: str,
    ) -> None:
        self._repository = repository
        self._owned_games_fetcher = owned_games_fetcher
        self._metadata_fetcher = metadata_fetcher
        self._tags_fetcher = tags_fetcher
        self._steam_id64 = steam_id64

    def sync(
        self,
        *,
        force: bool = False,
        progress: Callable[[str, float], None] | None = None,
    ) -> SyncResult:
        result = SyncResult()

        self._sync_owned_games(result, force=force, progress=progress)

        owned_games = self._repository.get_owned_games()
        self._sync_metadata(
            owned_games,
            result,
            force=force,
            progress=progress,
        )
        self._sync_tags(
            owned_games,
            result,
            force=force,
            progress=progress,
        )

        self._emit_progress(progress, "Library sync complete", 1.0)
        return result

    def _sync_owned_games(
        self,
        result: SyncResult,
        *,
        force: bool,
        progress: Callable[[str, float], None] | None,
    ) -> None:
        self._emit_progress(progress, "Checking owned-games cache", 0.05)
        if not force and is_fresh(self._repository.owned_fetched_at(), OWNED_GAMES_TTL):
            result.owned_games_skipped = 1
            self._emit_progress(progress, "Owned-games cache is fresh; skipping fetch", 0.2)
            return

        self._emit_progress(progress, "Fetching owned games from Steam Web API", 0.12)
        try:
            games = self._owned_games_fetcher.get_owned_games(self._steam_id64)
            self._repository.upsert_owned_games(games)
        except Exception:
            result.owned_games_failed = 1
            self._emit_progress(progress, "Owned-games fetch failed", 1.0)
            raise

        result.owned_games_fetched = len(games)
        self._emit_progress(progress, f"Stored {len(games)} owned games", 0.2)

    def _sync_metadata(
        self,
        owned_games: list[OwnedGame],
        result: SyncResult,
        *,
        force: bool,
        progress: Callable[[str, float], None] | None,
    ) -> None:
        total_games = len(owned_games)
        if total_games == 0:
            return

        self._emit_progress(progress, "Syncing Steam Store metadata", 0.25)
        for index, game in enumerate(owned_games, start=1):
            if not force and is_fresh(self._repository.metadata_fetched_at(game.appid), METADATA_TTL):
                result.metadata_skipped += 1
            else:
                try:
                    metadata = self._metadata_fetcher.get_metadata(game.appid)
                    self._repository.upsert_metadata(metadata)
                    result.metadata_fetched += 1
                except Exception:
                    result.metadata_failed += 1

            stage_ratio = index / total_games
            self._emit_progress(progress, "Syncing Steam Store metadata", 0.25 + stage_ratio * 0.35)

    def _sync_tags(
        self,
        owned_games: list[OwnedGame],
        result: SyncResult,
        *,
        force: bool,
        progress: Callable[[str, float], None] | None,
    ) -> None:
        total_games = len(owned_games)
        if total_games == 0:
            return

        self._emit_progress(progress, "Syncing SteamSpy tags", 0.65)
        for index, game in enumerate(owned_games, start=1):
            if not force and is_fresh(self._repository.tags_fetched_at(game.appid), TAGS_TTL):
                result.tags_skipped += 1
            else:
                try:
                    tags = self._tags_fetcher.get_tags(game.appid)
                    self._repository.upsert_tags(game.appid, tags)
                    result.tags_fetched += 1
                except Exception:
                    result.tags_failed += 1

            stage_ratio = index / total_games
            self._emit_progress(progress, "Syncing SteamSpy tags", 0.65 + stage_ratio * 0.3)

    @staticmethod
    def _emit_progress(
        progress: Callable[[str, float], None] | None,
        message: str,
        ratio: float,
    ) -> None:
        if progress is None:
            return
        progress(message, ratio)
