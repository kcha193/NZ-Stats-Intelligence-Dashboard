"""Bounded CSV ingestion of Stats NZ's quarterly GDP release, reconciled against its own release page."""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import NoReturn

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.gdp.series import (
    BY_KEY,
    BY_REFERENCE,
    CSV_FILE,
    KEYS,
    PAGE_CHARTS,
    PINNED,
    RECONCILE,
    SLUG,
    SUBJECT,
)
from nzstats.clock import AKL
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, Point
from nzstats.sources.calendar import parse_title
from nzstats.sources.release_page import ReleasePage, pick_downloads
from nzstats.stats.cpi import annual_changes, is_quarter_end, quarterly_changes
from nzstats.stats.gdp import annual_average_changes
from nzstats.stats.periods import add_months

LAYOUT_VERSION = "gdp-csv-v1"
MAX_FILE = 48 * 1024 * 1024  # the real file is 21 MB
MAX_ROWS = 250_000  # the real file has 98,547
# |change computed from the stored levels - published 1 d.p. change|; measured max 0.0533 (expenditure q/q,
# 1989-03) across the March and June 2026 releases (docs/data-sources/gdp.md).
RECONCILE_TOLERANCE_PP = 0.06
# A quarterly growth rate revised by more than this between releases is flagged for review (never blocked).
LARGE_REVISION_PP = 1.0
LEVEL_REVISION_MATERIALITY = 0.5  # NZ$ million: published levels are integers
HEADER = (
    "Series_reference",
    "Period",
    "Data_value",
    "STATUS",
    "UNITS",
    "MAGNITUDE",
    "Subject",
    "Group",
    "Series_title_1",
    "Series_title_2",
    "Series_title_3",
    "Series_title_4",
    "Series_title_5",
)
STATUS = {"FINAL": ObsStatus.FINAL, "REVISED": ObsStatus.UNKNOWN}
PERIOD = re.compile(r"[1-9][0-9]{3}\.(0[1-9]|1[0-2])")
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
           "oct": 10, "nov": 11, "dec": 12}  # fmt: skip
_CHART_LONG = re.compile(r"([A-Za-z]{3,4}) ([0-9]{4})")  # "Dec 2022" (June 2026 release)
_CHART_SHORT = re.compile(r"([A-Za-z]{3,4})-([0-9]{2})")  # "Sept-22" (March 2026 release)


def fail(message: str) -> NoReturn:
    raise IngestError(ErrorClass.VALIDATION_FAILED, message)


def layout(message: str) -> NoReturn:
    raise IngestError(ErrorClass.LAYOUT_CHANGED, message)


def chart_quarter(label: str) -> str:
    """A release page chart's quarter label as `YYYY-MM`; anything unrecognised fails closed."""
    text = label.strip()
    match = _CHART_LONG.fullmatch(text) or _CHART_SHORT.fullmatch(text)
    month = _MONTHS.get(match.group(1).lower()) if match else None
    if match is None or month is None or month % 3:
        layout(f"GDP chart period label not recognised: {text[:20]!r}")
    year = match.group(2)
    return f"{year if len(year) == 4 else '20' + year}-{month:02d}"


def check_page_charts(page: ReleasePage, data: Mapping[str, Mapping[str, float]]) -> int:
    """Each growth chart on the release page must equal its published series at every quarter it shows.

    Returns the number of values compared. This is the guard against labelling annual average growth (the page's
    "Annual growth") as the annual change of a quarter, or the reverse.
    """
    compared = 0
    for title, key in PAGE_CHARTS.items():
        chart = next((c for c in page.charts if c.title.strip() == title), None)
        if chart is None:
            layout(f"GDP release page has no {title!r} chart")
        rows = list(csv.reader(io.StringIO(chart.csv.strip())))
        if len(rows) != 2 or len(rows[0]) != len(rows[1]) or len(rows[0]) < 5:
            layout(f"GDP {title!r} chart layout changed")
        published = data.get(key, {})
        for label, text in zip(rows[0][1:], rows[1][1:], strict=True):
            quarter = chart_quarter(label)
            try:
                shown = float(text)
            except ValueError:
                layout(f"GDP {title!r} chart value is not a number")
            if quarter not in published or abs(published[quarter] - shown) > 1e-9:
                fail(f"GDP {title!r} chart does not match {key} at {quarter}")
            compared += 1
    return compared


def _rows(raw: bytes) -> list[dict[str, str]]:
    if len(raw) > MAX_FILE:
        fail("GDP file exceeds size limit")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if tuple(reader.fieldnames or ()) != HEADER:
            layout("GDP CSV schema changed")
        rows = []
        for n, row in enumerate(reader):
            if n >= MAX_ROWS:
                fail("GDP file exceeds row limit")
            if None in row or None in row.values():
                layout("GDP CSV has malformed rows")
            rows.append(row)
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "GDP file cannot be decoded") from exc


def _value(text: str, ref: str) -> float:
    try:
        value = float(text)
    except ValueError:
        fail(f"GDP value is not a number: {ref}")
    if not math.isfinite(value):
        fail(f"GDP value is not finite: {ref}")
    return value


class GdpAdapter:
    series_slug = SLUG
    required_downloads = (CSV_FILE,)
    previous_keys = KEYS
    preserve_publication_coverage = True

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle:
        if not page.title.lower().startswith("gross domestic product:"):
            fail("GDP source title does not match adapter")
        reference = parse_title(page.title).reference_period
        published_month = page.published_at.astimezone(AKL).strftime("%Y-%m")
        if not reference or not is_quarter_end(reference) or reference > published_month:
            fail("GDP reference period is incompatible with publication")
        source = pick_downloads(page.download_urls, self.required_downloads).get(CSV_FILE)

        found: dict[str, dict[str, Observation]] = {key: {} for key in KEYS}
        blanks: dict[str, set[str]] = {key: set() for key in KEYS}
        for row in _rows(files[CSV_FILE]):
            pinned = BY_REFERENCE.get(row["Series_reference"])
            if pinned is None:
                continue
            ref, key, e = pinned.reference, pinned.definition.key, pinned.expected
            if (
                row["UNITS"],
                row["MAGNITUDE"],
                row["Subject"],
                row["Group"],
                row["Series_title_1"],
                row["Series_title_2"],
                row["Series_title_3"],
                row["Series_title_4"],
                row["Series_title_5"],
            ) != (e.units, e.magnitude, SUBJECT, e.group, e.title_1, e.title_2, "", "", ""):
                fail(f"GDP metadata incompatible for {ref}")
            if not PERIOD.fullmatch(row["Period"]):
                fail(f"GDP period malformed: {ref}")
            period = row["Period"].replace(".", "-")
            if not is_quarter_end(period):
                fail(f"GDP period is not a quarter end: {ref}")
            if period > reference:
                fail(f"GDP period postdates the release reference: {ref}")
            if period in found[key] or period in blanks[key]:
                fail(f"GDP duplicate period for {ref}")
            if row["STATUS"] not in STATUS:
                fail(f"GDP status not recognised: {ref}")
            if row["Data_value"] == "":
                blanks[key].add(period)
                continue
            found[key][period] = Observation(
                key, period, _value(row["Data_value"], ref), STATUS[row["STATUS"]]
            )

        data = {key: {p: o.value for p, o in obs.items()} for key, obs in found.items()}
        check_page_charts(page, data)
        warnings = []
        series = []
        for p in PINNED:
            key = p.definition.key
            obs = found[key]
            if not obs:
                continue  # validation reports the missing series
            first = min(obs)
            # Blanks before a series starts are history Stats NZ does not publish; a blank after it starts is a
            # gap, kept out of the observations so the continuity check fails.
            leading = {b for b in blanks[key] if b < first}
            if leading:
                warnings.append(
                    f"{key}: {len(leading)} leading quarters unpublished before {first}"
                )
            definition = (
                p.definition if source is None else replace(p.definition, source_url=source)
            )
            series.append(ParsedSeries(definition, tuple(obs[period] for period in sorted(obs))))
        return ParsedBundle(LAYOUT_VERSION, tuple(series), tuple(warnings))

    def validate(
        self,
        bundle: ParsedBundle,
        *,
        reference_period: str | None,
        previous: Mapping[str, Mapping[str, Point]],
    ) -> list[Finding]:
        findings: list[Finding] = []

        def error(rule: str, message: str) -> None:
            findings.append(Finding(rule, "error", message))

        def warn(rule: str, message: str) -> None:
            findings.append(Finding(rule, "warning", message))

        keys = [s.definition.key for s in bundle.series]
        if len(keys) != len(set(keys)):
            error("duplicates", "Duplicate GDP series")
        missing = [k for k in KEYS if k not in keys]
        if missing:
            error("coverage", f"Missing required GDP series: {', '.join(missing)}")
        if not reference_period or not is_quarter_end(reference_period):
            error("reference", "GDP reference period is not a quarter end")
        data: dict[str, dict[str, float]] = {}
        for s in bundle.series:
            d, obs = s.definition, s.observations
            expected = BY_KEY.get(d.key)
            if expected is None or any(
                getattr(d, f) != getattr(expected.definition, f)
                for f in ("unit", "frequency", "adjustment", "definition_id", "category")
            ):
                error("metadata", f"Incompatible GDP measurement metadata: {d.key}")
                continue
            periods = [o.period for o in obs]
            if not obs or len(periods) != len(set(periods)):
                error("duplicates", f"Empty or duplicate GDP observations: {d.key}")
                continue
            if any(add_months(a, 3) != b for a, b in zip(periods, periods[1:], strict=False)):
                error("continuity", f"GDP periods are not continuous: {d.key}")
            if any(not math.isfinite(o.value) for o in obs) or (
                d.unit != "percent" and any(o.value <= 0 for o in obs)
            ):
                error("values", f"GDP observations incompatible with definition: {d.key}")
                continue
            data[d.key] = {o.period: o.value for o in obs}
            if reference_period and max(periods) != reference_period:
                error(
                    "reference",
                    f"GDP series {d.key} must end at the reference quarter {reference_period}",
                )
            _check_previous(d.key, d.unit, data[d.key], previous.get(d.key, {}), error, warn)
        _reconcile(data, error)
        return findings


def _check_previous(
    key: str,
    unit: str,
    current: Mapping[str, float],
    prior: Mapping[str, Point],
    error: Callable[[str, str], None],
    warn: Callable[[str, str], None],
) -> None:
    if not prior:
        return
    lost = set(prior) - set(current)
    if lost:
        error(
            "coverage",
            f"GDP published period coverage lost for {key}: {len(lost)} missing periods "
            f"({min(lost)} to {max(lost)})",
        )
    common = set(prior) & set(current)
    materiality = 1e-9 if unit == "percent" else LEVEL_REVISION_MATERIALITY
    revised = sorted(p for p in common if abs(prior[p].value - current[p]) > materiality)
    if revised:
        warn("revisions", f"Historical revisions captured: {key} ({len(revised)} quarters)")
    if key.endswith("pct_qoq"):
        large = [p for p in revised if abs(prior[p].value - current[p]) > LARGE_REVISION_PP]
        if large:
            warn(
                "large_revision",
                f"Quarterly growth revised by more than {LARGE_REVISION_PP} pp: {key} {large}",
            )


_CHANGES = {"qoq": quarterly_changes, "yoy": annual_changes, "annual_avg": annual_average_changes}


def _reconcile(data: Mapping[str, Mapping[str, float]], error: Callable[[str, str], None]) -> None:
    """Every published percentage must agree with the change computed from the same file's levels."""
    for pct_key, (level_key, kind) in RECONCILE.items():
        published, levels = data.get(pct_key), data.get(level_key)
        if not published or not levels:
            continue
        computed = _CHANGES[kind](levels)
        common = sorted(set(published) & set(computed))
        bad = [p for p in common if abs(computed[p] - published[p]) > RECONCILE_TOLERANCE_PP]
        if not common or bad:
            error(
                "reconcile",
                f"Published {pct_key} does not reconcile with {level_key}"
                + (f" at {', '.join(bad[:3])}" if bad else ": no common quarters"),
            )
