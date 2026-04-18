from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ludomancer.llm.anthropic_client import AnthropicLLMClient
from ludomancer.llm.base import LLMClientError, LLMResponseError, build_client
from ludomancer.models import (
    CandidateGame,
    GenrePayload,
    LLMPayload,
    LLMRecommendationResponse,
    ReferenceGame,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "llm_malformed_then_corrected.json"


def _sample_payload() -> LLMPayload:
    return LLMPayload(
        genres=[
            GenrePayload(
                genre="Action",
                reference_games=[
                    ReferenceGame(
                        name="Action Hero",
                        hours=12.0,
                        top_tags=["Action", "Shooter", "Fast-Paced"],
                    )
                ],
                candidates=[
                    CandidateGame(name="Action Backlog Match", top_tags=["Action", "Combat"]),
                    CandidateGame(name="Action Backlog Mid", top_tags=["Adventure", "Platformer"]),
                ],
            )
        ]
    )


def _valid_response() -> LLMRecommendationResponse:
    payload = _sample_payload()
    return LLMRecommendationResponse.model_validate(
        {
            "recommendations": [
                {
                    "genre": "Action",
                    "pick_name": "Action Backlog Match",
                    "reasoning": "A strong stylistic match with your top played action games.",
                }
            ]
        },
        context={"payload": payload},
    )


class _FakeAnthropicMessages:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    def create(self, **_kwargs):  # noqa: ANN003
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return {"content": [{"text": self._responses[index]}]}


class _FakeAnthropicClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = _FakeAnthropicMessages(responses)


class _FailingClient:
    def __init__(self) -> None:
        self.calls = 0

    def recommend(self, _payload: LLMPayload) -> LLMRecommendationResponse:
        self.calls += 1
        raise LLMClientError("provider unavailable")


class _WorkingClient:
    def __init__(self, response: LLMRecommendationResponse) -> None:
        self.calls = 0
        self._response = response

    def recommend(self, _payload: LLMPayload) -> LLMRecommendationResponse:
        self.calls += 1
        return self._response


@dataclass
class _DummySettings:
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    openrouter_model: str = "anthropic/claude-sonnet-4.5"
    http_timeout_s: float = 15.0


def test_anthropic_client_retries_once_with_malformed_then_corrected_response_pair() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    fake_sdk = _FakeAnthropicClient([fixture["malformed"], fixture["corrected"]])
    client = AnthropicLLMClient(api_key="test", model="test-model", client=fake_sdk)

    payload = _sample_payload()
    response = client.recommend(payload)

    assert fake_sdk.messages.calls == 2
    assert response.recommendations[0].pick_name == "Action Backlog Match"


def test_anthropic_client_raises_after_second_invalid_response() -> None:
    invalid = '{"recommendations":[{"genre":"Action","pick_name":"Invalid","reasoning":"Nope"}]}'
    fake_sdk = _FakeAnthropicClient([invalid, invalid])
    client = AnthropicLLMClient(api_key="test", model="test-model", client=fake_sdk)

    with pytest.raises(LLMResponseError):
        client.recommend(_sample_payload())

    assert fake_sdk.messages.calls == 2


def test_build_client_falls_through_to_openrouter_on_anthropic_transport_failure() -> None:
    failing = _FailingClient()
    working = _WorkingClient(_valid_response())
    settings = _DummySettings(anthropic_api_key="anthropic-key", openrouter_api_key="openrouter-key")

    client = build_client(
        settings,
        anthropic_factory=lambda **_kwargs: failing,
        openrouter_factory=lambda **_kwargs: working,
    )

    payload = _sample_payload()
    first = client.recommend(payload)
    second = client.recommend(payload)

    assert first.recommendations[0].pick_name == "Action Backlog Match"
    assert second.recommendations[0].pick_name == "Action Backlog Match"
    assert failing.calls == 1
    assert working.calls == 2


def test_build_client_requires_at_least_one_provider() -> None:
    settings = _DummySettings(anthropic_api_key=None, openrouter_api_key=None)
    with pytest.raises(LLMClientError):
        build_client(settings)
