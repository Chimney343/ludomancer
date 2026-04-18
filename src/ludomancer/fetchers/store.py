from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx

from ludomancer.models import GameMetadata


class StoreTransportError(RuntimeError):
    """Raised when Steam Store appdetails cannot be retrieved."""


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        if isinstance(item, str):
            text = item.strip()
            if text:
                normalized.append(text)
    return normalized


def _extract_descriptions(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        if isinstance(item, dict):
            description = item.get("description")
            if isinstance(description, str):
                text = description.strip()
                if text:
                    normalized.append(text)
    return normalized


def _parse_release_date(value: Any) -> date | None:
    if not isinstance(value, dict):
        return None

    raw_date = value.get("date")
    if not isinstance(raw_date, str):
        return None

    text = raw_date.strip()
    if not text:
        return None

    for fmt in ("%d %b, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class SteamStoreClient:
    """Fetches per-app metadata from Steam Store appdetails."""

    _APPDETAILS_ENDPOINT = "https://store.steampowered.com/api/appdetails"

    def __init__(
        self,
        *,
        timeout_s: float = 15.0,
        min_interval_s: float = 1.5,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval_s = min_interval_s
        self._sleep_fn = sleep_fn
        self._time_fn = time_fn
        self._last_request_at: float | None = None

        self._client = client or httpx.Client(timeout=timeout_s)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_metadata(self, appid: int) -> GameMetadata:
        """Return normalized metadata for one appid, tolerating partial responses."""

        payload = self._request_appdetails(appid)

        app_block = payload.get(str(appid))
        if not isinstance(app_block, dict):
            return self._empty_metadata(appid)

        if app_block.get("success") is not True:
            return self._empty_metadata(appid)

        raw_data = app_block.get("data")
        if not isinstance(raw_data, dict):
            return self._empty_metadata(appid)

        return GameMetadata(
            appid=appid,
            genres=_extract_descriptions(raw_data.get("genres")),
            categories=_extract_descriptions(raw_data.get("categories")),
            release_date=_parse_release_date(raw_data.get("release_date")),
            developers=_normalize_text_list(raw_data.get("developers")),
            publishers=_normalize_text_list(raw_data.get("publishers")),
            header_image_url=_as_optional_string(raw_data.get("header_image")),
            fetched_at=_now_utc(),
        )

    def _request_appdetails(self, appid: int) -> dict[str, Any]:
        params = {"appids": appid, "l": "english"}

        for attempt in range(2):
            self._respect_pacing()
            try:
                response = self._client.get(self._APPDETAILS_ENDPOINT, params=params)
            except (httpx.TransportError, httpx.TimeoutException) as error:
                raise StoreTransportError("Steam Store appdetails request failed.") from error

            if response.status_code == 429:
                if attempt == 0:
                    self._sleep_fn(300.0)
                    continue
                raise StoreTransportError("Steam Store rate limit persisted after cooldown.")

            if response.status_code >= 400:
                details = response.text.strip()
                raise StoreTransportError(
                    "Steam Store appdetails failed with "
                    f"HTTP {response.status_code}: {details[:300]}"
                )

            try:
                payload = response.json()
            except ValueError as error:
                raise StoreTransportError("Steam Store appdetails returned invalid JSON.") from error

            if not isinstance(payload, dict):
                raise StoreTransportError("Steam Store appdetails returned a non-object payload.")

            return payload

        raise StoreTransportError("Steam Store appdetails request failed unexpectedly.")

    def _respect_pacing(self) -> None:
        now = self._time_fn()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            wait_for = self._min_interval_s - elapsed
            if wait_for > 0:
                self._sleep_fn(wait_for)
                now = self._time_fn()
        self._last_request_at = now

    @staticmethod
    def _empty_metadata(appid: int) -> GameMetadata:
        return GameMetadata(appid=appid, fetched_at=_now_utc())


def _as_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None
