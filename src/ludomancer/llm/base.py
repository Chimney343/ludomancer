from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Protocol

from pydantic import ValidationError

from ludomancer.config import Settings
from ludomancer.models import LLMPayload, LLMRecommendationResponse

SYSTEM_PROMPT = (
    "You are a game-backlog curator. The user owns a Steam library and has hundreds of "
    "hours in some games but under 3 hours in others - their \"backlog\". For each genre "
    "you are given, you will see (a) up to 3 games the user has clearly enjoyed in that "
    "genre or elsewhere (\"reference games\") and (b) up to 3 candidate backlog games "
    "pre-ranked by content similarity. Your job: for each genre, pick exactly one "
    "candidate and explain in 1-3 sentences why this backlog game is a natural next play "
    "given the reference games. You must pick from the provided candidates only; do not "
    "invent games. Respond with a single JSON object matching the schema below and nothing "
    "else - no prose before or after, no markdown code fences."
)


class LLMClientError(RuntimeError):
    """Raised when the provider call fails at transport/service level."""


class LLMResponseError(RuntimeError):
    """Raised when the model cannot produce a valid schema response."""


class LLMClient(Protocol):
    """Provider-agnostic recommendation interface."""

    def recommend(self, payload: LLMPayload) -> LLMRecommendationResponse:
        ...


def build_user_prompt(payload: LLMPayload) -> str:
    """Render the Phase 5 user prompt from payload data."""

    lines = [
        "LIBRARY ANALYSIS",
        "================",
        "",
        "For each genre below, pick one candidate game the user should play next from their backlog.",
        "",
    ]

    for genre_payload in payload.genres:
        lines.append(f"GENRE: {genre_payload.genre}")
        lines.append("")
        lines.append("Reference games (user's hours played in parens):")
        if genre_payload.reference_games:
            for reference in genre_payload.reference_games:
                tags = ", ".join(reference.top_tags) if reference.top_tags else "none"
                lines.append(f"- {reference.name} ({reference.hours:.0f}h) - tags: {tags}")
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Backlog candidates (pre-ranked by content similarity):")
        if genre_payload.candidates:
            for candidate in genre_payload.candidates:
                tags = ", ".join(candidate.top_tags) if candidate.top_tags else "none"
                lines.append(f"- {candidate.name} - tags: {tags}")
        else:
            lines.append("- none")
        lines.append("")

    lines.extend(
        [
            "Respond with JSON matching this schema:",
            "{",
            '  "recommendations": [',
            '    {"genre": "<genre>", "pick_name": "<exact name from candidates>", "reasoning": "<1-3 sentences>"}',
            "  ]",
            "}",
        ]
    )
    return "\n".join(lines)


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(raw_text: str) -> str:
    cleaned = _strip_markdown_fences(raw_text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Model response does not contain a JSON object.")
    return cleaned[start : end + 1]


def _validate_response(raw_text: str, payload: LLMPayload) -> LLMRecommendationResponse:
    json_text = _extract_json_object(raw_text)
    json.loads(json_text)
    return LLMRecommendationResponse.model_validate_json(json_text, context={"payload": payload})


def _short_error(error: Exception) -> str:
    message = str(error).strip().replace("\n", " ")
    if len(message) <= 300:
        return message
    return f"{message[:297]}..."


def recommend_with_one_retry(
    payload: LLMPayload,
    invoke: Callable[[list[dict[str, str]]], str],
) -> LLMRecommendationResponse:
    """Run one request and one correction retry when the schema is invalid."""

    prompt = build_user_prompt(payload)
    first_messages = [{"role": "user", "content": prompt}]

    first_response = invoke(first_messages)
    try:
        return _validate_response(first_response, payload)
    except (JSONDecodeError, ValidationError, ValueError) as first_error:
        correction_prompt = (
            "Your previous response did not match the schema. Return only a valid JSON object. "
            f"Error: {_short_error(first_error)}"
        )
        retry_messages = [
            *first_messages,
            {"role": "assistant", "content": first_response},
            {"role": "user", "content": correction_prompt},
        ]

    retry_response = invoke(retry_messages)
    try:
        return _validate_response(retry_response, payload)
    except (JSONDecodeError, ValidationError, ValueError) as second_error:
        raise LLMResponseError(
            "Model response failed schema validation after one correction retry."
        ) from second_error


@dataclass
class _FallbackLLMClient:
    primary: LLMClient | None
    fallback: LLMClient | None

    def __post_init__(self) -> None:
        self._active = "primary"

    def recommend(self, payload: LLMPayload) -> LLMRecommendationResponse:
        if self._active == "fallback":
            if self.fallback is None:
                raise LLMClientError("No fallback LLM provider is configured.")
            return self.fallback.recommend(payload)

        if self.primary is None:
            if self.fallback is None:
                raise LLMClientError("No LLM provider is configured.")
            self._active = "fallback"
            return self.fallback.recommend(payload)

        try:
            return self.primary.recommend(payload)
        except LLMClientError:
            if self.fallback is None:
                raise
            self._active = "fallback"
            return self.fallback.recommend(payload)

    def close(self) -> None:
        for client in (self.primary, self.fallback):
            close = getattr(client, "close", None)
            if callable(close):
                close()


def build_client(
    settings: Settings,
    *,
    anthropic_factory: Callable[..., LLMClient] | None = None,
    openrouter_factory: Callable[..., LLMClient] | None = None,
) -> LLMClient:
    """Build Anthropic-first client with OpenRouter fallback when configured."""

    from ludomancer.llm.anthropic_client import AnthropicLLMClient
    from ludomancer.llm.openrouter_client import OpenRouterLLMClient

    anthropic_factory = anthropic_factory or AnthropicLLMClient
    openrouter_factory = openrouter_factory or OpenRouterLLMClient

    primary: LLMClient | None = None
    fallback: LLMClient | None = None

    if settings.anthropic_api_key:
        primary = anthropic_factory(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            timeout_s=settings.http_timeout_s,
        )

    if settings.openrouter_api_key:
        openrouter_client = openrouter_factory(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            timeout_s=settings.http_timeout_s,
        )
        if primary is None:
            primary = openrouter_client
        else:
            fallback = openrouter_client

    if primary is None:
        raise LLMClientError(
            "No LLM provider configured. Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
        )

    return _FallbackLLMClient(primary=primary, fallback=fallback)


def close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()
