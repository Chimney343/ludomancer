from __future__ import annotations

import json
from pathlib import Path

import httpx

from ludomancer.fetchers.steamspy import SteamSpyClient

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_steamspy_parses_tag_votes() -> None:
    payload = _load_fixture("steamspy_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api.php"
        assert request.url.params["request"] == "appdetails"
        assert request.url.params["appid"] == "10"
        return httpx.Response(200, json=payload)

    client = SteamSpyClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        tags = client.get_tags(10)
    finally:
        client.close()

    assert tags == {"Action": 100, "FPS": 88, "Co-op": 12}


def test_steamspy_returns_empty_dict_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    client = SteamSpyClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        tags = client.get_tags(10)
    finally:
        client.close()

    assert tags == {}


def test_steamspy_returns_empty_dict_on_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = SteamSpyClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        tags = client.get_tags(10)
    finally:
        client.close()

    assert tags == {}
