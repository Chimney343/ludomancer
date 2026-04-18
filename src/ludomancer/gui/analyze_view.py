from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AnalyzeView(QWidget):
    """Controls for refresh/analyze/LLM actions with progress and log output."""

    refresh_requested = pyqtSignal(bool)
    analyze_requested = pyqtSignal()
    ask_llm_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._llm_ready = False
        self._busy = False

        self._refresh_button = QPushButton("Refresh Cache")
        self._force_refresh_button = QPushButton("Force Refresh")
        self._analyze_button = QPushButton("Run Analysis")
        self._ask_llm_button = QPushButton("Ask LLM")
        self._ask_llm_button.setEnabled(False)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._refresh_button)
        controls_layout.addWidget(self._force_refresh_button)
        controls_layout.addWidget(self._analyze_button)
        controls_layout.addWidget(self._ask_llm_button)
        controls_layout.addStretch(1)

        self._status_label = QLabel("Idle")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Pipeline logs will appear here.")

        root_layout = QVBoxLayout()
        root_layout.addLayout(controls_layout)
        root_layout.addWidget(self._status_label)
        root_layout.addWidget(self._progress_bar)
        root_layout.addWidget(self._log)
        self.setLayout(root_layout)

        self._refresh_button.clicked.connect(lambda: self.refresh_requested.emit(False))
        self._force_refresh_button.clicked.connect(lambda: self.refresh_requested.emit(True))
        self._analyze_button.clicked.connect(self.analyze_requested.emit)
        self._ask_llm_button.clicked.connect(self.ask_llm_requested.emit)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        enabled = not busy
        self._refresh_button.setEnabled(enabled)
        self._force_refresh_button.setEnabled(enabled)
        self._analyze_button.setEnabled(enabled)
        self._ask_llm_button.setEnabled(enabled and self._llm_ready)

    def set_llm_ready(self, ready: bool) -> None:
        self._llm_ready = ready
        self._ask_llm_button.setEnabled((not self._busy) and ready)

    def set_progress(self, message: str, ratio: float) -> None:
        clamped = max(0.0, min(ratio, 1.0))
        self._status_label.setText(message)
        self._progress_bar.setValue(int(clamped * 100))

    def log_message(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{timestamp}] {message}")
