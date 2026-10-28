"""Bounded, streamed ingestion of the labour market statistics zip: HLFS headline series and the headline LCI.

The zip holds about 756 MB of CSV (the HLFS member alone is 423 MB), so it is never extracted: only the HLFS and LCI
members are opened, read row by row and filtered to the pinned series, under caps on the archive, each member's
declared size, the number of members and the number of rows.
"""

from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import NoReturn

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.labour.series import (
    BY_KEY,
    BY_REFERENCE,
    HEADER_REQUIRED,
    HLFS,
    KEYS,
    LCI,
    PINNED,
    SLUG,
    UNEMPLOYMENT,
    ZIP_FILE,
)
from nzstats.clock import AKL
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, Point
from nzstats.sources.calendar import parse_title
from nzstats.sources.release_page import ReleasePage, pick_downloads
from nzstats.stats.cpi import annual_changes, is_quarter_end, quarterly_changes
from nzstats.stats.periods import add_months

LAYOUT_VERSION = "labour-zip-v1"
MAX_ARCHIVE = 64 * 1024 * 1024  # the real archive is 18.6 MB
MAX_MEMBER = 1024 * 1024 * 1024  # declared uncompressed size; the real HLFS member is 423 MB
MAX_MEMBERS = 8  # files, not folders; the real archive has 4
MAX_ROWS = 2_500_000  # per member; the real HLFS member has 1,278,057
# Measured on the March (revised) and June 2026 releases over the whole history (docs/data-sources/labour-market.md):
IDENTITY_LEVEL_TOLERANCE = (
    1.5  # thousand: labour force vs employed + unemployed, three rounded values; max 1.0
)
IDENTITY_RATE_TOLERANCE_PP = 0.08  # rates recomputed from rounded levels; measured max 0.0706
LCI_TOLERANCE_PP = 0.06  # LCI changes recomputed from the integer index; measured max 0.0500
LEVEL_REVISION_MATERIALITY = 0.5  # thousand people or index points: published levels are rounded
MEMBER = {
    HLFS: re.compile(r"(?:.*/)?hlfs-[a-z]{3}[0-9]{2}qtr-[a-z]+\.csv"),
    LCI: re.compile(r"(?:.*/)?lci-[a-z]{3}[0-9]{2}qtr-[a-z]+\.csv"),
}
SKIP = {"Series_reference", "Period", "Data_value", "STATUS", "SER_NBR"}
STATUS = {"FINAL": ObsStatus.FINAL, "REVISED": ObsStatus.UNKNOWN}
PERIOD = re.compile(r"[1-9][0-9]{3}\.(0[1-9]|1[0-2])")
_MONTHS = {m: i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1
)}  # fmt: skip
_HEADLINE = re.compile(
    r"unemployment rate was ([0-9]{1,2}\.[0-9]) percent in the ([A-Z][a-z]+) ([0-9]{4}) quarter, compared with "
    r"([0-9]{1,2}\.[0-9]) percent in the ([A-Z][a-z]+) ([0-9]{4}) quarter"
)
RATES = {  # rate key: (numerator level, denominator level)
    "hlfs.rate.unemployment.sa": ("hlfs.level.unemployed.sa", "hlfs.level.labour_force.sa"),
    "hlfs.rate.employment.sa": ("hlfs.level.employed.sa", "hlfs.level.working_age_population.sa"),
    "hlfs.rate.participation.sa": (
        "hlfs.level.labour_force.sa",
        "hlfs.level.working_age_population.sa",
    ),
}
LCI_CHANGES = {"lci.all_wages.pct_qoq": quarterly_changes, "lci.all_wages.pct_yoy": annual_changes}


def fail(message: str) -> NoReturn:
    raise IngestError(ErrorClass.VALIDATION_FAILED, message)


def layout(message: str) -> NoReturn:
    raise IngestError(ErrorClass.LAYOUT_CHANGED, message)


def headline_rates(page: ReleasePage) -> dict[str, float]:
    """The unemployment rates the release page headline states, by quarter; empty if the wording differs."""
    match = _HEADLINE.search(page.headline or "")
    if match is None:
        return {}
    out = {}
    for value, month, year in (match.group(1, 2, 3), match.group(4, 5, 6)):
        if month not in _MONTHS or _MONTHS[month] % 3:
            return {}
        out[f"{year}-{_MONTHS[month]:02d}"] = float(value)
    return out


def _members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    files = [i for i in archive.infolist() if not i.is_dir()]
    if len(files) > MAX_MEMBERS:
        layout("Labour market zip has too many members")
    chosen = {}
    for survey, pattern in MEMBER.items():
        matches = [i for i in files if pattern.fullmatch(i.filename)]
        if len(matches) != 1:
            layout(f"Labour market zip must contain exactly one {survey.upper()} member")
        if matches[0].file_size > MAX_MEMBER:
            fail(f"Labour market {survey.upper()} member exceeds size limit")
        chosen[survey] = matches[0]
    return chosen


def _value(text: str, ref: str) -> float:
    try:
        value = float(text)
    except ValueError:
        fail(f"Labour market value is missing or not a number: {ref}")
    if not math.isfinite(value):
        fail(f"Labour market value is not finite: {ref}")
    return value


def _read_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, survey: str, reference: str
) -> dict[str, dict[str, Observation]]:
    found: dict[str, dict[str, Observation]] = {}
    with archive.open(info) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = next(reader, None) or []
        if len(header) != len(set(header)) or not HEADER_REQUIRED[survey] <= set(header):
            layout(f"Labour market {survey.upper()} CSV schema changed")
        col = {name: i for i, name in enumerate(header)}
        ref_i, period_i, value_i, status_i = (
            col[c] for c in ("Series_reference", "Period", "Data_value", "STATUS")
        )
        for n, row in enumerate(reader):
            if n >= MAX_ROWS:
                fail(f"Labour market {survey.upper()} member exceeds row limit")
            pinned = BY_REFERENCE.get(row[ref_i]) if len(row) > ref_i else None
            if pinned is None:
                continue
            ref = pinned.reference
            if pinned.survey != survey or len(row) != len(header):
                layout(f"Labour market row for {ref} is malformed")
            metadata = {
                h: v
                for h, v in zip(header, row, strict=True)
                if v not in ("", "NA") and h not in SKIP
            }
            if metadata != pinned.metadata:
                fail(f"Labour market metadata incompatible for {ref}")
            if not PERIOD.fullmatch(row[period_i]):
                fail(f"Labour market period malformed: {ref}")
            period = row[period_i].replace(".", "-")
            if not is_quarter_end(period) or period > reference:
                fail(f"Labour market period is not a quarter up to the reference: {ref}")
            series = found.setdefault(pinned.definition.key, {})
            if period in series:
                fail(f"Labour market duplicate period for {ref}")
            if row[status_i] not in STATUS:
                fail(f"Labour market status not recognised: {ref}")
            series[period] = Observation(
                pinned.definition.key, period, _value(row[value_i], ref), STATUS[row[status_i]]
            )
    return found


class LabourAdapter:
    series_slug = SLUG
    required_downloads = (ZIP_FILE,)
    previous_keys = KEYS
    preserve_publication_coverage = True

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle:
        if not page.title.lower().startswith("labour market statistics:"):
            fail("Labour market source title does not match adapter")
        reference = parse_title(page.title).reference_period
        published_month = page.published_at.astimezone(AKL).strftime("%Y-%m")
        if not reference or not is_quarter_end(reference) or reference > published_month:
            fail("Labour market reference period is incompatible with publication")
        raw = files[ZIP_FILE]
        if len(raw) > MAX_ARCHIVE:
            fail("Labour market zip exceeds size limit")
        found: dict[str, dict[str, Observation]] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for survey, info in _members(archive).items():
                    found.update(_read_member(archive, info, survey, reference))
        except (
            zipfile.BadZipFile,
            UnicodeError,
            csv.Error,
            RuntimeError,
            NotImplementedError,
            EOFError,
        ) as exc:
            raise IngestError(
                ErrorClass.LAYOUT_CHANGED, "Labour market zip cannot be read"
            ) from exc

        warnings = []
        stated = headline_rates(page)
        if not stated:
            warnings.append(
                "release page headline wording not recognised; unemployment rate not cross-checked"
            )
        stored = {p: o.value for p, o in found.get(UNEMPLOYMENT, {}).items()}
        for quarter, rate in stated.items():
            if stored.get(quarter) != rate:
                fail(
                    f"Release page headline unemployment rate for {quarter} does not match the file"
                )
        source = pick_downloads(page.download_urls, self.required_downloads).get(ZIP_FILE)
        series = []
        for p in PINNED:
            obs = found.get(p.definition.key)
            if not obs:
                continue  # validation reports the missing series
            definition = (
                p.definition if source is None else replace(p.definition, source_url=source)
            )
            series.append(ParsedSeries(definition, tuple(obs[k] for k in sorted(obs))))
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
            error("duplicates", "Duplicate labour market series")
        missing = [k for k in KEYS if k not in keys]
        if missing:
            error("coverage", f"Missing required labour market series: {', '.join(missing)}")
        if not reference_period or not is_quarter_end(reference_period):
            error("reference", "Labour market reference period is not a quarter end")
        data: dict[str, dict[str, float]] = {}
        for s in bundle.series:
            d, obs = s.definition, s.observations
            expected = BY_KEY.get(d.key)
            if expected is None or any(
                getattr(d, f) != getattr(expected.definition, f)
                for f in ("unit", "frequency", "adjustment", "definition_id", "category")
            ):
                error("metadata", f"Incompatible labour market measurement metadata: {d.key}")
                continue
            periods = [o.period for o in obs]
            if not obs or len(periods) != len(set(periods)):
                error("duplicates", f"Empty or duplicate labour market observations: {d.key}")
                continue
            if any(add_months(a, 3) != b for a, b in zip(periods, periods[1:], strict=False)):
                error("continuity", f"Labour market periods are not continuous: {d.key}")
            if any(not math.isfinite(o.value) for o in obs) or (
                d.unit != "percent" and any(o.value <= 0 for o in obs)
            ):
                error("values", f"Labour market observations incompatible with definition: {d.key}")
                continue
            data[d.key] = {o.period: o.value for o in obs}
            if reference_period and max(periods) != reference_period:
                error("reference", f"Labour market series {d.key} must end at {reference_period}")
            _check_previous(d.key, d.unit, data[d.key], previous.get(d.key, {}), error, warn)
        _identities(data, error)
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
            f"Labour market published period coverage lost for {key}: {len(lost)} missing periods "
            f"({min(lost)} to {max(lost)})",
        )
    materiality = 1e-9 if unit == "percent" else LEVEL_REVISION_MATERIALITY
    revised = [
        p for p in set(prior) & set(current) if abs(prior[p].value - current[p]) > materiality
    ]
    if revised:
        warn("revisions", f"Historical revisions captured: {key} ({len(revised)} quarters)")


def _identities(data: Mapping[str, Mapping[str, float]], error: Callable[[str, str], None]) -> None:
    """Published HLFS figures must agree with each other, and LCI changes with the index."""
    employed, unemployed, labour_force = (
        data.get(f"hlfs.level.{k}.sa", {}) for k in ("employed", "unemployed", "labour_force")
    )
    bad = [
        p
        for p in sorted(set(employed) & set(unemployed) & set(labour_force))
        if abs(labour_force[p] - employed[p] - unemployed[p]) > IDENTITY_LEVEL_TOLERANCE
    ]
    if bad:
        error("identity", f"Labour force is not employed plus unemployed at {', '.join(bad[:3])}")
    for rate_key, (top, bottom) in RATES.items():
        rate, num, den = data.get(rate_key, {}), data.get(top, {}), data.get(bottom, {})
        bad = [
            p
            for p in sorted(set(rate) & set(num) & set(den))
            if abs(num[p] / den[p] * 100 - rate[p]) > IDENTITY_RATE_TOLERANCE_PP
        ]
        if bad:
            error(
                "identity",
                f"Published {rate_key} does not match its levels at {', '.join(bad[:3])}",
            )
    index = data.get("lci.all_wages.index", {})
    for pct_key, change in LCI_CHANGES.items():
        published = data.get(pct_key, {})
        if not published or not index:
            continue
        computed = change(index)
        common = sorted(set(published) & set(computed))
        bad = [p for p in common if abs(computed[p] - published[p]) > LCI_TOLERANCE_PP]
        if not common or bad:
            error(
                "reconcile",
                f"Published {pct_key} does not reconcile with the index at {', '.join(bad[:3])}",
            )
