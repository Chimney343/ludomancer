from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from ludomancer.analysis.recommender import PLAYED_THRESHOLD_MINUTES
from ludomancer.cache.db import get_connection
from ludomancer.cache.repository import GameRepository
from ludomancer.config import Settings
from ludomancer.llm.base import LLMClient, close_client
from ludomancer.models import LLMPayload, LLMRecommendationResponse

from .analyze_view import AnalyzeView
from .recommendations_view import RecommendationsView
from .stats_view import StatsView
from .workers import (
    AnalyzeResult,
    AnalyzeWorker,
    LLMWorker,
    SyncWorker,
    format_llm_result,
    format_sync_result,
)


class MainWindow(QMainWindow):
    """Desktop shell with stats, analysis, and recommendations workflows."""

    def __init__(self, settings: Settings, *, llm_client: LLMClient | None = None) -> None:
        super().__init__()

        self._settings = settings
        self._llm_client = llm_client
        self._thread_pool = QThreadPool(self)
        self._active_workers: set[Any] = set()
        self._busy = False
        self._latest_payload: LLMPayload | None = None

        self._stats_view = StatsView(self)
        self._analyze_view = AnalyzeView(self)
        self._recommendations_view = RecommendationsView(self)

        self._tabs = QTabWidget(self)
        self._tabs.addTab(self._stats_view, "Stats")
        self._tabs.addTab(self._analyze_view, "Analyze")
        self._tabs.addTab(self._recommendations_view, "Recommendations")
        self.setCentralWidget(self._tabs)

        self.setWindowTitle("Ludomancer")
        self.resize(1120, 760)

        self._analyze_view.refresh_requested.connect(self._start_sync)
        self._analyze_view.analyze_requested.connect(self._start_analysis)
        self._analyze_view.ask_llm_requested.connect(self._ask_llm)
        self._recommendations_view.retry_requested.connect(self._ask_llm)

        self._analyze_view.log_message("UI ready.")
        self._recommendations_view.set_empty_state(
            "Run analysis and Ask LLM to populate recommendations."
        )
        self._refresh_stats_from_cache()
        self._update_llm_state()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._thread_pool.waitForDone(2000)
        close_client(self._llm_client)
        super().closeEvent(event)

    def _start_sync(self, force: bool) -> None:
        if self._busy:
            return

        worker = SyncWorker(self._settings, force=force)
        mode = "force refresh" if force else "refresh"
        self._analyze_view.log_message(f"Starting library {mode}.")
        self._start_worker(
            worker,
            label="Library sync",
            on_finished=self._handle_sync_finished,
        )

    def _start_analysis(self) -> None:
        if self._busy:
            return

        worker = AnalyzeWorker(self._settings.cache_db_path)
        self._analyze_view.log_message("Starting analysis run.")
        self._start_worker(
            worker,
            label="Analysis",
            on_finished=self._handle_analysis_finished,
        )

    def _ask_llm(self) -> None:
        if self._busy:
            return

        if self._latest_payload is None or not self._latest_payload.genres:
            self._recommendations_view.set_empty_state(
                "Run analysis first so recommendation payload exists."
            )
            QMessageBox.information(
                self,
                "No Analysis Payload",
                "Run analysis first so there is recommendation payload to send.",
            )
            return

        if self._llm_client is None:
            self._recommendations_view.set_empty_state(
                "Configure ANTHROPIC_API_KEY or OPENROUTER_API_KEY to ask the LLM."
            )
            QMessageBox.information(
                self,
                "LLM Not Configured",
                "Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY to enable Ask LLM.",
            )
            return

        worker = LLMWorker(self._llm_client, self._latest_payload)
        self._recommendations_view.set_loading_state("Generating recommendations with LLM...")
        self._analyze_view.log_message("Sending payload to LLM provider.")
        self._start_worker(worker, label="LLM request", on_finished=self._handle_llm_finished)

    def _start_worker(
        self,
        worker: Any,
        *,
        label: str,
        on_finished: Callable[[Any], None],
    ) -> None:
        self._set_busy(True)
        self._active_workers.add(worker)

        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(
            lambda payload, active_worker=worker: self._on_worker_finished(
                active_worker,
                payload,
                on_finished,
            )
        )
        worker.signals.failed.connect(
            lambda message, active_worker=worker: self._on_worker_failed(
                active_worker,
                label,
                message,
            )
        )

        self._analyze_view.set_progress(f"{label} started", 0.0)
        self._thread_pool.start(worker)

    def _on_progress(self, message: str, ratio: float) -> None:
        self._analyze_view.set_progress(message, ratio)

    def _on_worker_finished(
        self,
        worker: Any,
        payload: Any,
        on_finished: Callable[[Any], None],
    ) -> None:
        self._active_workers.discard(worker)
        self._set_busy(False)
        on_finished(payload)

    def _on_worker_failed(self, worker: Any, label: str, message: str) -> None:
        self._active_workers.discard(worker)
        self._set_busy(False)
        friendly_message = message or "Unknown error"
        self._analyze_view.log_message(f"{label} failed: {friendly_message}")
        if label == "LLM request":
            self._recommendations_view.set_error_state(
                f"Recommendation request failed: {friendly_message}"
            )
        QMessageBox.critical(
            self,
            f"{label} Failed",
            friendly_message,
        )

    def _handle_sync_finished(self, payload: Any) -> None:
        summary = format_sync_result(payload)
        self._latest_payload = None
        self._refresh_stats_from_cache()
        self._update_llm_state()
        self._recommendations_view.set_empty_state(
            "Library cache refreshed. Run analysis again before asking the LLM."
        )

        self._analyze_view.set_progress("Library sync complete", 1.0)
        self._analyze_view.log_message(f"Sync completed ({summary}).")

    def _handle_analysis_finished(self, payload: Any) -> None:
        result = self._as_analyze_result(payload)
        self._latest_payload = result.payload if result.payload.genres else None
        self._update_llm_state()

        self._analyze_view.set_progress("Analysis complete", 1.0)
        self._analyze_view.log_message(
            "Analysis produced "
            f"{len(result.shortlists)} genre shortlists from "
            f"{len(result.enriched_games)} enriched games "
            f"(played={len(result.played_games)}, backlog={len(result.backlog_games)})."
        )
        if self._latest_payload is None:
            self._analyze_view.log_message("No genre payload was produced for LLM.")
            self._recommendations_view.set_empty_state(
                "Analysis finished, but no valid genre payload was produced for recommendations."
            )
            return

        if self._llm_client is None:
            self._recommendations_view.set_empty_state(
                "Analysis is ready. Add an LLM API key, then click Ask LLM."
            )
            return

        self._recommendations_view.set_empty_state(
            "Analysis is ready. Click Ask LLM to generate one pick per genre."
        )

    def _handle_llm_finished(self, payload: Any) -> None:
        response = self._as_llm_response(payload)
        summary = format_llm_result(response)
        self._analyze_view.set_progress("LLM recommendations complete", 1.0)
        self._analyze_view.log_message(f"LLM picks: {summary}")

        if self._latest_payload is None:
            self._recommendations_view.set_error_state(
                "No analysis payload available to display recommendation cards."
            )
            return

        self._recommendations_view.set_recommendations(response, self._latest_payload)
        self._tabs.setCurrentWidget(self._recommendations_view)

    def _refresh_stats_from_cache(self) -> None:
        conn = get_connection(self._settings.cache_db_path)
        try:
            repository = GameRepository(conn)
            owned_games = repository.get_owned_games()
            metadata_by_appid = {
                metadata.appid: metadata for metadata in repository.get_all_metadata()
            }
        finally:
            conn.close()

        total_games = len(owned_games)
        played_games = sum(
            1
            for game in owned_games
            if game.playtime_forever_minutes >= PLAYED_THRESHOLD_MINUTES
        )
        backlog_games = total_games - played_games
        total_hours = sum(game.playtime_forever_minutes for game in owned_games) / 60.0

        hours_by_genre_map: dict[str, float] = defaultdict(float)
        for game in owned_games:
            metadata = metadata_by_appid.get(game.appid)
            if metadata is None:
                continue

            hours = game.playtime_forever_minutes / 60.0
            for genre in metadata.genres:
                cleaned = genre.strip()
                if cleaned:
                    hours_by_genre_map[cleaned] += hours

        hours_by_genre = sorted(
            hours_by_genre_map.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )

        sorted_owned_games = sorted(
            owned_games,
            key=lambda game: (-game.playtime_forever_minutes, game.name.lower()),
        )
        top_played_games: list[tuple[str, float, str]] = []
        for game in sorted_owned_games[:10]:
            metadata = metadata_by_appid.get(game.appid)
            genres = ", ".join(metadata.genres[:3]) if metadata and metadata.genres else "-"
            top_played_games.append(
                (
                    game.name,
                    game.playtime_forever_minutes / 60.0,
                    genres,
                )
            )

        self._stats_view.set_stats(
            total_games=total_games,
            played_games=played_games,
            backlog_games=backlog_games,
            total_hours=total_hours,
            hours_by_genre=hours_by_genre,
            top_played_games=top_played_games,
        )
        self._analyze_view.log_message(
            f"Stats refreshed (games={total_games}, played={played_games}, backlog={backlog_games})."
        )

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._analyze_view.set_busy(busy)
        if not busy:
            self._update_llm_state()

    def _update_llm_state(self) -> None:
        ready = (
            not self._busy
            and self._llm_client is not None
            and self._latest_payload is not None
            and bool(self._latest_payload.genres)
        )
        self._analyze_view.set_llm_ready(ready)

    @staticmethod
    def _as_analyze_result(payload: Any) -> AnalyzeResult:
        if isinstance(payload, AnalyzeResult):
            return payload
        raise TypeError("Analyze worker returned an unexpected payload type.")

    @staticmethod
    def _as_llm_response(payload: Any) -> LLMRecommendationResponse:
        if isinstance(payload, LLMRecommendationResponse):
            return payload
        raise TypeError("LLM worker returned an unexpected payload type.")
