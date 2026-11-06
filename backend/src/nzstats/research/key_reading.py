"""A read-only reading of the dedicated OpenRouter key's spend, set against the local ledger (Phase 4R).

One GET to the key-metadata endpoint, which is not an inference and spends nothing. The reading reports numbers and booleans only: the key
is never printed, stored or returned, and a refused or malformed response raises a fixed message that repeats nothing from the server.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime

import httpx

from nzstats.research.pilot import PilotRefused, _get
from nzstats.research.summary_store import (
    LIFETIME_ATTEMPTS,
    LIFETIME_USD,
    lifetime_spent,
    version_attempts,
)

TOLERANCE = 1e-6


def _number(value: object) -> float | None:
    ok = type(value) in (int, float) and math.isfinite(value)
    return float(value) if ok else None  # type: ignore[arg-type]


def read_key(client: httpx.Client, key: str, conn: sqlite3.Connection) -> dict[str, object]:
    """Key metadata against the ledger. Raises PilotRefused when the key cannot be read or the answer is not what was expected."""
    if not key:
        raise PilotRefused("no key supplied")
    data = _get(client, "/key", key=key).get("data")
    if not isinstance(data, dict):
        raise PilotRefused("dedicated key metadata invalid")
    usage, limit, remaining, byok = (
        _number(data.get(k)) for k in ("usage", "limit", "limit_remaining", "byok_usage")
    )
    if None in (usage, limit, remaining, byok):
        raise PilotRefused("dedicated key metadata invalid")
    if not all(0 <= n <= LIFETIME_USD for n in (usage, limit, remaining, byok)):  # type: ignore[operator]
        raise PilotRefused("dedicated key metadata out of range")
    management, reset = data.get("is_management_key"), data.get("limit_reset")
    if type(management) is not bool or reset is not None:
        raise PilotRefused("dedicated key metadata not as expected")
    ledger = lifetime_spent(conn)
    attempts = int(
        conn.execute(
            "SELECT COUNT(*) FROM research_llm_reservation WHERE provider='openrouter'"
        ).fetchone()[0]
    )
    per_version = {
        int(r[0]): version_attempts(conn, int(r[0]))
        for r in conn.execute(
            "SELECT DISTINCT version_id FROM research_llm_reservation WHERE provider='openrouter'"
        )
    }
    return {
        "read_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "key_usage_usd": usage,
        "key_limit_usd": limit,
        "key_remaining_usd": remaining,
        "byok_usage_usd": byok,
        "management_key": management,
        "limit_reset": None,
        "ledger_usd": ledger,
        "ledger_attempts": attempts,
        "lifetime_attempts": LIFETIME_ATTEMPTS,
        "attempts_left": LIFETIME_ATTEMPTS - attempts,
        "attempts_by_version": per_version,
        "usage_matches_ledger": abs(usage - ledger) <= TOLERANCE,
        "limit_is_lifetime_cap": limit == LIFETIME_USD,
        "remaining_is_consistent": abs(remaining + usage - limit) <= TOLERANCE,
        "byok_is_zero": byok == 0,
    }
