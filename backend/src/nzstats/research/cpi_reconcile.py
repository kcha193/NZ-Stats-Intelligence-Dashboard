"""Reconcile the stored CPI vintages and outcomes against the official files (Phase 3F). Read-only; no request.

Two independent checks, neither of which uses the Stats NZ adapter or `outcomes.compute`:

1. Fidelity. Every stored all-groups index vintage (unadjusted and seasonally adjusted) must be reproduced exactly,
   period for period from its first stored period, by one of the official CSV files kept in `raw_artifact` (parsed here with the csv module and
   Decimal). A vintage no kept file reproduces is a discrepancy.
2. Outcomes. For each measure and quarter, the first-published and latest values the dashboard reports
   (`CpiActuals`) must equal the value calculated here from the official files of the matching releases: first from
   the earliest stored bundle of the release that holds enough of the series (labelled genuine only when it is the quarter's own release
   and the shared provenance guard supports an original-publication capture), latest from the newest release's current bundle. Rounding is half away
   from zero to one decimal place, the convention Stats NZ uses.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from nzstats.research.outcomes import CPI_SLUG, MEASURES, NSA, SA, CpiActuals, Target
from nzstats.sources.artifacts import valid_rel
from nzstats.store.repo import (
    VintageInfo,
    list_vintages,
    supports_first_publication,
    vintage_points,
)

SERIES_REF = {NSA: "CPIQ.SE9A", SA: "CPIQ.SE9SA"}
_SCAN_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class OfficialFile:
    sha256: str
    series: dict[str, dict[str, Decimal]]  # series key -> "YYYY-MM" quarter -> index number


@dataclass(frozen=True)
class VintageCheck:
    series: str
    vintage_id: int
    release_key: str
    file_sha256: str | None  # None: no kept official file reproduces this vintage


@dataclass(frozen=True)
class OutcomeCheck:
    measure: str
    quarter: str
    stored_first: float
    expected_first: float
    stored_latest: float
    expected_latest: float
    genuine_first_release: bool
    ok: bool


@dataclass
class Reconciliation:
    vintages: list[VintageCheck] = field(default_factory=list)
    outcomes: list[OutcomeCheck] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    official_files: int = 0

    @property
    def ok(self) -> bool:
        return not self.discrepancies


def parse_official(body: bytes) -> OfficialFile | None:
    """The all-groups index series of one official CSV, or None if this is not a Stats NZ CPI series file."""
    if b"Series_reference" not in body[:2048]:
        return None
    wanted = {ref: key for key, ref in SERIES_REF.items()}
    series: dict[str, dict[str, Decimal]] = {}
    try:
        for row in csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline="")):
            key = wanted.get(row.get("Series_reference", ""))
            raw = (row.get("Data_value") or "").strip()
            if key is None or raw in ("", "NA"):
                continue
            year, month = row["Period"].split(".")
            series.setdefault(key, {})[f"{year}-{month}"] = Decimal(raw)
    except (UnicodeDecodeError, KeyError, ValueError, InvalidOperation, csv.Error):
        return None
    import hashlib

    return OfficialFile(hashlib.sha256(body).hexdigest(), series) if series else None


def load_official_files(conn: sqlite3.Connection, raw_dir: Path) -> list[OfficialFile]:
    found, seen = [], set()
    for (rel,) in conn.execute("SELECT DISTINCT path FROM raw_artifact ORDER BY id"):
        path = raw_dir / rel
        if (
            rel in seen
            or not valid_rel(rel)
            or not path.is_file()
            or path.stat().st_size > _SCAN_BYTES
        ):
            continue
        seen.add(rel)
        parsed = parse_official(path.read_bytes())
        if parsed is not None:
            found.append(parsed)
    return found


def _quarter_back(quarter: str, n: int) -> str:
    y, m = int(quarter[:4]), int(quarter[5:])
    i = y * 4 + m // 3 - 1 - n
    return f"{i // 4:04d}-{(i % 4 + 1) * 3:02d}"


def _one_dp(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def expected_value(measure: str, index: dict[str, Decimal], quarter: str) -> float | None:
    """The official-definition value of `measure` for `quarter` from index numbers, or None if the data run short."""
    try:
        if measure == "annual_average_change":
            recent = sum(index[_quarter_back(quarter, k)] for k in range(4))
            earlier = sum(index[_quarter_back(quarter, k)] for k in range(4, 8))
            return _one_dp((recent / earlier - 1) * 100)
        lag = MEASURES[measure][2]
        return _one_dp((index[quarter] / index[_quarter_back(quarter, lag)] - 1) * 100)
    except KeyError:
        return None


def _matches(points: dict[str, float], official: dict[str, Decimal]) -> bool:
    """The stored series equals the file's from its first stored period onwards.

    The adapter starts a series where its definition does (the file reaches back further), so earlier periods the
    file holds may be absent; anything from the first stored period on must be present, equal and nothing extra.
    """
    if not points:
        return False
    tail = {p: v for p, v in official.items() if p >= min(points)}
    return set(points) == set(tail) and all(float(tail[p]) == v for p, v in points.items())


def reconcile(conn: sqlite3.Connection, raw_dir: Path) -> Reconciliation:
    result = Reconciliation()
    files = load_official_files(conn, raw_dir)
    result.official_files = len(files)
    reference = {
        r["release_key"]: r["reference_period"]
        for r in conn.execute(
            "SELECT release_key, reference_period FROM release WHERE series_slug = ?", (CPI_SLUG,)
        )
    }
    chain: dict[str, list[tuple[VintageInfo, dict[str, Decimal]]]] = {NSA: [], SA: []}
    window_start = ""  # the first period the newest stored unadjusted vintage holds
    for key in (NSA, SA):
        for info in list_vintages(conn, key):
            points = {p: pt.value for p, pt in vintage_points(conn, info.vintage_id).items()}
            hit = next(
                (f for f in files if key in f.series and _matches(points, f.series[key])), None
            )
            result.vintages.append(
                VintageCheck(key, info.vintage_id, info.release_key, hit.sha256 if hit else None)
            )
            if hit is None:
                result.discrepancies.append(
                    f"{key} vintage {info.vintage_id} ({info.release_key}): no kept official file reproduces it"
                )
            else:
                held = {
                    p: v for p, v in hit.series[key].items() if p >= min(points)
                }  # what the vintage holds
                chain[key].append((info, held))
                if key == NSA:
                    window_start = min(points)
    if not result.vintages:
        result.discrepancies.append("no CPI vintages are stored: there is nothing to reconcile")
    newest = chain[NSA][-1][1] if chain[NSA] else {}
    actuals = CpiActuals(conn)
    for measure, (_, series, _) in MEASURES.items():
        first = _first_per_release(chain[series])
        latest = _latest_per_release(chain[series])
        for quarter in sorted(q for q in newest if q >= window_start):
            exp_first = next(
                (
                    (i, v)
                    for i, idx in first
                    if (v := expected_value(measure, idx, quarter)) is not None
                ),
                None,
            )
            exp_latest = next(((i, v) for i, idx in reversed(latest)
                               if (v := expected_value(measure, idx, quarter)) is not None), None)  # fmt: skip
            got = actuals.outcome(Target(measure, quarter))
            if exp_first is None or exp_latest is None:
                if got is not None:
                    result.discrepancies.append(
                        f"{measure} {quarter}: reported, but the official files cannot give it"
                    )
                continue
            if got is None:
                result.discrepancies.append(
                    f"{measure} {quarter}: the official files give it, but it is not reported"
                )
                continue
            genuine = reference.get(
                exp_first[0].release_key
            ) == quarter and supports_first_publication(conn, exp_first[0])
            ok = (got.first.value, got.latest.value, got.first.first_release) == (
                exp_first[1],
                exp_latest[1],
                genuine,
            )
            result.outcomes.append(OutcomeCheck(measure, quarter, got.first.value, exp_first[1], got.latest.value,
                                                exp_latest[1], genuine, ok))  # fmt: skip
            if not ok:
                result.discrepancies.append(
                    f"{measure} {quarter}: reported first {got.first.value} / latest {got.latest.value}"
                    f" (genuine first: {got.first.first_release}); official files give {exp_first[1]} /"
                    f" {exp_latest[1]} (genuine first: {genuine})"
                )
    if result.vintages and not result.outcomes and not result.discrepancies:
        result.discrepancies.append("no outcome could be checked against the official files")
    return result


def _first_per_release(chain):
    """Each release's earliest stored bundle, in release order."""
    earliest: dict[str, tuple[VintageInfo, dict[str, Decimal]]] = {}
    for info, idx in chain:
        held = earliest.get(info.release_key)
        if held is None or info.vintage_id < held[0].vintage_id:
            earliest[info.release_key] = (info, idx)
    return sorted(earliest.values(), key=lambda t: (t[0].published_at, t[0].vintage_id))


def _latest_per_release(chain):
    """Each release's current bundle (the last in `list_vintages` order), in release order."""
    current: dict[str, tuple[VintageInfo, dict[str, Decimal]]] = {}
    for info, idx in chain:
        current[info.release_key] = (info, idx)
    return list(current.values())
