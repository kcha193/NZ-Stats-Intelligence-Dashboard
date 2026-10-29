"""Official outcomes for CPI forecasts (Phase 3D-B), from the Stats NZ vintages already stored. Read-only.

Only CPI is evaluated: it is the one forecast indicator whose official series this site ingests. A claim is matched
only on a stated basis (`compare.basis_of`) and a horizon that names one quarter:

- annual change (through the year) and annual average change: the unadjusted all-groups index;
- quarterly change: the seasonally adjusted index when the label says so, the unadjusted index when it says
  "unadjusted"; a quarterly change that says neither is not matched;
- anything else (a region or other part of the series, a seasonally adjusted annual change, a calendar or split year, a
  month that is not a quarter end) is not matched, with the reason.

Percentage changes are computed like Stats NZ's: from the index numbers as published, rounded half away from zero to one
decimal place. The first-published actual comes from the release whose reference period is the target quarter; when
that release is not stored, the earliest stored release holding the quarter is used and labelled as such. The latest
actual comes from the newest stored release. A target no stored release covers is pending: no other quarter stands in.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from nzstats.clock import AKL, from_utc_iso
from nzstats.research.api_models import ForecastOut
from nzstats.research.compare import basis_of, horizon_of
from nzstats.store.repo import VintageInfo, list_vintages, vintage_points

CPI_SLUG = "consumers-price-index"
NSA, SA = "cpi.index.nsa.all_groups", "cpi.index.sa.all_groups"
MEASURES = {
    "annual_change": ("Annual change (through the year)", NSA, 4),
    "annual_average_change": ("Annual average change", NSA, None),
    "quarterly_change_nsa": ("Quarterly change, unadjusted", NSA, 1),
    "quarterly_change_sa": ("Quarterly change, seasonally adjusted", SA, 1),
}
NO_SERIES = (
    "No official series for this indicator is ingested here, so the forecast cannot be evaluated."
)
_SA = re.compile(r"\bseasonally[- ]adjusted\b|\bs\.?a\.?\b", re.IGNORECASE)


_Vintage = tuple[
    VintageInfo, str | None, dict[str, float]
]  # vintage, its release's reference period, points


@dataclass(frozen=True)
class Target:
    measure: str
    quarter: str  # YYYY-MM, quarter-end month


@dataclass(frozen=True)
class Actual:
    value: float
    release: str  # the release title
    released_at: str  # UTC ISO
    first_release: bool  # from the release whose reference period is the target


@dataclass(frozen=True)
class Outcome:
    first: Actual
    latest: Actual

    @property
    def revision(self) -> float:
        return round(self.latest.value - self.first.value, 6)


def cpi_target(f: ForecastOut) -> Target | str:
    """The official measure and quarter a CPI forecast states, or why it cannot be matched."""
    if f.indicator != "cpi_inflation":
        return NO_SERIES
    basis = basis_of(f.indicator, f.indicator_label, f.horizon, f.unit)
    key = (horizon_of(f.horizon) or ("",))[0]
    if f.unit != "percent" or basis is None:
        return "The statistical basis is not stated clearly enough to match an official figure."
    base, _, part = basis.partition(":")
    if part not in ("", "unadjusted"):
        return "No official series is ingested for this part of the CPI, so it cannot be evaluated."
    kind, _, period = key.partition(":")
    if kind not in ("quarter", "year_to") or period[5:] not in ("03", "06", "09", "12"):
        return "The horizon does not name a single CPI quarter (a calendar or fiscal year, or a month), so it is not matched."
    stated_sa = bool(_SA.search(f.indicator_label)) and not part
    if base == "quarterly_change":
        if kind == "year_to":
            return "A quarterly change needs a single quarter, not a year, so it is not matched."
        if not stated_sa and part != "unadjusted":
            return "The label does not say whether the quarterly change is seasonally adjusted, so it is not matched."
        return Target("quarterly_change_sa" if stated_sa else "quarterly_change_nsa", period)
    if stated_sa:
        return "A seasonally adjusted annual change is not the official measure (Stats NZ uses the unadjusted index)."
    return Target(base, period)


def _quarters_back(quarter: str, n: int) -> str:
    y, m = int(quarter[:4]), int(quarter[5:])
    index = y * 4 + m // 3 - 1 - n
    return f"{index // 4:04d}-{(index % 4 + 1) * 3:02d}"


def _pct(now: Decimal, before: Decimal) -> float:
    change = (now / before - 1) * 100
    return float(change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def compute(measure: str, points: dict[str, float], quarter: str) -> float | None:
    """The official-style percentage change at `quarter`, or None when a needed quarter is missing."""
    _, _, lag = MEASURES[measure]
    need = (
        [quarter, *(_quarters_back(quarter, k) for k in range(1, 8))]
        if lag is None
        else [quarter, _quarters_back(quarter, lag)]
    )
    if any(q not in points for q in need):
        return None
    value = {q: Decimal(repr(points[q])) for q in need}
    if lag is not None:
        return _pct(value[quarter], value[need[1]])
    return _pct(sum(value[q] for q in need[:4]), sum(value[q] for q in need[4:]))  # type: ignore[arg-type]


def quarter_end(quarter: str) -> date:
    y, m = int(quarter[:4]), int(quarter[5:])
    return (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)


def akl_date(utc_iso: str) -> str:
    return from_utc_iso(utc_iso).astimezone(AKL).date().isoformat()


def look_ahead(published_on: str | None, quarter: str, release_utc: str | None) -> str | None:
    """Why the forecast could have known the outcome (it is then excluded), or None."""
    if not published_on:
        return "The document has no publication date, so it cannot be shown to precede the outcome."
    if release_utc is not None:
        released = akl_date(release_utc)
        if published_on >= released:
            return f"Published on or after the official figure was released ({released}), so it is not a forecast of it."
        return None
    if published_on > quarter_end(quarter).isoformat():
        return "Published after the target quarter ended, and the release date is not stored, so it may not precede the outcome."
    return None


class CpiActuals:
    """The stored CPI releases, loaded once per request.

    Two views of the same vintages, both deterministic: the first-published baseline reads each release's earliest
    stored bundle (lowest vintage id), which a later correction or re-ingest never replaces; the latest outcome reads
    each release's current bundle (the one `list_vintages` orders last). A release reverted to an earlier bundle has
    that bundle as its current one, and its earliest bundle is unchanged.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._releases = {
            r["reference_period"]: (r["title"], r["published_at"])
            for r in conn.execute(
                "SELECT reference_period, title, published_at FROM release WHERE series_slug = ?"
                " AND reference_period IS NOT NULL", (CPI_SLUG,))
        }  # fmt: skip
        reference = {r["release_key"]: r["reference_period"] for r in conn.execute(
            "SELECT release_key, reference_period FROM release WHERE series_slug = ?", (CPI_SLUG,))}  # fmt: skip
        self._first: dict[str, list[_Vintage]] = {}
        self._latest: dict[str, list[_Vintage]] = {}
        for key in (NSA, SA):
            current: dict[str, VintageInfo] = {}
            earliest: dict[str, VintageInfo] = {}
            for info in list_vintages(
                conn, key
            ):  # release order; later bundles of a release replace earlier
                current[info.release_key] = info
                held = earliest.get(info.release_key)
                if held is None or info.vintage_id < held.vintage_id:
                    earliest[info.release_key] = info
            loaded: dict[int, _Vintage] = {}

            def load(info: VintageInfo, _loaded=loaded, _key=key) -> _Vintage:
                if info.vintage_id not in _loaded:
                    _loaded[info.vintage_id] = (
                        info,
                        reference.get(info.release_key),
                        {p: pt.value for p, pt in vintage_points(conn, info.vintage_id).items()},
                    )
                return _loaded[info.vintage_id]

            self._latest[key] = [load(i) for i in current.values()]
            self._first[key] = [
                load(i)
                for i in sorted(earliest.values(), key=lambda v: (v.published_at, v.vintage_id))
            ]

    indicator = "cpi_inflation"
    official_series = NSA

    @staticmethod
    def target(f: ForecastOut) -> Target | str:
        return cpi_target(f)

    @staticmethod
    def measure_label(measure: str) -> str:
        return MEASURES[measure][0]

    def release_date(self, quarter: str) -> str | None:
        """When the release for this reference quarter was (or is scheduled to be) published, UTC."""
        found = self._releases.get(quarter)
        return found[1] if found else None

    def newest_release(self) -> tuple[str, str] | None:
        stored = self._latest[NSA]
        return (stored[-1][0].title, stored[-1][0].published_at) if stored else None

    def outcome(self, target: Target) -> Outcome | None:
        _, series, _ = MEASURES[target.measure]
        first = self._actual(self._first[series], target, earliest=True)
        latest = self._actual(self._latest[series], target, earliest=False)
        if first is None or latest is None:
            return None
        return Outcome(first, latest)

    @staticmethod
    def _actual(vintages: list[_Vintage], target: Target, *, earliest: bool) -> Actual | None:
        """The first (earliest=True) or last release in `vintages` that holds enough of the series for the target."""
        for info, reference, points in vintages if earliest else reversed(vintages):
            value = compute(target.measure, points, target.quarter)
            if value is not None:
                return Actual(value, info.title, info.published_at, reference == target.quarter)
        return None


@dataclass(frozen=True)
class StoredRelease:
    reference_period: str
    title: str
    published_at: str  # UTC ISO
    bundles: (
        int  # distinct stored bundles of the all-groups index (a correction or re-ingest adds one)
    )
    earliest_captured_at: str


def stored_cpi_releases(conn: sqlite3.Connection) -> list[StoredRelease]:
    """CPI releases with a stored all-groups vintage, oldest first (Phase 3E vintage audit; read-only).

    Only these quarters can have a genuine first-published value; every earlier quarter's "first" value is the
    earliest stored one, read from the oldest release listed here.
    """
    rows = conn.execute(
        "SELECT r.reference_period, r.title, r.published_at, COUNT(v.id) AS bundles,"
        " MIN(v.captured_at) AS earliest FROM release r JOIN vintage v ON v.release_id = r.id"
        " JOIN series s ON s.id = v.series_id WHERE r.series_slug = ? AND s.key = ?"
        " AND r.reference_period IS NOT NULL GROUP BY r.id ORDER BY r.reference_period",
        (CPI_SLUG, NSA),
    ).fetchall()
    return [StoredRelease(r["reference_period"], r["title"], r["published_at"], r["bundles"], r["earliest"])
            for r in rows]  # fmt: skip
