"""Bounded CSV ingestion of the official CPI files and the release page's contribution charts."""

from __future__ import annotations

import csv
import io
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from typing import NoReturn

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.cpi.series import (
    BASE_QUARTER,
    BASE_VALUE,
    CHART_GROUPS,
    CORE_KEYS,
    CROSS_CHECK,
    INDEX_FILE,
    LEVEL1_SLUGS,
    SA_FILE,
    SLUG,
    TRADABLES_FILE,
    contribution_definition,
    contribution_key,
    identity,
    supported_definitions,
)
from nzstats.clock import AKL
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, Point
from nzstats.sources.calendar import parse_title
from nzstats.sources.release_page import ReleasePage, classify_download
from nzstats.stats.cpi import annual_changes, contiguous_run, is_quarter_end, quarterly_changes
from nzstats.stats.periods import add_months

# Measured on the official Dec 2025, Mar 2026 and Jun 2026 releases (docs/data-sources/cpi.md).
CHART_PCT_TOLERANCE = 0.05  # computed vs published 1 d.p. percentage; measured max 0.0492
CONTRIBUTION_SUM_TOLERANCE_PP = 0.15  # |headline - sum of group contributions|; measured max 0.094
SA_REVISION_MATERIALITY = 0.05  # index points; smaller seasonal-adjustment differences are noise
ORDERING_TOLERANCE_PP = 0.1  # all groups vs [min, max] of tradables/non-tradables; measured 0.082
LARGE_MOVE = 0.05  # quarterly index move that warrants review
MAX_FILE = 16 * 1024 * 1024
MAX_ROWS = 150_000
LAYOUT_VERSION = "cpi-csv-v1"
HEADER = {
    "Series_reference",
    "Period",
    "Data_value",
    "STATUS",
    "UNITS",
    "Subject",
    "Group",
    "Series_title_1",
    "Series_title_2",
}
STATUS = {"FINAL": ObsStatus.FINAL, "REVISED": ObsStatus.UNKNOWN}
PERIOD = re.compile(r"[1-9][0-9]{3}\.(0[1-9]|1[0-2])")
# Group wording that marks rows we deliberately do not store.
IGNORED_GROUPS = {
    INDEX_FILE: ("Level 2", "Level 3"),
    SA_FILE: ("Level 2", "Level 3"),
    TRADABLES_FILE: ("Tradables and Non-tradables",),
}
CONTRIBUTION_TITLE = re.compile(
    r"(Quarterly|Annual) percentage point contribution to consumers price index, by group, "
    r"(January|February|March|April|May|June|July|August|September|October|November|December) "
    r"([0-9]{4}) quarter"
)
MONTHS = {
    m: f"{i:02d}"
    for i, m in enumerate(
        "January February March April May June July August September October November December".split(),
        1,
    )
}


def fail(message: str) -> NoReturn:
    raise IngestError(ErrorClass.VALIDATION_FAILED, message)


def layout(message: str) -> NoReturn:
    raise IngestError(ErrorClass.LAYOUT_CHANGED, message)


def _read(raw: bytes, label: str) -> list[dict[str, str]]:
    if len(raw) > MAX_FILE:
        fail(f"CPI {label} file exceeds size limit")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        names = reader.fieldnames
        if not names or len(names) != len(set(names)) or not HEADER <= set(names):
            layout(f"CPI {label} CSV schema changed")
        rows = []
        for n, row in enumerate(reader):
            if n >= MAX_ROWS:
                fail(f"CPI {label} file exceeds row limit")
            if None in row or None in row.values():
                layout(f"CPI {label} CSV has malformed rows")
            rows.append(row)
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"CPI {label} file cannot be decoded") from exc


class CpiAdapter:
    series_slug = SLUG
    required_downloads = (INDEX_FILE, SA_FILE, TRADABLES_FILE)
    previous_keys = CORE_KEYS
    preserve_publication_coverage = True

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle:
        if not page.title.lower().startswith("consumers price index:"):
            fail("CPI source title does not match adapter")
        reference = parse_title(page.title).reference_period
        if (
            not reference
            or not is_quarter_end(reference)
            or reference > page.published_at.astimezone(AKL).strftime("%Y-%m")
        ):
            fail("CPI reference period is incompatible with publication")
        published_month = page.published_at.astimezone(AKL).strftime("%Y-%m")
        sources = {classify_download(u): u for u in reversed(page.download_urls)}

        points: dict[str, dict[str, tuple[float, ObsStatus]]] = defaultdict(dict)
        definitions = {}
        cross: dict[str, float] = {}
        for kind in self.required_downloads:
            seen: set[tuple[str, str]] = set()
            for row in _read(files[kind], kind.removeprefix("cpi_")):
                ref = row["Series_reference"]
                found = identity(kind, ref, sources.get(kind))
                is_cross = kind == TRADABLES_FILE and ref == CROSS_CHECK
                if found is None and not is_cross:
                    if any(token in row["Group"] for token in IGNORED_GROUPS[kind]):
                        continue
                    layout(f"CPI source contains an unexpected series: {ref}")
                if found is not None:
                    definition, expected = found
                    if any(row[k] != v for k, v in expected.fields.items()) or not all(
                        t in row["Group"] for t in expected.group_tokens
                    ):
                        fail(f"CPI metadata incompatible for {ref}")
                elif row["UNITS"] != "Index" or row["Subject"] != "CPI":
                    fail(f"CPI metadata incompatible for {ref}")
                period = row["Period"]
                if not PERIOD.fullmatch(period):
                    fail("CPI period malformed")
                period = period.replace(".", "-")
                if not is_quarter_end(period):
                    fail("CPI period is not a quarter end")
                if period > published_month:
                    fail("CPI observations postdate publication")
                if (ref, period) in seen:
                    fail("CPI duplicate observation")
                seen.add((ref, period))
                status = STATUS.get(row["STATUS"])
                if status is None:
                    fail("CPI unknown observation status")
                raw = row["Data_value"]
                if raw in ("NA", ""):
                    continue  # missing, never zero
                try:
                    value = float(raw)
                except ValueError:
                    fail("CPI numeric value is invalid")
                if not math.isfinite(value) or value < 0:
                    fail("CPI numeric value is invalid")
                if value == 0:
                    continue  # the files write unpublished early history as 0
                if is_cross:
                    cross[period] = value
                    continue
                definitions[definition.key] = definition
                points[definition.key][period] = (value, status)
        stored = points.get("cpi.index.nsa.all_groups", {})
        if any(p in stored and stored[p][0] != v for p, v in cross.items()):
            fail("CPI all-groups index differs between source files")

        series = []
        for key in sorted(points):
            run = contiguous_run(points[key])
            observations = tuple(
                Observation(key, p, points[key][p][0], points[key][p][1]) for p in run
            )
            series.append(ParsedSeries(definitions[key], observations))
        series.extend(self._contributions(page, reference))
        bundle = ParsedBundle(LAYOUT_VERSION, tuple(series))
        findings = self.validate(bundle, reference_period=reference, previous={})
        if not any(f.severity == "error" for f in findings):
            findings += self._reconcile(page, bundle)
        errors = [f.message for f in findings if f.severity == "error"]
        if errors:
            fail("; ".join(errors[:5]))
        return bundle

    def _contributions(self, page: ReleasePage, reference: str) -> list[ParsedSeries]:
        out: list[ParsedSeries] = []
        horizons: set[str] = set()
        for chart in page.charts:
            if "percentage point contribution" not in chart.title.lower():
                continue
            match = CONTRIBUTION_TITLE.fullmatch(chart.title)
            if match is None:
                layout("CPI contribution chart title changed")
            horizon = "q" if match[1] == "Quarterly" else "a"
            if f"{match[3]}-{MONTHS[match[2]]}" != reference:
                fail("CPI contribution chart is for a different quarter")
            if horizon in horizons:
                fail("CPI duplicate contribution chart")
            horizons.add(horizon)
            rows = list(csv.reader(io.StringIO(chart.csv.lstrip("﻿"))))
            if (
                len(rows) != 2
                or rows[0][:1] != ["Group"]
                or rows[1][:1] != ["Percentage point contribution"]
                or len(rows[0]) != len(rows[1])
            ):
                layout("CPI contribution chart layout changed")
            slugs: list[str] = []
            for name in rows[0][1:]:
                slug = CHART_GROUPS.get(name.strip())
                if slug is None or slug in slugs:
                    fail("CPI contribution chart group is unknown or repeated")
                slugs.append(slug)
            for slug, text in zip(slugs, rows[1][1:], strict=True):
                try:
                    value = float(text)
                except ValueError:
                    fail("CPI contribution value is invalid")
                if not math.isfinite(value):
                    fail("CPI contribution value is invalid")
                definition = contribution_definition(horizon, slug)
                observation = Observation(definition.key, reference, value, ObsStatus.UNKNOWN)
                out.append(ParsedSeries(definition, (observation,)))
        return sorted(out, key=lambda s: s.definition.key)

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

        supported = supported_definitions()
        keys = [s.definition.key for s in bundle.series]
        if len(keys) != len(set(keys)):
            error("duplicates", "Duplicate CPI series")
        if not reference_period or not _is_quarter(reference_period):
            error("reference", "CPI reference period is not a quarter end")
        missing = [k for k in CORE_KEYS if k not in keys]
        if missing:
            error("coverage", f"Missing required CPI indicators: {', '.join(missing)}")
        data: dict[str, dict[str, float]] = {}
        for s in bundle.series:
            d, obs = s.definition, s.observations
            expected = supported.get(d.key)
            if expected is None or any(
                getattr(d, k) != getattr(expected, k)
                for k in ("unit", "frequency", "adjustment", "definition_id", "category")
            ):
                error("metadata", f"Incompatible CPI measurement metadata: {d.key}")
            periods = [o.period for o in obs]
            if not obs or len(periods) != len(set(periods)):
                error("duplicates", f"Empty or duplicate CPI observations: {d.key}")
                continue
            if any(add_months(a, 3) != b for a, b in zip(periods, periods[1:], strict=False)):
                error("continuity", f"CPI periods are not continuous: {d.key}")
            is_index = d.unit == "index"
            if any(
                o.series_key != d.key or not math.isfinite(o.value) or (is_index and o.value <= 0)
                for o in obs
            ):
                error("values", f"CPI observations incompatible with definition: {d.key}")
                continue
            data[d.key] = {o.period: o.value for o in obs}
            if reference_period:
                self._check_reference(d.key, max(periods), reference_period, error, warn)
            self._check_previous(d, obs, previous.get(d.key, {}), error, warn)
            if is_index and len(obs) > 1 and abs(obs[-1].value / obs[-2].value - 1) > LARGE_MOVE:
                warn("structural_change", f"Large CPI movement requires review: {d.key}")
        self._check_base(data, error)
        if reference_period and _is_quarter(reference_period):
            self._check_ordering(data, reference_period, error)
            self._check_contributions(data, reference_period, error, warn)
        return findings

    @staticmethod
    def _check_reference(key, latest, reference, error, warn) -> None:
        optional = key.startswith("cpi.index.") and key not in CORE_KEYS
        if latest > reference:
            error("reference", f"CPI latest period postdates the release reference: {key}")
        elif latest < reference:
            if optional:
                warn(
                    "optional", f"Optional CPI series is stale or discontinued: {key} ends {latest}"
                )
            else:
                error(
                    "reference", f"CPI series {key} must include the reference quarter {reference}"
                )

    @staticmethod
    def _check_previous(d, obs, prior, error, warn) -> None:
        if not prior:
            return
        current = {o.period: o.value for o in obs}
        lost = set(prior) - set(current)
        if lost:
            error(
                "coverage",
                f"CPI published period coverage lost for {d.key}: {len(lost)} missing periods "
                f"({min(lost)} to {max(lost)})",
            )
        threshold = SA_REVISION_MATERIALITY if d.adjustment.value == "seasonally_adjusted" else 1e-9
        if any(abs(prior[p].value - current[p]) > threshold for p in set(prior) & set(current)):
            warn("revisions", f"Historical revisions captured: {d.key}")

    @staticmethod
    def _check_base(data, error) -> None:
        for slug in ("all_groups", *LEVEL1_SLUGS):
            level = data.get(f"cpi.index.nsa.{slug}", {}).get(BASE_QUARTER)
            if level != BASE_VALUE:
                error(
                    "base",
                    f"CPI index base changed: {slug} is {level} at {BASE_QUARTER}, expected {BASE_VALUE:g}",
                )

    @staticmethod
    def _check_ordering(data, reference, error) -> None:
        names = ("all_groups", "tradables", "non_tradables")
        levels = [data.get(f"cpi.index.nsa.{n}") for n in names]
        if not all(levels):
            return
        for change in (quarterly_changes, annual_changes):
            try:
                a, t, n = (change(lv).get(reference) for lv in levels)
            except ValueError:
                return
            if None in (a, t, n):
                error("ordering", "CPI tradables reconciliation cannot be checked")
            elif not min(t, n) - ORDERING_TOLERANCE_PP <= a <= max(t, n) + ORDERING_TOLERANCE_PP:
                error(
                    "ordering",
                    "CPI all-groups change lies outside its tradables/non-tradables components",
                )

    @staticmethod
    def _check_contributions(data, reference, error, warn) -> None:
        headline = data.get("cpi.index.nsa.all_groups", {})
        for horizon, change, label in (
            ("q", quarterly_changes, "quarterly"),
            ("a", annual_changes, "annual"),
        ):
            present = [s for s in LEVEL1_SLUGS if contribution_key(horizon, s) in data]
            if not present:
                warn(
                    "contribution", f"CPI {label} contributions were not published in this release"
                )
                continue
            if len(present) != len(LEVEL1_SLUGS):
                error("contribution", f"CPI {label} contributions do not cover the 11 groups")
                continue
            total = sum(data[contribution_key(horizon, s)][reference] for s in present)
            try:
                expected = change(headline).get(reference)
            except ValueError:
                expected = None
            if expected is not None and abs(expected - total) > CONTRIBUTION_SUM_TOLERANCE_PP:
                error(
                    "contribution",
                    f"CPI {label} contributions do not reconcile with the headline change",
                )

    def _reconcile(self, page: ReleasePage, bundle: ParsedBundle) -> list[Finding]:
        levels = {
            s.definition.key: {o.period: o.value for o in s.observations} for s in bundle.series
        }
        findings: list[Finding] = []
        found: set[tuple[str, int]] = set()
        for chart in page.charts:
            if not chart.csv.startswith("Quarter,"):
                continue
            rows = list(csv.reader(io.StringIO(chart.csv)))
            for row in rows[1:]:
                target = PERCENT_ROWS.get(row[0].strip().lower()) if row else None
                if target is None:
                    continue
                slug, lag = target
                found.add(target)
                changes = (quarterly_changes if lag == 3 else annual_changes)(
                    levels[f"cpi.index.nsa.{slug}"]
                )
                for label, text in zip(rows[0][1:], row[1:], strict=False):
                    if text == "":
                        continue
                    period = _quarter_label(label)
                    try:
                        published = float(text)
                    except ValueError:
                        layout("CPI percentage chart value is not numeric")
                    computed = changes.get(period)
                    if computed is None or not math.isfinite(published):
                        findings.append(
                            Finding(
                                "reconcile", "error", f"CPI {slug} {period} cannot be reconciled"
                            )
                        )
                    elif abs(computed - published) > CHART_PCT_TOLERANCE + 1e-9:
                        findings.append(
                            Finding(
                                "reconcile",
                                "error",
                                f"CPI published percentage does not reconcile with levels: {slug} {period}",
                            )
                        )
        if found != REQUIRED_PERCENT_ROWS:
            layout("CPI percentage chart rows are missing or renamed")
        return findings


PERCENT_ROWS = {
    "cpi all groups (quarterly)": ("all_groups", 3),
    "cpi all groups (annual)": ("all_groups", 12),
    "tradeables (annual)": ("tradables", 12),
    "tradables (annual)": ("tradables", 12),
    "non-tradeables (annual)": ("non_tradables", 12),
    "non-tradables (annual)": ("non_tradables", 12),
}
REQUIRED_PERCENT_ROWS = set(PERCENT_ROWS.values())
QUARTER_LABEL = re.compile(r"(Mar|Jun|Sept?|Dec)-([0-9]{2})")
LABEL_MONTH = {"Mar": "03", "Jun": "06", "Sep": "09", "Sept": "09", "Dec": "12"}


def _quarter_label(label: str) -> str:
    match = QUARTER_LABEL.fullmatch(label.strip())
    if match is None:
        layout("CPI percentage chart quarter label changed")
    return f"20{match[2]}-{LABEL_MONTH[match[1]]}"


def _is_quarter(period: str) -> bool:
    try:
        return is_quarter_end(period)
    except ValueError:
        return False
