from __future__ import annotations

from datetime import UTC, datetime, timedelta

OWNED_GAMES_TTL = timedelta(hours=24)
METADATA_TTL = timedelta(days=30)
TAGS_TTL = timedelta(days=30)


def is_fresh(fetched_at: datetime | None, ttl: timedelta) -> bool:
    """Return True when fetched_at is within ttl of current UTC time."""

    if fetched_at is None:
        return False

    normalized = fetched_at
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)

    return datetime.now(UTC) - normalized <= ttl
