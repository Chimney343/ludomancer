from __future__ import annotations

import json
from pathlib import Path

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.analysis.recommender import classify, recommend
from ludomancer.models import EnrichedGame

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "small_library.json"


def _load_small_library() -> list[EnrichedGame]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [EnrichedGame.model_validate(item) for item in raw]


def test_recommend_top_action_candidate_matches_highest_tag_overlap_fixture() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)

    shortlists = recommend(games, matrix)
    by_genre = {item.genre: item for item in shortlists}

    assert "Action" in by_genre
    assert by_genre["Action"].candidates[0][1] == "Action Backlog Match"


def test_recommend_uses_global_fallback_when_genre_has_no_played_games() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)

    shortlists = recommend(games, matrix)
    by_genre = {item.genre: item for item in shortlists}

    strategy = by_genre["Strategy"]
    assert strategy.signal_games == []
    assert len(strategy.candidates) >= 1


def test_recommend_emits_candidates_for_each_active_genre_with_backlog_games() -> None:
    games = _load_small_library()
    played, backlog = classify(games)
    assert played
    assert backlog

    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)
    shortlists = recommend(games, matrix)

    expected_genres: set[str] = set()
    for game in backlog:
        for genre in game.metadata.genres:
            expected_genres.add(genre)

    emitted_genres = {item.genre for item in shortlists}
    assert expected_genres == emitted_genres

    racing = next(item for item in shortlists if item.genre == "Racing")
    assert len(racing.candidates) == 1
