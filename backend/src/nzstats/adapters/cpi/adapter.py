"""Bounded CSV ingestion of the official CPI files and the release page's contribution charts."""

from __future__ import annotations

import csv
import io
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from typing import NoReturn

from nzstats.adapters.base import ParsedBundle, ParsedSeries
from nzstats.adapters.cpi.series import (
    CHART_GROUPS,
    CORE_KEYS,
    CROSS_CHECK,
    INDEX_FILE,
    SA_FILE,
    SLUG,
    TRADABLES_FILE,
    contribution_definition,
    identity,
)
from nzstats.clock import AKL
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus
from nzstats.sources.calendar import parse_title
from nzstats.sources.release_page import ReleasePage, classify_download
from nzstats.stats.cpi import contiguous_run, is_quarter_end

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
        return ParsedBundle(LAYOUT_VERSION, tuple(series))

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
