from __future__ import annotations

from ludomancer.models import (
    CandidateGame,
    EnrichedGame,
    GenrePayload,
    GenreShortlist,
    LLMPayload,
    ReferenceGame,
)


def _top_tags(tags: dict[str, int], limit: int = 5) -> list[str]:
    ordered = sorted(tags.items(), key=lambda item: (-item[1], item[0].lower()))
    return [name for name, _votes in ordered[:limit]]


def _rank_played_games(games: list[EnrichedGame]) -> list[EnrichedGame]:
    ranked = list(games)
    ranked.sort(key=lambda game: (-game.owned.playtime_forever_minutes, game.owned.name.lower()))
    return ranked


def _reference_games_for_genre(genre: str, played: list[EnrichedGame]) -> list[EnrichedGame]:
    genre_played = [game for game in played if genre in game.metadata.genres]
    if genre_played:
        return _rank_played_games(genre_played)[:3]
    return _rank_played_games(played)[:3]


def build_llm_payload(
    shortlists: list[GenreShortlist],
    played: list[EnrichedGame],
    all_games: list[EnrichedGame] | None = None,
) -> LLMPayload:
    """Build a compact payload for the LLM from shortlist and played signal."""

    game_pool = all_games if all_games is not None else played
    games_by_appid = {game.owned.appid: game for game in game_pool}

    genre_payloads: list[GenrePayload] = []
    for shortlist in shortlists:
        references = [
            ReferenceGame(
                name=game.owned.name,
                hours=game.owned.playtime_forever_minutes / 60.0,
                top_tags=_top_tags(game.tags),
            )
            for game in _reference_games_for_genre(shortlist.genre, played)
        ]

        candidates: list[CandidateGame] = []
        for appid, name, _score in shortlist.candidates[:3]:
            game = games_by_appid.get(appid)
            tags = game.tags if game else {}
            candidates.append(CandidateGame(name=name, top_tags=_top_tags(tags)))

        if not candidates:
            continue

        genre_payloads.append(
            GenrePayload(
                genre=shortlist.genre,
                reference_games=references,
                candidates=candidates,
            )
        )

    return LLMPayload(genres=genre_payloads)
