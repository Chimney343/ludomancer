from __future__ import annotations

import json
from pathlib import Path

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.models import EnrichedGame

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "small_library.json"


def _load_small_library() -> list[EnrichedGame]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [EnrichedGame.model_validate(item) for item in raw]


def test_build_corpus_keeps_row_alignment_and_tag_weighting() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)

    assert len(corpus) == len(games)

    action_hero_index = next(i for i, game in enumerate(games) if game.owned.appid == 101)
    tokens = corpus[action_hero_index].split()
    assert tokens.count("tag_action") == 5


def test_build_corpus_includes_zero_signal_game_as_empty_document() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)

    zero_signal_index = next(i for i, game in enumerate(games) if game.owned.appid == 120)
    assert corpus[zero_signal_index] == ""


def test_fit_vectorizer_returns_matrix_with_zero_vector_for_zero_signal_game() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)

    assert matrix.shape[0] == len(games)
    assert matrix.shape[1] > 0

    zero_signal_index = next(i for i, game in enumerate(games) if game.owned.appid == 120)
    assert matrix.getrow(zero_signal_index).nnz == 0
