from __future__ import annotations

import logging
import sys

from pydantic import ValidationError
from PyQt6.QtWidgets import QApplication, QMessageBox

from ludomancer.cache.db import ensure_schema, get_connection
from ludomancer.config import get_settings
from ludomancer.llm.base import LLMClientError, build_client

from .main_window import MainWindow

logger = logging.getLogger(__name__)


def _format_settings_validation_error(error: ValidationError) -> str:
    lines = ["Invalid configuration. Update .env with required values:"]
    for issue in error.errors():
        location = ".".join(str(part) for part in issue.get("loc", [])) or "settings"
        message = issue.get("msg", "invalid value")
        lines.append(f"- {location}: {message}")
    return "\n".join(lines)


def _show_error_dialog(title: str, message: str) -> None:
    QMessageBox.critical(None, title, message)


def _apply_app_stylesheet(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            font-family: "Segoe UI", "Arial";
            font-size: 10pt;
        }
        QGroupBox {
            font-weight: 600;
            margin-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        QLabel#statsTileValue {
            font-size: 16pt;
            font-weight: 700;
        }
        QFrame#genreCardFrame {
            border: 1px solid #cfcfcf;
            border-radius: 8px;
            background-color: #fafafa;
        }
        QLabel#recommendationGenre {
            font-size: 11pt;
            font-weight: 700;
        }
        QLabel#recommendationPick {
            font-size: 13pt;
            font-weight: 700;
            color: #1c4d7a;
        }
        QLabel#recommendationReasoning {
            color: #202020;
        }
        QLabel#recommendationsStateError {
            color: #9f1d1d;
            font-weight: 700;
        }
        """
    )


def main() -> int:
    """Launch the desktop app and wire background workers to the main window."""

    logging.basicConfig(level=logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName("Ludomancer")
    _apply_app_stylesheet(app)

    try:
        settings = get_settings()
    except ValidationError as error:
        _show_error_dialog("Invalid Configuration", _format_settings_validation_error(error))
        return 1

    conn = None
    try:
        conn = get_connection(settings.cache_db_path)
        ensure_schema(conn)
    except Exception as error:  # pragma: no cover - requires runtime DB failure
        _show_error_dialog("Cache Initialization Failed", str(error))
        return 1
    finally:
        if conn is not None:
            conn.close()

    llm_client = None
    try:
        llm_client = build_client(settings)
    except LLMClientError as error:
        logger.info("LLM integration disabled: %s", error)

    window = MainWindow(settings, llm_client=llm_client)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
