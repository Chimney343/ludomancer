from __future__ import annotations

import math

import numpy as np
from scipy import sparse
from sklearn.metrics.pairwise import cosine_similarity

from ludomancer.models import EnrichedGame, GenreShortlist

PLAYED_THRESHOLD_MINUTES = 180


def classify(games: list[EnrichedGame]) -> tuple[list[EnrichedGame], list[EnrichedGame]]:
    """Split library into played and backlog games by the 3-hour threshold."""

    played: list[EnrichedGame] = []
    backlog: list[EnrichedGame] = []
    for game in games:
        if game.owned.playtime_forever_minutes >= PLAYED_THRESHOLD_MINUTES:
            played.append(game)
        else:
            backlog.append(game)
    return played, backlog


def _game_hours(game: EnrichedGame) -> float:
    return max(game.owned.playtime_forever_minutes, 0) / 60.0


def genre_centroid(
    played: list[EnrichedGame],
    genre: str | None,
    matrix: sparse.csr_matrix,
    game_index: dict[int, int],
) -> np.ndarray:
    """Compute playtime-weighted centroid for a genre or globally when genre is None."""

    feature_count = matrix.shape[1]
    if feature_count == 0:
        return np.zeros((0,), dtype=float)

    if not played:
        return np.zeros((feature_count,), dtype=float)

    vectors: list[np.ndarray] = []
    weights: list[float] = []
    for game in played:
        if genre is not None and genre not in game.metadata.genres:
            continue

        row_index = game_index.get(game.owned.appid)
        if row_index is None or row_index < 0 or row_index >= matrix.shape[0]:
            continue

        weight = math.log1p(_game_hours(game))
        if weight <= 0:
            continue

        vectors.append(matrix.getrow(row_index).toarray().ravel())
        weights.append(weight)

    if not vectors:
        if genre is None:
            return np.zeros((feature_count,), dtype=float)
        return genre_centroid(played, None, matrix, game_index)

    weighted = np.average(np.vstack(vectors), axis=0, weights=np.asarray(weights, dtype=float))
    return np.asarray(weighted, dtype=float)


def _active_genres(games: list[EnrichedGame]) -> list[str]:
    active: set[str] = set()
    for game in games:
        for genre in game.metadata.genres:
            if genre.strip():
                active.add(genre)
    return sorted(active)


def _top_signal_games(played: list[EnrichedGame], genre: str, limit: int = 3) -> list[tuple[str, float]]:
    ranked = [game for game in played if genre in game.metadata.genres]
    ranked.sort(key=lambda game: (-game.owned.playtime_forever_minutes, game.owned.name.lower()))
    return [(game.owned.name, _game_hours(game)) for game in ranked[:limit]]


def _score_candidates(
    candidates: list[EnrichedGame],
    centroid: np.ndarray,
    matrix: sparse.csr_matrix,
    game_index: dict[int, int],
) -> list[tuple[EnrichedGame, float]]:
    if not candidates:
        return []

    if centroid.size == 0 or np.linalg.norm(centroid) == 0:
        return [(candidate, 0.0) for candidate in candidates]

    rows: list[int] = []
    mapped_candidates: list[EnrichedGame] = []
    for candidate in candidates:
        row_index = game_index.get(candidate.owned.appid)
        if row_index is None or row_index < 0 or row_index >= matrix.shape[0]:
            continue
        rows.append(row_index)
        mapped_candidates.append(candidate)

    if not rows:
        return []

    candidate_matrix = matrix[rows]
    scores = cosine_similarity(candidate_matrix, centroid.reshape(1, -1)).ravel()
    return list(zip(mapped_candidates, [float(score) for score in scores], strict=True))


def recommend(
    games: list[EnrichedGame],
    matrix: sparse.csr_matrix,
    top_k_per_genre: int = 3,
) -> list[GenreShortlist]:
    """Rank backlog candidates per active genre using cosine similarity to centroids."""

    if matrix.shape[0] != len(games):
        raise ValueError("Matrix row count must match game list length.")

    if top_k_per_genre <= 0:
        return []

    played, backlog = classify(games)
    game_index = {game.owned.appid: idx for idx, game in enumerate(games)}
    global_centroid = genre_centroid(played, None, matrix, game_index)

    shortlists: list[GenreShortlist] = []
    for genre in _active_genres(games):
        backlog_in_genre = [game for game in backlog if genre in game.metadata.genres]
        if not backlog_in_genre:
            continue

        played_in_genre = [game for game in played if genre in game.metadata.genres]
        centroid = (
            genre_centroid(played, genre, matrix, game_index)
            if played_in_genre
            else global_centroid
        )

        scored_candidates = _score_candidates(backlog_in_genre, centroid, matrix, game_index)
        scored_candidates.sort(
            key=lambda item: (
                -item[1],
                item[0].owned.name.lower(),
                item[0].owned.appid,
            )
        )
        top_candidates = scored_candidates[:top_k_per_genre]
        if not top_candidates:
            continue

        shortlists.append(
            GenreShortlist(
                genre=genre,
                signal_games=_top_signal_games(played, genre, limit=3),
                candidates=[
                    (candidate.owned.appid, candidate.owned.name, score)
                    for candidate, score in top_candidates
                ],
            )
        )

    return shortlists
