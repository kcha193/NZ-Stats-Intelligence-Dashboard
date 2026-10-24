"""Check exported payloads against the database they came from, observation by observation."""

from __future__ import annotations

import sqlite3
from typing import Any

from nzstats.store import repo


def _point_tuple(p: dict[str, Any]) -> tuple:
    return (p["period"], p["value"], p["status"], p["std_error"], p["released_in"])


def _series_problems(conn: sqlite3.Connection, key: str, points: list[dict[str, Any]]) -> list[str]:
    vintages = repo.list_vintages(conn, key)
    if not vintages:
        return [f"{key}: published but has no vintage in the database"]
    stored = repo.vintage_observations(conn, vintages[-1].vintage_id)
    expected = [
        (o.period, o.value, o.status.value, o.std_error, o.released_in) for o in stored.values()
    ]
    return (
        []
        if sorted(map(_point_tuple, points)) == sorted(expected)
        else [
            f"{key}: published points differ from the latest stored vintage "
            f"({len(points)} published, {len(expected)} stored)"
        ]
    )


def _matches_some_vintage(conn: sqlite3.Connection, key: str, values: dict[str, float]) -> bool:
    """Whether one stored vintage of `key` holds exactly these values for these periods."""
    for info in repo.list_vintages(conn, key):
        stored = repo.vintage_observations(conn, info.vintage_id)
        if all(p in stored and stored[p].value == v for p, v in values.items()):
            return True
    return False


def reconcile_with_database(payloads: dict[str, Any], conn: sqlite3.Connection) -> list[str]:
    problems: list[str] = []
    for path, payload in payloads.items():
        if path.startswith("series/"):
            problems += _series_problems(conn, payload["series"]["key"], payload["points"])
    for s in payloads["ect.json"]["series"]:
        key = s["series"]["key"]
        values = {p["period"]: p["value"] for p in s["points"]}
        if not _matches_some_vintage(conn, key, values):
            problems.append(f"{key}: published card-transaction values match no stored vintage")
    for s in payloads["cpi.json"]["series"]:
        values = {p["period"]: p["index"] for p in s["points"]}
        if not _matches_some_vintage(conn, s["key"], values):
            problems.append(f"{s['key']}: published index values match no stored vintage")
    stored_releases = conn.execute("SELECT COUNT(*) FROM release").fetchone()[0]
    if len(payloads["releases.json"]) != stored_releases:
        problems.append(
            f"releases: {len(payloads['releases.json'])} published, {stored_releases} stored"
        )
    return problems
