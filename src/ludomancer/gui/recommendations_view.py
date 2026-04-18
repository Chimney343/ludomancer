from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ludomancer.models import LLMPayload, LLMRecommendationResponse


@dataclass(slots=True)
class RecommendationCardData:
    genre: str
    pick_name: str
    reasoning: str
    alternatives: list[tuple[str, list[str]]]


def build_card_data(
    response: LLMRecommendationResponse,
    payload: LLMPayload,
) -> list[RecommendationCardData]:
    payload_by_genre = {genre_payload.genre: genre_payload for genre_payload in payload.genres}

    cards: list[RecommendationCardData] = []
    for recommendation in response.recommendations:
        genre_payload = payload_by_genre.get(recommendation.genre)
        alternatives: list[tuple[str, list[str]]] = []
        if genre_payload is not None:
            for candidate in genre_payload.candidates:
                if candidate.name == recommendation.pick_name:
                    continue
                alternatives.append((candidate.name, list(candidate.top_tags)))

        cards.append(
            RecommendationCardData(
                genre=recommendation.genre,
                pick_name=recommendation.pick_name,
                reasoning=recommendation.reasoning,
                alternatives=alternatives,
            )
        )

    return cards


class GenreCard(QFrame):
    """Recommendation card for one genre with a picked game and alternatives."""

    def __init__(self, data: RecommendationCardData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("genreCardFrame")

        genre_label = QLabel(data.genre)
        genre_label.setObjectName("recommendationGenre")

        pick_label = QLabel(data.pick_name)
        pick_label.setObjectName("recommendationPick")

        reasoning_label = QLabel(data.reasoning)
        reasoning_label.setWordWrap(True)
        reasoning_label.setObjectName("recommendationReasoning")

        self._toggle_button = QPushButton("Show alternatives")
        self._toggle_button.setObjectName("alternativesToggle")
        self._toggle_button.setCheckable(True)
        self._toggle_button.toggled.connect(self._on_toggled)

        self._alternatives_container = QWidget()
        alternatives_layout = QVBoxLayout()
        alternatives_layout.setContentsMargins(0, 0, 0, 0)
        alternatives_layout.setSpacing(4)
        self._alternatives_container.setLayout(alternatives_layout)
        self._alternatives_container.setVisible(False)

        if data.alternatives:
            for candidate_name, tags in data.alternatives:
                tags_text = ", ".join(tags) if tags else "no tags"
                alternatives_layout.addWidget(QLabel(f"- {candidate_name} ({tags_text})"))
        else:
            self._toggle_button.setEnabled(False)
            self._toggle_button.setText("No alternatives")

        header_layout = QHBoxLayout()
        header_layout.addWidget(genre_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self._toggle_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header_layout)
        layout.addWidget(pick_label)
        layout.addWidget(reasoning_label)
        layout.addWidget(self._alternatives_container)
        self.setLayout(layout)

    def _on_toggled(self, checked: bool) -> None:
        self._alternatives_container.setVisible(checked)
        self._toggle_button.setText("Hide alternatives" if checked else "Show alternatives")


class RecommendationsView(QWidget):
    """State-driven recommendations panel with empty/loading/error/content modes."""

    retry_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._cards: list[GenreCard] = []

        self._state_label = QLabel("Run analysis and Ask LLM to populate recommendations.")
        self._state_label.setObjectName("recommendationsState")
        self._state_label.setWordWrap(True)

        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        self._loading_bar.setVisible(False)

        self._retry_button = QPushButton("Retry")
        self._retry_button.clicked.connect(self.retry_requested.emit)
        self._retry_button.setVisible(False)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_container.setLayout(self._cards_layout)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setWidget(self._cards_container)
        self._scroll_area.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(self._state_label)
        layout.addWidget(self._loading_bar)
        layout.addWidget(self._retry_button)
        layout.addWidget(self._scroll_area)
        self.setLayout(layout)

    def set_empty_state(self, message: str) -> None:
        self._clear_cards()
        self._state_label.setObjectName("recommendationsState")
        self._state_label.setStyleSheet("")
        self._state_label.setText(message)
        self._state_label.setVisible(True)
        self._loading_bar.setVisible(False)
        self._retry_button.setVisible(False)
        self._scroll_area.setVisible(False)

    def set_loading_state(self, message: str) -> None:
        self._state_label.setObjectName("recommendationsState")
        self._state_label.setStyleSheet("")
        self._state_label.setText(message)
        self._state_label.setVisible(True)
        self._loading_bar.setVisible(True)
        self._retry_button.setVisible(False)
        self._scroll_area.setVisible(False)

    def set_error_state(self, message: str) -> None:
        self._state_label.setObjectName("recommendationsStateError")
        self._state_label.setStyleSheet("")
        self._state_label.setText(message)
        self._state_label.setVisible(True)
        self._loading_bar.setVisible(False)
        self._retry_button.setVisible(True)
        self._scroll_area.setVisible(False)

    def set_recommendations(self, response: LLMRecommendationResponse, payload: LLMPayload) -> None:
        cards = build_card_data(response, payload)
        if not cards:
            self.set_empty_state("No recommendations were returned by the model.")
            return

        self._clear_cards()
        for card_data in cards:
            card = GenreCard(card_data)
            self._cards_layout.addWidget(card)
            self._cards.append(card)

        self._state_label.setVisible(False)
        self._loading_bar.setVisible(False)
        self._retry_button.setVisible(False)
        self._scroll_area.setVisible(True)

    def _clear_cards(self) -> None:
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
