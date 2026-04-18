from __future__ import annotations

from ludomancer.gui.recommendations_view import build_card_data
from ludomancer.models import CandidateGame, GenrePayload, LLMPayload, LLMRecommendationResponse


def test_build_card_data_excludes_selected_pick_from_alternatives() -> None:
    payload = LLMPayload(
        genres=[
            GenrePayload(
                genre="Action",
                candidates=[
                    CandidateGame(name="Action Backlog Match", top_tags=["Action", "Shooter"]),
                    CandidateGame(name="Action Backlog Mid", top_tags=["Adventure"]),
                ],
            ),
            GenrePayload(
                genre="RPG",
                candidates=[
                    CandidateGame(name="RPG Candidate", top_tags=["RPG"]),
                ],
            ),
        ]
    )
    response = LLMRecommendationResponse.model_validate(
        {
            "recommendations": [
                {
                    "genre": "Action",
                    "pick_name": "Action Backlog Match",
                    "reasoning": "Strong overlap with your played action signal.",
                },
                {
                    "genre": "RPG",
                    "pick_name": "RPG Candidate",
                    "reasoning": "Fits your RPG-heavy history.",
                },
            ]
        },
        context={"payload": payload},
    )

    cards = build_card_data(response, payload)

    assert len(cards) == 2
    assert cards[0].genre == "Action"
    assert cards[0].pick_name == "Action Backlog Match"
    assert cards[0].alternatives == [("Action Backlog Mid", ["Adventure"])]
    assert cards[1].alternatives == []


def test_build_card_data_handles_missing_payload_genre() -> None:
    payload = LLMPayload(
        genres=[
            GenrePayload(
                genre="Action",
                candidates=[
                    CandidateGame(name="Action Backlog Match", top_tags=["Action"]),
                ],
            )
        ]
    )
    response = LLMRecommendationResponse.model_validate(
        {
            "recommendations": [
                {
                    "genre": "Unknown",
                    "pick_name": "Unmapped Game",
                    "reasoning": "Still a valid object when payload context is absent.",
                }
            ]
        }
    )

    cards = build_card_data(response, payload)

    assert len(cards) == 1
    assert cards[0].genre == "Unknown"
    assert cards[0].alternatives == []
