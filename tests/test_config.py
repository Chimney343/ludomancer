from __future__ import annotations

import pytest
from pydantic import ValidationError

from ludomancer.config import Settings


def _clear_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("STEAM_API_KEY", "steam_api_key", "STEAM_ID64", "steam_id64"):
        monkeypatch.delenv(key, raising=False)


def test_settings_require_steam_api_key_and_steam_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_required_env(monkeypatch)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_load_required_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_required_env(monkeypatch)
    monkeypatch.setenv("STEAM_API_KEY", "  test-api-key  ")
    monkeypatch.setenv("STEAM_ID64", " 76561198000000000 ")

    settings = Settings(_env_file=None)
    assert settings.steam_api_key == "test-api-key"
    assert settings.steam_id64 == "76561198000000000"
