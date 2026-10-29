"""Phase 3D-B: matching CPI forecasts to official outcomes, on real Stats NZ CPI releases (December 2025 to
September 2026 fixtures). Forecast claims are SYNTHETIC FIXTURE; every expected actual is Stats NZ's own published
figure (the release pages' chart data) or hand-computed from the published index numbers, as noted.
"""

from __future__ import annotations

import pytest

from nzstats.pipeline.ingest import ingest_release
from nzstats.research.outcomes import CpiActuals, cpi_target, look_ahead
from tests.cpi_support import NOW, ingest_cpi, seed_cpi

from .test_compare import claim


@pytest.fixture()
def actuals(rt, site):
    ingest_cpi(rt, site, "2025-12", "2026-03", "2026-06", "2026-09")
    return CpiActuals(rt.conn)


@pytest.fixture()
def partial(rt, site):
    """Only the September 2026 release is stored: earlier first releases are missing."""
    ingest_cpi(rt, site, "2026-09")
    return CpiActuals(rt.conn)


def cpi(label="Annual CPI inflation", horizon="June 2026 quarter", **kw):
    return claim(indicator_label=label, horizon=horizon, **kw)


@pytest.mark.parametrize(("label", "horizon", "measure", "quarter"), [
    ("Annual CPI inflation", "June 2026 quarter", "annual_change", "2026-06"),
    ("Annual CPI inflation", "year to September 2026", "annual_change", "2026-09"),
    ("CPI inflation, annual average", "year to September 2026", "annual_average_change", "2026-09"),
    ("CPI, quarterly change, seasonally adjusted", "June 2026 quarter", "quarterly_change_sa", "2026-06"),
    ("CPI, quarterly change, unadjusted", "Q2 2026", "quarterly_change_nsa", "2026-06"),
])  # fmt: skip
def test_targets_on_a_stated_basis_and_a_named_quarter(label, horizon, measure, quarter):
    target = cpi_target(cpi(label, horizon))
    assert (target.measure, target.quarter) == (measure, quarter)


@pytest.mark.parametrize(("label", "horizon", "why"), [
    ("CPI, quarterly change", "June 2026 quarter", "seasonally adjusted"),
    ("Annual CPI inflation", "2026", "quarter"),
    ("Annual CPI inflation", "2026/27", "quarter"),
    ("Annual CPI inflation", "May 2026", "quarter"),
    ("CPI, quarterly change, seasonally adjusted", "year to June 2026", "single quarter"),
    ("Annual CPI inflation, seasonally adjusted", "June 2026 quarter", "official"),
    ("Annual Auckland CPI inflation", "June 2026 quarter", "official series"),
])  # fmt: skip
def test_unmatchable_claims_say_why(label, horizon, why):
    reason = cpi_target(cpi(label, horizon))
    assert isinstance(reason, str) and why in reason


def test_non_cpi_indicators_have_no_official_series_here():
    reason = cpi_target(
        claim(indicator="ocr", indicator_label="OCR", horizon="June 2026 quarter", value=3.0)
    )
    assert isinstance(reason, str) and "no official" in reason.lower()


def test_annual_change_matches_the_published_figures(actuals):
    # Stats NZ chart data, "CPI all groups (annual)": March 2026 3.1, June 2026 4.1, September 2026 3.7.
    for quarter, published in (("2026-03", 3.1), ("2026-06", 4.1), ("2026-09", 3.7)):
        out = actuals.outcome(cpi_target(cpi(horizon=f"year to {quarter_name(quarter)}")))
        assert out.first.value == published and not out.first.first_release


def test_quarterly_unadjusted_change_matches_the_published_figures(actuals):
    # "CPI all groups (quarterly)": March 2026 0.9, June 2026 1.5, September 2026 0.7.
    for quarter, published in (("2026-03", 0.9), ("2026-06", 1.5), ("2026-09", 0.7)):
        target = cpi_target(
            cpi("CPI, quarterly change, unadjusted", f"{quarter_name(quarter)} quarter")
        )
        assert actuals.outcome(target).first.value == published


def test_annual_average_change_is_derived_from_the_published_index(actuals):
    # Hand-computed: (1327 + 1339 + 1359 + 1368) / (1319 + 1306 + 1299 + 1287) = 5393 / 5211 -> 3.49% -> 3.5.
    target = cpi_target(cpi("CPI inflation, annual average", "year to September 2026"))
    assert actuals.outcome(target).first.value == 3.5


def test_a_revised_seasonally_adjusted_quarter_reports_first_and_latest(actuals):
    # SA index, June 2026 release: 1359.9237187 / 1339.6379152 -> 1.514% -> 1.5 (first published).
    # September 2026 release: 1359.9292265 / 1338.8588419 -> 1.574% -> 1.6 (latest).
    out = actuals.outcome(
        cpi_target(cpi("CPI, quarterly change, seasonally adjusted", "June 2026 quarter"))
    )
    assert out.first.value == 1.5 and not out.first.first_release
    assert "June 2026" in out.first.release
    assert out.latest.value == 1.6 and "September 2026" in out.latest.release
    assert out.revision == pytest.approx(0.1)


def test_an_unrevised_outcome_has_no_revision(actuals):
    out = actuals.outcome(cpi_target(cpi(horizon="year to March 2026")))
    assert out.first.value == out.latest.value == 3.1 and out.revision == 0


def test_a_missing_first_release_is_labelled_as_the_earliest_stored(partial):
    out = partial.outcome(cpi_target(cpi(horizon="year to June 2026")))
    assert out.first.value == 4.1 and not out.first.first_release
    assert "September 2026" in out.first.release


def test_a_target_not_yet_released_is_pending_never_the_latest_quarter(actuals):
    assert actuals.outcome(cpi_target(cpi(horizon="year to December 2026"))) is None
    assert actuals.newest_release()[0].startswith("Consumers price index: September 2026")


def test_look_ahead_excludes_forecasts_published_on_or_after_the_release(actuals):
    release = actuals.release_date("2026-06")  # 21 July 2026, 10:45 NZST
    assert release is not None
    assert look_ahead("2026-07-20", "2026-06", release) is None
    assert "on or after" in look_ahead("2026-07-21", "2026-06", release)
    assert "on or after" in look_ahead("2026-08-01", "2026-06", release)
    assert "no publication date" in look_ahead(None, "2026-06", release)


def test_without_a_release_date_only_forecasts_made_within_the_quarter_count():
    assert look_ahead("2026-06-30", "2026-06", None) is None
    assert "release date" in look_ahead("2026-07-01", "2026-06", None)


def correct_june_sa_index(rt, site, key, value):
    """Re-ingest the June 2026 release with its seasonally adjusted all-groups index for the June quarter set to
    `value`. (The unadjusted all-groups index is cross-checked against the contributions, so a bare edit is refused.)"""
    row_start = '"CPIQ.SE9SA","2026.06"'
    for url, (status, body, ctype) in list(site.routes.items()):
        text = body.decode() if isinstance(body, bytes) and url.endswith(".csv") else ""
        row = next((ln for ln in text.splitlines() if ln.startswith(row_start)), None)
        if row is not None:
            corrected = row.replace(row.split(",")[2], f'"{value}"')
            site.routes[url] = (status, text.replace(row, corrected).encode(), ctype)
    outcome = ingest_release(rt, key, now_fn=lambda: NOW)
    assert outcome.outcome == "ingested", outcome.detail


@pytest.fixture()
def june(rt, site):
    """Only the June 2026 release, ingested as first published (seasonally adjusted quarterly change 1.5), and its routes."""
    _, key, _, downloads = seed_cpi(rt, site)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    return key, dict(site.routes)


def june_target():
    return cpi_target(cpi("CPI, quarterly change, seasonally adjusted", "June 2026 quarter"))


def test_a_corrected_release_keeps_the_original_as_first_published(rt, site, june):
    key, _ = june
    correct_june_sa_index(rt, site, key, 1362.0)  # 1362.0 / 1339.6379152 -> 1.67 -> 1.7
    out = CpiActuals(rt.conn).outcome(june_target())
    assert out.first.value == 1.5 and not out.first.first_release
    assert out.latest.value == 1.7 and not out.latest.first_release
    assert out.revision == pytest.approx(0.2)


def test_several_corrections_keep_the_first_bundle_and_use_the_last_as_latest(rt, site, june):
    key, _ = june
    correct_june_sa_index(rt, site, key, 1362.0)
    correct_june_sa_index(rt, site, key, 1365.0)  # 1365.0 / 1339.6379152 -> 1.89 -> 1.9
    out = CpiActuals(rt.conn).outcome(june_target())
    assert (out.first.value, out.latest.value) == (1.5, 1.9)


def test_a_reverted_correction_still_has_the_original_as_first_and_latest(rt, site, june):
    key, original = june
    correct_june_sa_index(rt, site, key, 1362.0)
    site.routes.update(original)
    assert ingest_release(rt, key, now_fn=lambda: NOW).outcome == "ingested"
    out = CpiActuals(rt.conn).outcome(june_target())
    assert (out.first.value, out.latest.value, out.revision) == (1.5, 1.5, 0)


def quarter_name(quarter: str) -> str:
    return {"03": "March", "06": "June", "09": "September", "12": "December"}[
        quarter[5:]
    ] + f" {quarter[:4]}"
