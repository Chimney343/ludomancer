from __future__ import annotations

import json
from pathlib import Path

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.analysis.recommender import classify, recommend
from ludomancer.analysis.summary import build_llm_payload
from ludomancer.models import EnrichedGame, LLMPayload

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "small_library.json"


def _load_small_library() -> list[EnrichedGame]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return [EnrichedGame.model_validate(item) for item in raw]


def test_build_llm_payload_round_trips_through_pydantic() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)

    shortlists = recommend(games, matrix)
    played, _backlog = classify(games)
    payload = build_llm_payload(shortlists, played, all_games=games)

    encoded = payload.model_dump_json()
    parsed = LLMPayload.model_validate_json(encoded)

    assert parsed.model_dump() == payload.model_dump()


def test_build_llm_payload_uses_global_reference_when_genre_has_no_played_games() -> None:
    games = _load_small_library()
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)

    shortlists = recommend(games, matrix)
    played, _backlog = classify(games)
    payload = build_llm_payload(shortlists, played, all_games=games)

    strategy_payload = next(item for item in payload.genres if item.genre == "Strategy")
    assert len(strategy_payload.reference_games) == 3
    assert strategy_payload.reference_games[0].name == "RPG Legend"
    assert strategy_payload.candidates
