"""Structural and sanity checks. Errors block ingestion; warnings are recorded only.

Thresholds are grounded in measured real data: monthly Net equals Arrivals - Departures to within
1 (rounding); derived twelve-month sums match published rolling-year figures to within 3 at every
period (2001 onwards, 2026-06 and 2026-07 releases); NZ + non-NZ arrivals match total arrivals to
within 1 in every month. Countries + 'Not Stated' match total arrivals in every stored month of
the 2026-06 and 2026-07 releases (13 and 14 months, 225-230 series) to within 9, against a tolerance
of about 100, so the country tolerance applies to every month unchanged. Do not loosen a threshold
without evidence from the failing file.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from nzstats.adapters.base import Finding, ParsedBundle
from nzstats.domain import ObsStatus, Point
from nzstats.stats.periods import month_range
from nzstats.stats.rolling import rolling_by_period

NET_IDENTITY_TOLERANCE = 2.0
ROLLING_TOLERANCE = 5.0
# Both citizenship components are rounded independently, so their sum can differ from total arrivals
# by rounding alone (observed <= 1); 2 matches the net identity's allowance.
CITIZENSHIP_TOLERANCE = 2.0
MAX_REPORTED_PERIODS = 5
BIG_REVISION = 0.25
MAX_BIG_REVISION_SHARE = 0.10
REVISION_FLOOR = 100.0
PROVISIONAL_MAX_MONTHS = 16
COUNTRY_TOLERANCE_ABS = 20.0
COUNTRY_TOLERANCE_REL = 0.01
MIN_HISTORY_MONTHS = 12

MONTHLY = ("mig.m.arrivals", "mig.m.departures", "mig.m.net")
ROLLING = ("mig.ry.arrivals", "mig.ry.departures", "mig.ry.net")
CITIZENSHIP_MONTHLY = ("mig.m.arrivals.nz", "mig.m.arrivals.nonnz")
REQUIRED = (*MONTHLY, *ROLLING, *CITIZENSHIP_MONTHLY)
# Year-ended citizenship series come from a chart Stats NZ did not publish with every release (it is
# absent from the September 2025 page), so their absence is a warning and the series simply gets no
# vintage from that release.
OPTIONAL_ROLLING_CITIZENSHIP = ("mig.ry.net.nz", "mig.ry.net.nonnz")


def _listed(items: list[str]) -> str:
    """First few items for an error message, with a count of the rest."""
    shown = "; ".join(items[:MAX_REPORTED_PERIODS])
    rest = len(items) - MAX_REPORTED_PERIODS
    return f"{shown} (+{rest} more)" if rest > 0 else shown


def validate_migration(
    bundle: ParsedBundle,
    *,
    reference_period: str | None,
    previous: Mapping[str, Mapping[str, Point]],
) -> list[Finding]:
    findings: list[Finding] = []

    def error(rule: str, message: str) -> None:
        findings.append(Finding(rule, "error", message))

    by_key = {ps.definition.key: ps for ps in bundle.series}
    for key in REQUIRED:
        if key not in by_key:
            error("required_series", f"required series missing: {key}")
    for key in REQUIRED:
        if key in by_key and not by_key[key].observations:
            error("empty_series", f"required series has no observations: {key}")
    if findings:
        return findings
    for key in OPTIONAL_ROLLING_CITIZENSHIP:
        if key not in by_key:
            findings.append(
                Finding(
                    "optional_series",
                    "warning",
                    f"year-ended citizenship series {key} not published in this release",
                )
            )

    for ps in bundle.series:
        bad = [o.period for o in ps.observations if not math.isfinite(o.value)]
        if bad:
            error("finite", f"{ps.definition.key}: non-finite values at {bad[:3]}")

    values = {k: {o.period: o.value for o in ps.observations} for k, ps in by_key.items()}

    for key in (*MONTHLY, *CITIZENSHIP_MONTHLY):
        periods = sorted(values[key])
        if len(periods) < MIN_HISTORY_MONTHS:
            error("history", f"{key}: only {len(periods)} months of history")
            continue
        expected = month_range(periods[0], periods[-1])
        if len(expected) != len(periods):
            missing = sorted(set(expected) - set(periods))
            error("continuity", f"{key}: missing months, e.g. {missing[:3]}")
        if reference_period and periods[-1] != reference_period:
            error(
                "latest_period", f"{key}: latest month {periods[-1]} != release {reference_period}"
            )
    for key in ROLLING:
        if values[key] and reference_period and max(values[key]) != reference_period:
            error(
                "latest_period",
                f"{key}: latest year-ended {max(values[key])} != release {reference_period}",
            )

    arr, dep, net = (values[k] for k in MONTHLY)
    off = [
        p
        for p in sorted(set(arr) & set(dep) & set(net))
        if abs(net[p] - (arr[p] - dep[p])) > NET_IDENTITY_TOLERANCE
    ]
    if off:
        error(
            "net_identity",
            f"net != arrivals - departures (tolerance {NET_IDENTITY_TOLERANCE:g}) in "
            f"{len(off)} months, e.g. {off[:3]}",
        )

    for direction in ("arrivals", "departures", "net"):
        published = values[f"mig.ry.{direction}"]
        derived = rolling_by_period(values[f"mig.m.{direction}"], 12)
        if not published:
            continue
        latest = max(published)
        if latest not in derived:
            error("rolling_check", f"cannot derive year ended {latest} for {direction}")
        # Earlier periods without a complete monthly window cannot be checked and are skipped.
        off = [
            p
            for p in sorted(published)
            if p in derived and abs(published[p] - derived[p]) > ROLLING_TOLERANCE
        ]
        if off:
            detail = _listed(
                [
                    f"{p}: published {published[p]:g} vs derived {derived[p]:g} "
                    f"(diff {published[p] - derived[p]:+g})"
                    for p in off
                ]
            )
            error(
                "rolling_check",
                f"{direction}: {len(off)} published year-ended values differ from the sum of twelve "
                f"monthly estimates by more than {ROLLING_TOLERANCE:g}: {detail}",
            )

    nz, nonnz = (values[k] for k in CITIZENSHIP_MONTHLY)
    off = [
        p
        for p in sorted(set(nz) & set(nonnz) & set(arr))
        if abs(nz[p] + nonnz[p] - arr[p]) > CITIZENSHIP_TOLERANCE
    ]
    if off:
        detail = _listed([f"{p}: {nz[p] + nonnz[p]:g} vs {arr[p]:g}" for p in off])
        error(
            "citizenship_sum",
            f"NZ + non-NZ arrivals != total arrivals (tolerance {CITIZENSHIP_TOLERANCE:g}) in "
            f"{len(off)} months: {detail}",
        )

    status = {o.period: o.status for o in by_key["mig.m.net"].observations}
    provisional = sorted(p for p, s in status.items() if s is ObsStatus.PROVISIONAL)
    if provisional and (
        len(provisional) > PROVISIONAL_MAX_MONTHS
        or provisional != month_range(provisional[0], provisional[-1])
        or provisional[-1] != max(status)
    ):
        findings.append(
            Finding(
                "provisional_window",
                "warning",
                f"provisional months are not the latest <= {PROVISIONAL_MAX_MONTHS} contiguous "
                f"months ({len(provisional)} provisional, spanning {provisional[0]}..{provisional[-1]})",
            )
        )

    for key in MONTHLY:
        prev = previous.get(key) or {}
        common = [p for p in values[key] if p in prev]
        if len(common) < MIN_HISTORY_MONTHS:
            continue
        big = [
            p
            for p in common
            if abs(values[key][p] - prev[p].value) / max(abs(prev[p].value), REVISION_FLOOR)
            > BIG_REVISION
        ]
        if len(big) / len(common) > MAX_BIG_REVISION_SHARE:
            error(
                "revision_plausibility",
                f"{key}: {len(big)} of {len(common)} overlapping months moved by more than "
                f"{BIG_REVISION:.0%} versus the previous vintage",
            )

    _reconcile_places(by_key, values, error)
    return findings


def _reconcile_places(by_key, values, error) -> None:
    """Countries + 'Not Stated' must add up to total arrivals in every month `rank_countries` reads.

    The ranking sums up to 36 months and a prior window of the same length from these observations,
    so a bad historical month corrupts shares and changes even when the latest month reconciles.
    Stats NZ's country file is sparse (a country with no migrants in a month has no row), so a
    missing row counts as zero, but only from the first month the file covers: earlier months are
    unknown, not zero (as in `rank_countries`). Regions are aggregates of countries and are left out
    to avoid double-counting.
    """
    arrivals = values["mig.m.arrivals"]
    latest = max(arrivals)
    place_keys = [
        k
        for k, ps in by_key.items()
        if ps.definition.category in ("migration:country", "migration:unallocated")
    ]
    if not place_keys:
        return
    country_firsts = [
        min(values[k])
        for k, ps in by_key.items()
        if ps.definition.category == "migration:country" and values[k]
    ]
    first = min(country_firsts) if country_firsts else latest
    absent: list[str] = []
    off: list[str] = []
    for period in month_range(first, latest):
        total = arrivals.get(period, 0.0)
        tolerance = max(COUNTRY_TOLERANCE_ABS, COUNTRY_TOLERANCE_REL * total)
        summed = sum(values[k].get(period, 0.0) for k in place_keys)
        if abs(summed - total) <= tolerance:
            continue
        if not any(period in values[k] for k in place_keys):
            absent.append(f"{period}: no country observations, total arrivals {total:g}")
        else:
            off.append(
                f"{period}: countries sum to {summed:g} vs total arrivals {total:g} "
                f"(diff {summed - total:+g}, tolerance {tolerance:g})"
            )
    if absent:
        error(
            "country_month_missing",
            f"country data is missing entirely for {len(absent)} months between {first} and "
            f"{latest}: {_listed(absent)}",
        )
    if off:
        error(
            "country_sum",
            f"countries (excluding regions) plus unallocated do not reconcile with total arrivals "
            f"in {len(off)} months: {_listed(off)}",
        )
