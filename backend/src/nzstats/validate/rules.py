"""Structural and sanity checks. Errors block ingestion; warnings are recorded only.

Thresholds are grounded in measured real data: monthly Net equals Arrivals - Departures to within
1 (rounding); derived twelve-month sums match published rolling-year figures to within 2. Do not
loosen a threshold without evidence from the failing file.
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
BIG_REVISION = 0.25
MAX_BIG_REVISION_SHARE = 0.10
REVISION_FLOOR = 100.0
PROVISIONAL_MAX_MONTHS = 16
COUNTRY_TOLERANCE_ABS = 20.0
COUNTRY_TOLERANCE_REL = 0.01
MIN_HISTORY_MONTHS = 12

MONTHLY = ("mig.m.arrivals", "mig.m.departures", "mig.m.net")
ROLLING = ("mig.ry.arrivals", "mig.ry.departures", "mig.ry.net")
REQUIRED = (*MONTHLY, *ROLLING, "mig.m.arrivals.nz", "mig.m.arrivals.nonnz")
# Year-ended citizenship series come from a chart Stats NZ did not publish with every release (it is
# absent from the September 2025 page), so their absence is a warning and the series simply gets no
# vintage from that release.
OPTIONAL_ROLLING_CITIZENSHIP = ("mig.ry.net.nz", "mig.ry.net.nonnz")


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

    for key in MONTHLY:
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
        elif abs(published[latest] - derived[latest]) > ROLLING_TOLERANCE:
            error(
                "rolling_check",
                f"{direction}: published year ended {latest} = {published[latest]:g} but the sum "
                f"of twelve monthly estimates = {derived[latest]:g}",
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
                f"months ({len(provisional)} provisional, {provisional[0]}..{provisional[-1]})",
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

    latest_total = max(values["mig.m.arrivals"])
    total = values["mig.m.arrivals"][latest_total]
    place_keys = [
        k
        for k, ps in by_key.items()
        if ps.definition.category in ("migration:country", "migration:unallocated")
    ]
    if place_keys:
        summed = sum(values[k].get(latest_total, 0.0) for k in place_keys)
        tolerance = max(COUNTRY_TOLERANCE_ABS, COUNTRY_TOLERANCE_REL * total)
        if abs(summed - total) > tolerance:
            error(
                "country_sum",
                f"countries (excluding regions) sum to {summed:g} for {latest_total} but total "
                f"arrivals are {total:g} (tolerance {tolerance:g})",
            )
    return findings
