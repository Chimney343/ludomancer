"""GUI package for Ludomancer."""

from .analyze_view import AnalyzeView
from .app import main
from .main_window import MainWindow
from .recommendations_view import RecommendationsView
from .stats_view import StatsView

__all__ = ["AnalyzeView", "MainWindow", "RecommendationsView", "StatsView", "main"]
