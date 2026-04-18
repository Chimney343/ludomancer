from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StatsView(QWidget):
    """Read-only dashboard for library stats and genre-level playtime."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._total_games_value = QLabel("0")
        self._played_games_value = QLabel("0")
        self._backlog_games_value = QLabel("0")
        self._total_hours_value = QLabel("0.0")

        self._genre_table = QTableWidget(0, 2)
        self._genre_table.setHorizontalHeaderLabels(["Genre", "Hours"])
        self._genre_table.verticalHeader().setVisible(False)
        self._genre_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._genre_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        self._top_games_table = QTableWidget(0, 3)
        self._top_games_table.setHorizontalHeaderLabels(["Game", "Hours", "Genres"])
        self._top_games_table.verticalHeader().setVisible(False)
        self._top_games_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._top_games_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        summary_layout = QGridLayout()
        summary_layout.addWidget(self._tile("Total Games", self._total_games_value), 0, 0)
        summary_layout.addWidget(self._tile("Played (>=3h)", self._played_games_value), 0, 1)
        summary_layout.addWidget(self._tile("Backlog (<3h)", self._backlog_games_value), 0, 2)
        summary_layout.addWidget(self._tile("Total Hours", self._total_hours_value), 0, 3)

        genres_box = QGroupBox("Hours by Genre")
        genres_layout = QVBoxLayout()
        genres_layout.addWidget(self._genre_table)
        genres_box.setLayout(genres_layout)

        top_games_box = QGroupBox("Top Played Games")
        top_games_layout = QVBoxLayout()
        top_games_layout.addWidget(self._top_games_table)
        top_games_box.setLayout(top_games_layout)

        root_layout = QVBoxLayout()
        root_layout.addLayout(summary_layout)
        root_layout.addWidget(genres_box)
        root_layout.addWidget(top_games_box)
        self.setLayout(root_layout)

    def set_stats(
        self,
        *,
        total_games: int,
        played_games: int,
        backlog_games: int,
        total_hours: float,
        hours_by_genre: Sequence[tuple[str, float]],
        top_played_games: Sequence[tuple[str, float, str]],
    ) -> None:
        self._total_games_value.setText(str(total_games))
        self._played_games_value.setText(str(played_games))
        self._backlog_games_value.setText(str(backlog_games))
        self._total_hours_value.setText(f"{total_hours:.1f}")

        self._set_table_rows(
            self._genre_table,
            [(genre, f"{hours:.1f}") for genre, hours in hours_by_genre],
        )
        self._set_table_rows(
            self._top_games_table,
            [(name, f"{hours:.1f}", genres) for name, hours, genres in top_played_games],
        )

        self._genre_table.resizeColumnsToContents()
        self._top_games_table.resizeColumnsToContents()

    @staticmethod
    def _set_table_rows(table: QTableWidget, rows: Sequence[Sequence[str]]) -> None:
        table.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            for col_index, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                if col_index > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_index, col_index, item)

    @staticmethod
    def _tile(label: str, value_label: QLabel) -> QGroupBox:
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setObjectName("statsTileValue")

        tile = QGroupBox(label)
        tile_layout = QVBoxLayout()
        tile_layout.addWidget(value_label)
        tile.setLayout(tile_layout)
        return tile
