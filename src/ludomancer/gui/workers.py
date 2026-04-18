from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.analysis.recommender import classify, recommend
from ludomancer.analysis.summary import build_llm_payload
from ludomancer.cache.db import get_connection
from ludomancer.cache.repository import GameRepository
from ludomancer.config import Settings
from ludomancer.fetchers.steamspy import SteamSpyClient
from ludomancer.fetchers.store import SteamStoreClient
from ludomancer.fetchers.web_api import SteamWebAPIClient
from ludomancer.llm.base import LLMClient
from ludomancer.models import EnrichedGame, GenreShortlist, LLMPayload, LLMRecommendationResponse
from ludomancer.services.library_sync import LibrarySyncService, SyncResult


class WorkerSignals(QObject):
    """Signals shared by QRunnable workers."""

    progress = pyqtSignal(str, float)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


@dataclass(slots=True)
class AnalyzeResult:
    enriched_games: list[EnrichedGame]
    played_games: list[EnrichedGame]
    backlog_games: list[EnrichedGame]
    shortlists: list[GenreShortlist]
    payload: LLMPayload


class SyncWorker(QRunnable):
    """Background worker for full library synchronization."""

    def __init__(self, settings: Settings, *, force: bool = False) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._settings = settings
        self._force = force

    def run(self) -> None:
        conn = get_connection(self._settings.cache_db_path)
        web_api = SteamWebAPIClient(
            api_key=self._settings.steam_api_key,
            timeout_s=self._settings.http_timeout_s,
        )
        store = SteamStoreClient(timeout_s=self._settings.http_timeout_s)
        steamspy = SteamSpyClient(timeout_s=self._settings.http_timeout_s)

        try:
            repository = GameRepository(conn)
            service = LibrarySyncService(
                repository,
                web_api,
                store,
                steamspy,
                self._settings.steam_id64,
            )
            result = service.sync(force=self._force, progress=self._emit_progress)
        except Exception as error:  # pragma: no cover - exercised through integration behavior
            self.signals.failed.emit(str(error))
            return
        finally:
            web_api.close()
            store.close()
            steamspy.close()
            conn.close()

        self.signals.finished.emit(result)

    def _emit_progress(self, message: str, ratio: float) -> None:
        self.signals.progress.emit(message, ratio)


class AnalyzeWorker(QRunnable):
    """Background worker for feature extraction and shortlist generation."""

    def __init__(self, cache_db_path: Path) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._cache_db_path = cache_db_path

    def run(self) -> None:
        try:
            self.signals.progress.emit("Loading games from cache", 0.1)
            games = self._load_enriched_games()

            self.signals.progress.emit("Building feature corpus", 0.35)
            corpus = build_corpus(games)
            _vectorizer, matrix = fit_vectorizer(corpus)

            self.signals.progress.emit("Ranking backlog candidates", 0.65)
            shortlists = recommend(games, matrix)
            played_games, backlog_games = classify(games)
            payload = build_llm_payload(shortlists, played_games, all_games=games)

            result = AnalyzeResult(
                enriched_games=games,
                played_games=played_games,
                backlog_games=backlog_games,
                shortlists=shortlists,
                payload=payload,
            )
            self.signals.progress.emit("Analysis complete", 1.0)
            self.signals.finished.emit(result)
        except Exception as error:  # pragma: no cover - exercised through integration behavior
            self.signals.failed.emit(str(error))

    def _load_enriched_games(self) -> list[EnrichedGame]:
        conn = get_connection(self._cache_db_path)
        try:
            repository = GameRepository(conn)
            enriched_games: list[EnrichedGame] = []
            for owned_game in repository.get_owned_games():
                metadata = repository.get_metadata(owned_game.appid)
                if metadata is None:
                    continue

                tags = repository.get_tags(owned_game.appid)
                enriched_games.append(
                    EnrichedGame(owned=owned_game, metadata=metadata, tags=tags)
                )
            return enriched_games
        finally:
            conn.close()


class LLMWorker(QRunnable):
    """Background worker for provider-backed recommendation generation."""

    def __init__(self, client: LLMClient, payload: LLMPayload) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._client = client
        self._payload = payload

    def run(self) -> None:
        try:
            self.signals.progress.emit("Requesting recommendations from LLM", 0.35)
            response = self._client.recommend(self._payload)
            self.signals.progress.emit("LLM response validated", 1.0)
            self.signals.finished.emit(response)
        except Exception as error:  # pragma: no cover - exercised through integration behavior
            self.signals.failed.emit(str(error))


def format_sync_result(result: SyncResult) -> str:
    summary = result.to_dict()
    return (
        "owned: "
        f"fetched={summary['owned_games_fetched']} "
        f"skipped={summary['owned_games_skipped']} "
        f"failed={summary['owned_games_failed']} | "
        "metadata: "
        f"fetched={summary['metadata_fetched']} "
        f"skipped={summary['metadata_skipped']} "
        f"failed={summary['metadata_failed']} | "
        "tags: "
        f"fetched={summary['tags_fetched']} "
        f"skipped={summary['tags_skipped']} "
        f"failed={summary['tags_failed']}"
    )


def format_llm_result(response: LLMRecommendationResponse) -> str:
    picks = [f"{item.genre}: {item.pick_name}" for item in response.recommendations]
    return "; ".join(picks)
