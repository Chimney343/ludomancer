from __future__ import annotations

from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, ValidationInfo, model_validator


class OwnedGame(BaseModel):
    """Owned Steam game from the Web API."""

    appid: int
    name: str
    playtime_forever_minutes: int = Field(ge=0)
    playtime_2weeks_minutes: int = Field(default=0, ge=0)
    icon_url: str | None = None


class GameMetadata(BaseModel):
    """Store metadata for one Steam app."""

    appid: int
    genres: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    release_date: date | None = None
    developers: list[str] = Field(default_factory=list)
    publishers: list[str] = Field(default_factory=list)
    header_image_url: str | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class SteamSpyTags(BaseModel):
    """SteamSpy tag vote counts for one Steam app."""

    appid: int
    tags: dict[str, int] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class EnrichedGame(BaseModel):
    """In-memory aggregate of owned game + metadata + tags."""

    owned: OwnedGame
    metadata: GameMetadata
    tags: dict[str, int] = Field(default_factory=dict)


class PlaytimeStats(BaseModel):
    """Precomputed playtime statistics for the UI."""

    total_games: int = 0
    played_games: int = 0
    backlog_games: int = 0
    total_hours: float = 0.0
    hours_by_genre: dict[str, float] = Field(default_factory=dict)
    top_played: list[tuple[str, float]] = Field(default_factory=list)


class GenreShortlist(BaseModel):
    """Top recommendation candidates for a genre."""

    genre: str
    signal_games: list[tuple[str, float]] = Field(default_factory=list)
    candidates: list[tuple[int, str, float]] = Field(default_factory=list)


class ReferenceGame(BaseModel):
    name: str
    hours: float = Field(ge=0)
    top_tags: list[str] = Field(default_factory=list)


class CandidateGame(BaseModel):
    name: str
    top_tags: list[str] = Field(default_factory=list)


class GenrePayload(BaseModel):
    genre: str
    reference_games: list[ReferenceGame] = Field(default_factory=list)
    candidates: list[CandidateGame] = Field(default_factory=list)


class LLMPayload(BaseModel):
    genres: list[GenrePayload] = Field(default_factory=list)


class Recommendation(BaseModel):
    genre: str
    pick_name: str
    reasoning: str = Field(min_length=1, max_length=500)


class LLMRecommendationResponse(BaseModel):
    recommendations: list[Recommendation]

    @model_validator(mode="after")
    def validate_with_payload(self, info: ValidationInfo) -> Self:
        """Validate genre and pick consistency when payload context is provided."""

        context = info.context or {}
        payload: LLMPayload | None = context.get("payload")
        if payload is None:
            return self

        expected_genres = [genre_payload.genre for genre_payload in payload.genres]
        expected_set = set(expected_genres)

        provided_genres = [recommendation.genre for recommendation in self.recommendations]
        provided_set = set(provided_genres)

        if provided_set != expected_set:
            missing = sorted(expected_set - provided_set)
            extras = sorted(provided_set - expected_set)
            raise ValueError(
                "Recommendations must include each payload genre exactly once "
                f"(missing={missing}, extras={extras})."
            )

        if len(provided_genres) != len(expected_set):
            raise ValueError("Recommendations must not contain duplicate genres.")

        candidates_by_genre = {
            genre_payload.genre: {candidate.name for candidate in genre_payload.candidates}
            for genre_payload in payload.genres
        }

        for recommendation in self.recommendations:
            valid_candidates = candidates_by_genre.get(recommendation.genre, set())
            if recommendation.pick_name not in valid_candidates:
                raise ValueError(
                    f"Pick '{recommendation.pick_name}' is not a valid candidate "
                    f"for genre '{recommendation.genre}'."
                )

        return self
