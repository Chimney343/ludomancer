from __future__ import annotations

import argparse
import json

from ludomancer.cache.db import get_connection
from ludomancer.cache.repository import GameRepository
from ludomancer.config import get_settings
from ludomancer.fetchers.steamspy import SteamSpyClient
from ludomancer.fetchers.store import SteamStoreClient
from ludomancer.fetchers.web_api import PrivateProfileError, SteamTransportError, SteamWebAPIClient
from ludomancer.services.library_sync import LibrarySyncService


def _print_progress(message: str, ratio: float) -> None:
    print(f"[{ratio:>6.1%}] {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for full library sync.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass TTL and re-fetch owned games from Steam Web API.",
    )
    args = parser.parse_args()

    settings = get_settings()

    conn = get_connection(settings.cache_db_path)
    web_api_client = SteamWebAPIClient(api_key=settings.steam_api_key, timeout_s=settings.http_timeout_s)
    store_client = SteamStoreClient(timeout_s=settings.http_timeout_s)
    steamspy_client = SteamSpyClient(timeout_s=settings.http_timeout_s)
    try:
        repository = GameRepository(conn)
        service = LibrarySyncService(
            repository,
            web_api_client,
            store_client,
            steamspy_client,
            settings.steam_id64,
        )
        result = service.sync(force=args.force, progress=_print_progress)
    except (PrivateProfileError, SteamTransportError) as error:
        print(f"Sync failed: {error}")
        raise SystemExit(1) from error
    finally:
        web_api_client.close()
        store_client.close()
        steamspy_client.close()
        conn.close()

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
