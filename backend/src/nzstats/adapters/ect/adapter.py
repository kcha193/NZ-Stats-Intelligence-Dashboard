"""Bounded in-memory ZIP/CSV ingestion with source chart reconciliation."""

from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import NoReturn

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.ect.series import (
    ACTUAL_COMPONENTS,
    INDUSTRIES,
    REQUIRED,
    SLUG,
    identity,
    supported_definitions,
)
from nzstats.clock import AKL
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, Point
from nzstats.sources.calendar import parse_title
from nzstats.sources.release_page import ReleasePage, classify_download
from nzstats.stats.periods import add_months

MAX_ARCHIVE = 16 * 1024 * 1024
MAX_UNPACKED = 32 * 1024 * 1024
MAX_ROWS = 150_000

# Official CSV levels are rounded to NZD 0.1 million, so each rounded figure is off by <= 0.05.
ROUNDING = 0.05
# Measured on the official August and September 2026 files (every period with complete components):
# monthly actual aggregates equal the sum of their industries within rounding from January 2017
# (earlier months differ by up to 0.43%), quarterly industries equal the sum of their three months
# within rounding for all history, but quarterly aggregates and counts differ from the sum of their
# months by up to ~0.06% (Stats NZ does not recompute them). Rounding-level tolerance is therefore
# enforced only where the source supports it; elsewhere a coarse plausibility bound still rejects
# scale errors, which are an order of magnitude larger.
STRICT_FROM = "2017-01"
COARSE_RELATIVE = 0.01


def fail(message: str) -> NoReturn:
    raise IngestError(ErrorClass.VALIDATION_FAILED, message)


def read_archive(raw: bytes) -> str:
    if len(raw) > MAX_ARCHIVE:
        fail("ECT archive exceeds size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            files = z.infolist()
            if not files or len(files) > 8 or sum(f.file_size for f in files) > MAX_UNPACKED:
                fail("ECT archive exceeds member limits")
            for f in files:
                path = PurePosixPath(f.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in f.filename
                    or f.flag_bits & 1
                ):
                    fail("ECT archive contains unsafe members")
                if f.file_size / max(f.compress_size, 1) > 250:
                    fail("ECT archive compression ratio exceeds limit")
            tables = [f for f in files if f.filename.lower().endswith(".csv")]
            if len(tables) != 1:
                fail("ECT archive must contain exactly one CSV table")
            with z.open(tables[0]) as handle:
                content = handle.read(MAX_UNPACKED + 1)
            if len(content) > MAX_UNPACKED:
                fail("ECT table exceeds size limit")
            return content.decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, NotImplementedError, EOFError) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "ECT ZIP cannot be decoded") from exc


class EctAdapter:
    series_slug = SLUG
    required_downloads = ("ect_zip",)
    previous_keys = tuple(supported_definitions())
    preserve_publication_coverage = True

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle:
        if not page.title.lower().startswith("electronic card transactions:"):
            fail("ECT source title does not match adapter")
        reference = parse_title(page.title).reference_period
        if not reference or reference > page.published_at.astimezone(AKL).strftime("%Y-%m"):
            fail("ECT reference period is incompatible with publication")
        rows = csv.DictReader(io.StringIO(read_archive(files["ect_zip"])))
        required = {
            "Series_reference",
            "Period",
            "Data_value",
            "Suppressed",
            "STATUS",
            "UNITS",
            "Magnitude",
            "Subject",
            "Group",
            *(f"Series_title_{i}" for i in range(1, 6)),
        }
        if (
            not rows.fieldnames
            or len(rows.fieldnames) != len(set(rows.fieldnames))
            or not required <= set(rows.fieldnames)
        ):
            fail("ECT CSV schema changed")
        source = next((u for u in page.download_urls if classify_download(u) == "ect_zip"), None)
        definitions, observations, seen = {}, defaultdict(list), set()
        for n, row in enumerate(rows):
            if n >= MAX_ROWS:
                fail("ECT table exceeds row limit")
            try:
                code = row["Series_reference"]
                found = identity(code, source)
                if found is None:
                    if not re.fullmatch(r"ECT[AMQ]\.[A-Z0-9]+", code):
                        fail("ECT source contains an invalid series reference")
                    continue  # explicitly out-of-scope annual, proportions and annual changes
                definition, expected = found
                if any(row.get(k) != v for k, v in expected.items()):
                    fail(f"ECT metadata incompatible for {code}")
                period = row["Period"]
                if not re.fullmatch(r"[1-9][0-9]{3}\.(0[1-9]|1[0-2])", period):
                    fail("ECT period malformed")
                period = period.replace(".", "-")
                if definition.frequency.value == "quarterly" and period[-2:] not in (
                    "03",
                    "06",
                    "09",
                    "12",
                ):
                    fail("ECT quarterly period is not a quarter end")
                if period > page.published_at.astimezone(AKL).strftime("%Y-%m"):
                    fail("ECT observations postdate publication")
                key = definition.key
                if (key, period) in seen:
                    fail("ECT duplicate observation")
                seen.add((key, period))
                definitions[key] = definition
                status = row["STATUS"]
                if row["Suppressed"] or not row["Data_value"]:
                    if status not in ("C", "S") and not row["Suppressed"]:
                        fail("ECT missing value without confidentiality status")
                    continue
                if status not in ("F", "P", "R"):
                    fail("ECT unknown observation status")
                value = float(row["Data_value"])
                if not math.isfinite(value) or (value < 0 and definition.unit != "percent"):
                    fail("ECT numeric value is invalid")
                if definition.unit == "transactions" and not value.is_integer():
                    fail("ECT transaction count must be integral")
                obs_status = {
                    "F": ObsStatus.FINAL,
                    "P": ObsStatus.PROVISIONAL,
                    "R": ObsStatus.UNKNOWN,
                }[status]
                observations[key].append(Observation(key, period, value, obs_status))
            except (ValueError, TypeError, KeyError) as exc:
                raise IngestError(ErrorClass.LAYOUT_CHANGED, "ECT row cannot be parsed") from exc
        bundle = ParsedBundle(
            "ect-csv-anzsic06-v1",
            tuple(
                ParsedSeries(definitions[k], tuple(sorted(v, key=lambda o: o.period)))
                for k, v in sorted(observations.items())
                if v
            ),
        )
        try:
            self._reconcile(page, bundle)
        except (ValueError, IndexError, OverflowError) as exc:
            raise IngestError(
                ErrorClass.LAYOUT_CHANGED, "ECT embedded chart layout changed"
            ) from exc
        findings = self.validate(bundle, reference_period=reference, previous={})
        if any(f.severity == "error" for f in findings):
            fail("; ".join(f.message for f in findings if f.severity == "error"))
        return bundle

    def _reconcile(self, page: ReleasePage, bundle: ParsedBundle) -> None:
        data = {
            s.definition.key: {o.period: o.value for o in s.observations} for s in bundle.series
        }
        for key, values in data.items():
            if not key.endswith(".change"):
                continue
            levels = data.get(key.removesuffix(".change") + ".value", {})
            lag = 3 if ".q." in key else 1
            for p, published in values.items():
                prev = levels.get(add_months(p, -lag))
                if p in levels and prev and abs((levels[p] / prev - 1) * 100 - published) > 0.065:
                    fail("ECT published percentage does not reconcile with levels")
        for chart in page.charts:
            rows = list(csv.reader(io.StringIO(chart.csv)))
            if "Percentage change in seasonally adjusted card transaction values" in chart.title:
                if len(rows) != 2 or len(rows[0]) != len(rows[1]):
                    fail("ECT industry chart layout changed")
                names = {v[1]: v[0] for v in INDUSTRIES.values()}
                for name, published in zip(rows[0][1:], rows[1][1:], strict=True):
                    if name not in names:
                        fail("ECT industry chart classification changed")
                    values = data.get(f"ect.m.sa.{names[name]}.value", {})
                    if not values:
                        fail("ECT industry chart has no source series")
                    p = max(values)
                    prev = values.get(add_months(p, -1))
                    if (
                        not math.isfinite(float(published))
                        or not prev
                        or abs((values[p] / prev - 1) * 100 - float(published)) > 0.065
                    ):
                        fail("ECT industry chart does not reconcile with levels")
            if "Retail card spending ($)" in chart.title:
                for row in rows[1:]:
                    adj = {"Actual": "actual", "Seasonally adjusted": "sa", "Trend": "trend"}.get(
                        row[0]
                    )
                    if adj is None:
                        fail("ECT retail chart adjustment changed")
                    values = data.get(f"ect.m.{adj}.retail.value", {})
                    for label, value in zip(rows[0][1:], row[1:], strict=True):
                        # Official chart expresses dollars; CSV levels are rounded to $0.1 million.
                        p = datetime.strptime(label, "%b-%y").strftime("%Y-%m")
                        if value and (
                            not math.isfinite(float(value))
                            or p not in values
                            or abs(values[p] - float(value) / 1_000_000) > 0.051
                        ):
                            fail("ECT retail chart does not reconcile with levels")

    def validate(
        self,
        bundle: ParsedBundle,
        *,
        reference_period: str | None,
        previous: Mapping[str, Mapping[str, Point]],
    ) -> list[Finding]:
        findings = []
        definitions = supported_definitions()
        latest_quarter = (
            add_months(reference_period, -(int(reference_period[-2:]) % 3))
            if reference_period
            else None
        )

        def error(rule, message):
            findings.append(Finding(rule, "error", message))

        keys = [s.definition.key for s in bundle.series]
        if len(keys) != len(set(keys)):
            error("duplicates", "Duplicate ECT series")
        if not set(REQUIRED) <= set(keys):
            error("coverage", "Missing required ECT indicators")
        quarterly = {k for k in keys if k.startswith("ect.q.")}
        required_quarters = {k.replace("ect.m.", "ect.q.", 1) for k in REQUIRED}
        if not required_quarters <= quarterly:
            missing = ", ".join(sorted(required_quarters - quarterly))
            error("coverage", f"Missing required quarterly ECT indicators: {missing}")
        missing_series = {k for k, points in previous.items() if points} - set(keys)
        if missing_series:
            error(
                "coverage",
                f"ECT previously published series missing: {', '.join(sorted(missing_series))}",
            )
        for s in bundle.series:
            d = s.definition
            obs = s.observations
            periods = [o.period for o in obs]
            expected = definitions.get(d.key)
            if expected is None or any(
                getattr(d, k) != getattr(expected, k)
                for k in ("unit", "frequency", "adjustment", "definition_id", "category")
            ):
                error("metadata", f"Incompatible ECT measurement metadata: {d.key}")
            step = 3 if d.frequency.value == "quarterly" else 1
            if not obs or len(periods) != len(set(periods)):
                error("duplicates", "Empty or duplicate ECT observations")
                continue
            if any(add_months(a, step) != b for a, b in zip(periods, periods[1:], strict=False)):
                error("continuity", f"ECT periods are not continuous: {d.key}")
            if (
                not reference_period
                or max(periods) > reference_period
                or (step == 1 and max(periods) != reference_period)
            ):
                error("reference", "ECT latest period differs from release reference")
            if step == 3 and latest_quarter and max(periods) != latest_quarter:
                error(
                    "reference",
                    f"ECT quarterly series {d.key} must include latest completed quarter "
                    f"{latest_quarter}",
                )
            if any(
                o.series_key != d.key
                or not math.isfinite(o.value)
                or (o.value < 0 and d.unit != "percent")
                for o in obs
            ):
                error("values", "ECT observations incompatible with definition")
            prior = previous.get(d.key, {})
            missing_periods = set(prior) - set(periods)
            if missing_periods:
                error(
                    "coverage",
                    f"ECT published period coverage lost for {d.key}: "
                    f"{len(missing_periods)} missing periods "
                    f"({min(missing_periods)} to {max(missing_periods)})",
                )
            common = set(periods) & set(prior)
            if any(prior[o.period].value != o.value for o in obs if o.period in common):
                findings.append(
                    Finding("revisions", "warning", f"Historical revisions captured: {d.key}")
                )
            if (
                len(obs) > 1
                and d.unit != "percent"
                and obs[-2].value
                and abs(obs[-1].value / obs[-2].value - 1) > 0.5
            ):
                findings.append(
                    Finding(
                        "structural_change",
                        "warning",
                        f"Large ECT movement requires review: {d.key}",
                    )
                )
        for message in actual_value_inconsistencies(bundle):
            error("consistency", f"ECT actual-value consistency failed: {message}")
        return findings


def _levels(bundle: ParsedBundle) -> dict[str, dict[str, float]]:
    return {s.definition.key: {o.period: o.value for o in s.observations} for s in bundle.series}


def actual_value_inconsistencies(bundle: ParsedBundle) -> list[str]:
    """Cross-series identities that hold for actual (unadjusted) ECT levels.

    Catches a series whose absolute levels are wrong while its published percentage changes still
    reconcile (for example a consistent x10 scaling). Periods where a component is absent
    (confidential or not published) are skipped, never treated as zero. Seasonally adjusted and
    trend series are not checked because their components are adjusted independently.
    """
    data = _levels(bundle)
    problems: list[str] = []

    def series(freq: str, name: str, measure: str = "value") -> dict[str, float]:
        return data.get(f"ect.{freq}.actual.{name}.{measure}", {})

    # Monthly aggregate = sum of its industries.
    for aggregate, parts in ACTUAL_COMPONENTS.items():
        total, components = series("m", aggregate), [series("m", p) for p in parts]
        for period, value in sorted(total.items()):
            if not all(period in c for c in components):
                continue
            expected = sum(c[period] for c in components)
            tolerance = (
                ROUNDING * (len(parts) + 1)
                if period >= STRICT_FROM
                else COARSE_RELATIVE * abs(value)
            )
            if abs(value - expected) > tolerance + 1e-9:
                problems.append(
                    f"{aggregate} {period} is {value:,.1f} but its industries sum to {expected:,.1f}"
                )
                break
    # Quarter = sum of its three months (industries exactly; aggregates and counts coarsely).
    quarterly = {name: "strict" for name, _ in INDUSTRIES.values()}
    quarterly |= {name: "coarse" for name in ACTUAL_COMPONENTS}
    for name, mode in quarterly.items():
        months = series("m", name)
        for period, value in sorted(series("q", name).items()):
            parts = [months.get(add_months(period, -k)) for k in range(3)]
            if any(p is None for p in parts):
                continue
            tolerance = 3 * ROUNDING if mode == "strict" else COARSE_RELATIVE * abs(value)
            if abs(value - sum(parts)) > tolerance + 1e-9:
                problems.append(f"{name} quarter {period} differs from the sum of its months")
                break
    months, quarters = series("m", "total", "count"), series("q", "total", "count")
    for period, value in sorted(quarters.items()):
        parts = [months.get(add_months(period, -k)) for k in range(3)]
        if all(p is not None for p in parts) and abs(value - sum(parts)) > COARSE_RELATIVE * value:
            problems.append(
                f"transaction count quarter {period} differs from the sum of its months"
            )
            break
    # Monthly count x mean transaction value = total value, within the rounding of mean and total.
    values, means = series("m", "total"), series("m", "total", "average")
    for period, count in sorted(months.items()):
        mean, value = means.get(period), values.get(period)
        if not mean or not value:
            continue
        tolerance = 1.1 * (ROUNDING / mean + ROUNDING / value)
        if abs(count * mean / 1_000_000 - value) / value > tolerance:
            problems.append(
                f"count x mean transaction value does not equal total value in {period}"
            )
            break
    return problems
