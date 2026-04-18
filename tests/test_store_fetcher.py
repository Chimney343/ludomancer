from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from ludomancer.fetchers.store import SteamStoreClient

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _build_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    min_interval_s: float = 0.0,
    sleep_fn: Callable[[float], None] | None = None,
    time_fn: Callable[[], float] | None = None,
) -> SteamStoreClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return SteamStoreClient(
        client=http_client,
        min_interval_s=min_interval_s,
        sleep_fn=sleep_fn or (lambda _: None),
        time_fn=time_fn or (lambda: 0.0),
    )


def test_store_success_parses_expected_metadata() -> None:
    payload = _load_fixture("store_success.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/appdetails"
        assert request.url.params["appids"] == "10"
        assert request.url.params["l"] == "english"
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        metadata = client.get_metadata(10)
    finally:
        client.close()

    assert metadata.appid == 10
    assert metadata.genres == ["Action", "Classic"]
    assert metadata.categories == ["Single-player"]
    assert metadata.release_date is not None
    assert metadata.release_date.isoformat() == "2000-11-01"
    assert metadata.developers == ["Valve"]
    assert metadata.publishers == ["Valve"]
    assert metadata.header_image_url == "https://cdn.akamai.steamstatic.com/steam/apps/10/header.jpg"


def test_store_missing_fields_returns_tolerant_defaults() -> None:
    payload = _load_fixture("store_missing_fields.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        metadata = client.get_metadata(20)
    finally:
        client.close()

    assert metadata.appid == 20
    assert metadata.genres == []
    assert metadata.categories == ["Multi-player"]
    assert metadata.release_date is None
    assert metadata.developers == []
    assert metadata.publishers == []
    assert metadata.header_image_url is None


def test_store_unsuccessful_payload_returns_empty_metadata() -> None:
    payload = _load_fixture("store_unsuccessful.json")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = _build_client(handler)
    try:
        metadata = client.get_metadata(30)
    finally:
        client.close()

    assert metadata.appid == 30
    assert metadata.genres == []
    assert metadata.categories == []
    assert metadata.developers == []
    assert metadata.publishers == []


def test_store_pacing_waits_between_calls() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def time_fn() -> float:
        return now[0]

    def sleep_fn(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        appid = request.url.params["appids"]
        return httpx.Response(
            200,
            json={
                appid: {
                    "success": True,
                    "data": {
                        "genres": [{"description": "Action"}],
                    },
                }
            },
        )

    client = _build_client(handler, min_interval_s=1.5, sleep_fn=sleep_fn, time_fn=time_fn)
    try:
        client.get_metadata(10)
        client.get_metadata(20)
    finally:
        client.close()

    assert sleeps
    assert sleeps[0] == 1.5


def test_store_429_cooldown_then_retry() -> None:
    attempts = [0]
    sleeps: list[float] = []

    def sleep_fn(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(_: httpx.Request) -> httpx.Response:
        attempts[0] += 1
        if attempts[0] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=_load_fixture("store_success.json"))

    client = _build_client(handler, min_interval_s=0.0, sleep_fn=sleep_fn)
    try:
        metadata = client.get_metadata(10)
    finally:
        client.close()

    assert metadata.appid == 10
    assert attempts[0] == 2
    assert 300.0 in sleeps
