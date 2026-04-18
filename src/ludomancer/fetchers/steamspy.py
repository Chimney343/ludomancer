from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SteamSpyClient:
    """Fetches per-app tag vote counts from SteamSpy."""

    _APPDETAILS_ENDPOINT = "https://steamspy.com/api.php"

    def __init__(self, *, timeout_s: float = 15.0, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=timeout_s)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_tags(self, appid: int) -> dict[str, int]:
        """Return SteamSpy tags for one appid; returns {} on transport or parse failures."""

        params = {"request": "appdetails", "appid": appid}
        try:
            response = self._client.get(self._APPDETAILS_ENDPOINT, params=params)
            if response.status_code >= 400:
                logger.warning(
                    "SteamSpy request failed for appid=%s with HTTP %s",
                    appid,
                    response.status_code,
                )
                return {}

            payload = response.json()
            if not isinstance(payload, dict):
                logger.warning("SteamSpy returned non-object payload for appid=%s", appid)
                return {}

            return _parse_tags(payload.get("tags"))
        except (httpx.TransportError, httpx.TimeoutException) as error:
            logger.warning("SteamSpy transport failure for appid=%s: %s", appid, error)
            return {}
        except ValueError as error:
            logger.warning("SteamSpy returned invalid JSON for appid=%s: %s", appid, error)
            return {}


def _parse_tags(raw_tags: Any) -> dict[str, int]:
    if not isinstance(raw_tags, dict):
        return {}

    parsed: dict[str, int] = {}
    for raw_name, raw_votes in raw_tags.items():
        if not isinstance(raw_name, str):
            continue

        name = raw_name.strip()
        if not name:
            continue

        try:
            votes = int(raw_votes)
        except (TypeError, ValueError):
            continue

        parsed[name] = max(votes, 0)

    return parsed
