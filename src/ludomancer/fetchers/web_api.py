from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from ludomancer.models import OwnedGame


class SteamWebAPIError(RuntimeError):
    """Base exception for Steam Web API failures."""


class PrivateProfileError(SteamWebAPIError):
    """Raised when Steam owned-games cannot be read due to profile visibility."""


class SteamTransportError(SteamWebAPIError):
    """Raised when Steam Web API transport or HTTP errors occur."""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_icon_url(appid: int, icon_hash: Any) -> str | None:
    if not icon_hash:
        return None
    return (
        "https://media.steampowered.com/steamcommunity/public/images/apps/"
        f"{appid}/{icon_hash}.jpg"
    )


class SteamWebAPIClient:
    """Client for Steam IPlayerService endpoints used by Ludomancer."""

    _OWNED_GAMES_ENDPOINT = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 15.0,
        max_retries: int = 4,
        base_backoff_s: float = 1.0,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._base_backoff_s = base_backoff_s
        self._sleep_fn = sleep_fn
        self._client = client or httpx.Client(timeout=timeout_s)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_owned_games(self, steam_id64: str) -> list[OwnedGame]:
        """Fetch and normalize owned games for the given Steam account."""

        response_payload = self._fetch_owned_games_response(steam_id64)
        if not response_payload:
            raise PrivateProfileError("Steam profile appears private or unavailable: empty response.")

        raw_games = response_payload.get("games")
        if raw_games is None:
            raise PrivateProfileError(
                "Steam profile appears private or unavailable: no games in response."
            )
        if not isinstance(raw_games, list):
            raise SteamTransportError("Unexpected Steam payload format: 'games' must be a list.")

        games: list[OwnedGame] = []
        for game in raw_games:
            if not isinstance(game, dict):
                continue

            appid_raw = game.get("appid")
            if appid_raw is None:
                continue

            appid = _safe_int(appid_raw, default=-1)
            if appid <= 0:
                continue

            playtime_forever = _safe_int(game.get("playtime_forever"), default=0)
            playtime_2weeks = _safe_int(game.get("playtime_2weeks"), default=0)
            name = str(game.get("name") or f"App {appid}")

            games.append(
                OwnedGame(
                    appid=appid,
                    name=name,
                    playtime_forever_minutes=max(playtime_forever, 0),
                    playtime_2weeks_minutes=max(playtime_2weeks, 0),
                    icon_url=_build_icon_url(appid, game.get("img_icon_url")),
                )
            )

        return games

    def _fetch_owned_games_response(self, steam_id64: str) -> dict[str, Any]:
        params = {
            "key": self._api_key,
            "steamid": steam_id64,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        }

        response = self._request_with_retry(params)
        try:
            payload = response.json()
        except ValueError as error:
            raise SteamTransportError("Steam Web API returned invalid JSON.") from error

        if not isinstance(payload, dict):
            raise SteamTransportError("Steam Web API returned a non-object payload.")

        response_payload = payload.get("response")
        if response_payload is None:
            raise PrivateProfileError("Steam response did not include a response object.")
        if not isinstance(response_payload, dict):
            raise SteamTransportError("Steam Web API response object is not a dictionary.")

        return response_payload

    def _request_with_retry(self, params: dict[str, Any]) -> httpx.Response:
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(self._OWNED_GAMES_ENDPOINT, params=params)
            except (httpx.TransportError, httpx.TimeoutException) as error:
                if attempt >= self._max_retries:
                    raise SteamTransportError(
                        "Steam Web API request failed after retries due to transport errors."
                    ) from error
                self._sleep_before_retry(attempt)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise SteamTransportError(
                        "Steam Web API request failed after retries with "
                        f"HTTP {response.status_code}."
                    )
                self._sleep_before_retry(attempt)
                continue

            if response.status_code >= 400:
                details = response.text.strip()
                raise SteamTransportError(
                    "Steam Web API request failed with "
                    f"HTTP {response.status_code}: {details[:300]}"
                )

            return response

        raise SteamTransportError("Steam Web API request failed without a usable response.")

    def _sleep_before_retry(self, attempt: int) -> None:
        base_delay = self._base_backoff_s * (2 ** (attempt - 1))
        delay = min(base_delay + random.uniform(0, base_delay * 0.25), 60.0)
        self._sleep_fn(delay)
