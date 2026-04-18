from __future__ import annotations

import logging
import math
import re

from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from ludomancer.models import EnrichedGame

logger = logging.getLogger(__name__)

_TOKEN_NORMALIZER = re.compile(r"[^a-z0-9]+")


def _normalize_token(value: str) -> str:
    token = _TOKEN_NORMALIZER.sub("_", value.strip().lower()).strip("_")
    return token


def _genre_tokens(game: EnrichedGame) -> list[str]:
    tokens: list[str] = []
    for genre in game.metadata.genres:
        normalized = _normalize_token(genre)
        if normalized:
            tokens.append(f"genre_{normalized}")
    return tokens


def _category_tokens(game: EnrichedGame) -> list[str]:
    tokens: list[str] = []
    for category in game.metadata.categories:
        normalized = _normalize_token(category)
        if normalized:
            tokens.append(f"category_{normalized}")
    return tokens


def _tag_tokens(game: EnrichedGame) -> list[str]:
    tokens: list[str] = []
    for name, votes in game.tags.items():
        normalized = _normalize_token(name)
        if not normalized:
            continue

        vote_count = max(int(votes), 0)
        repeats = max(1, round(math.log1p(vote_count)))
        tokens.extend([f"tag_{normalized}"] * repeats)
    return tokens


def build_corpus(games: list[EnrichedGame]) -> list[str]:
    """Build one TF-IDF document per game from tags, genres, and categories."""

    corpus: list[str] = []
    for game in games:
        tokens = _genre_tokens(game)
        tokens.extend(_category_tokens(game))
        tokens.extend(_tag_tokens(game))

        if not tokens:
            logger.info(
                "Skipping zero-signal game from corpus appid=%s name=%s",
                game.owned.appid,
                game.owned.name,
            )
            corpus.append("")
            continue

        corpus.append(" ".join(tokens))

    return corpus


def fit_vectorizer(corpus: list[str]) -> tuple[TfidfVectorizer, sparse.csr_matrix]:
    """Fit a TF-IDF vectorizer over the game corpus."""

    vectorizer = TfidfVectorizer(sublinear_tf=True, min_df=1, lowercase=True)
    if not corpus:
        return vectorizer, sparse.csr_matrix((0, 0), dtype=float)

    if all(not document.strip() for document in corpus):
        return vectorizer, sparse.csr_matrix((len(corpus), 0), dtype=float)

    matrix = vectorizer.fit_transform(corpus)
    return vectorizer, sparse.csr_matrix(matrix)
