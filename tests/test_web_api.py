from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from ludomancer.fetchers.web_api import PrivateProfileError, SteamTransportError, SteamWebAPIClient

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _build_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 3,
) -> SteamWebAPIClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return SteamWebAPIClient(
        api_key="test-api-key",
        client=http_client,
        max_retries=max_retries,
        sleep_fn=lambda _: None,
    )


def test_get_owned_games_success_returns_owned_games() -> None:
    payload = _load_fixture("owned_games_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/IPlayerService/GetOwnedGames/v0001/")
        assert request.url.params["key"] == "test-api-key"
        assert request.url.params["steamid"] == "76561198000000000"
        assert request.url.params["include_appinfo"] == "1"
        assert request.url.params["include_played_free_games"] == "1"
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        games = client.get_owned_games("76561198000000000")
    finally:
        client.close()

    assert [game.appid for game in games] == [10, 20]
    assert games[0].name == "Counter-Strike"
    assert games[0].playtime_forever_minutes == 120
    assert games[0].playtime_2weeks_minutes == 25
    assert (
        games[0].icon_url
        == "https://media.steampowered.com/steamcommunity/public/images/apps/10/"
        "6b0312cda02f5f777efa34e8c7a6f9e1c263f0d0.jpg"
    )
    assert games[1].icon_url is None


def test_get_owned_games_private_profile_raises_error() -> None:
    payload = _load_fixture("owned_games_private.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        with pytest.raises(PrivateProfileError):
            client.get_owned_games("76561198000000000")
    finally:
        client.close()


def test_get_owned_games_transport_error_retries_then_raises() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("network unreachable", request=request)

    client = _build_client(handler, max_retries=3)
    try:
        with pytest.raises(SteamTransportError):
            client.get_owned_games("76561198000000000")
    finally:
        client.close()

    assert attempts == 3
