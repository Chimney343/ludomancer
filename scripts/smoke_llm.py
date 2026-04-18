from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.analysis.recommender import classify, recommend
from ludomancer.analysis.summary import build_llm_payload
from ludomancer.cache.db import get_connection
from ludomancer.cache.repository import GameRepository
from ludomancer.llm.base import LLMClientError, LLMResponseError, build_client, close_client
from ludomancer.models import EnrichedGame


@dataclass
class _LLMSettings:
    anthropic_api_key: str | None
    openrouter_api_key: str | None
    anthropic_model: str
    openrouter_model: str
    http_timeout_s: float


def _load_llm_settings() -> _LLMSettings:
    return _LLMSettings(
        anthropic_api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip() or None,
        openrouter_api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip() or None,
        anthropic_model=(os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-5").strip(),
        openrouter_model=(os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.5").strip(),
        http_timeout_s=float((os.getenv("HTTP_TIMEOUT_S") or "15.0").strip()),
    )


def _load_enriched_games_from_fixture(path: Path) -> list[EnrichedGame]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [EnrichedGame.model_validate(item) for item in raw]


def _load_enriched_games_from_cache(db_path: Path) -> list[EnrichedGame]:
    conn = get_connection(db_path)
    try:
        repository = GameRepository(conn)
        enriched: list[EnrichedGame] = []
        for owned in repository.get_owned_games():
            metadata = repository.get_metadata(owned.appid)
            if metadata is None:
                continue
            tags = repository.get_tags(owned.appid)
            enriched.append(EnrichedGame(owned=owned, metadata=metadata, tags=tags))
        return enriched
    finally:
        conn.close()


def _build_payload(games: list[EnrichedGame]):
    corpus = build_corpus(games)
    _vectorizer, matrix = fit_vectorizer(corpus)
    shortlists = recommend(games, matrix)
    played, _backlog = classify(games)
    payload = build_llm_payload(shortlists, played, all_games=games)
    return shortlists, played, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for Phase 5 LLM recommendation flow.")
    parser.add_argument(
        "--source",
        choices=["cache", "fixture"],
        default="fixture",
        help="Where to load enriched games from.",
    )
    parser.add_argument(
        "--fixture-path",
        default="tests/fixtures/small_library.json",
        help="Fixture path used when --source=fixture.",
    )
    parser.add_argument(
        "--payload-only",
        action="store_true",
        help="Build and print payload without calling an LLM provider.",
    )
    parser.add_argument(
        "--cache-db-path",
        default=(os.getenv("CACHE_DB_PATH") or "cache.db"),
        help="SQLite cache path used when --source=cache.",
    )
    args = parser.parse_args()

    if args.source == "fixture":
        games = _load_enriched_games_from_fixture(Path(args.fixture_path))
    else:
        games = _load_enriched_games_from_cache(Path(args.cache_db_path))

    if not games:
        print("No enriched games available for analysis.")
        raise SystemExit(1)

    shortlists, played, payload = _build_payload(games)
    print(
        json.dumps(
            {
                "games": len(games),
                "played": len(played),
                "genres": len(shortlists),
                "payload_genres": len(payload.genres),
            },
            indent=2,
            sort_keys=True,
        )
    )

    if args.payload_only:
        print(payload.model_dump_json(indent=2))
        return

    settings = _load_llm_settings()
    try:
        client = build_client(settings)
    except LLMClientError as error:
        print(f"Client setup failed: {error}")
        raise SystemExit(1) from error

    try:
        response = client.recommend(payload)
    except (LLMClientError, LLMResponseError) as error:
        print(f"LLM call failed: {error}")
        raise SystemExit(1) from error
    finally:
        close_client(client)

    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
