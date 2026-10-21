import io
import math
import zipfile
from dataclasses import replace

import pytest

from nzstats.adapters.cpi import adapter as cpi_adapter
from nzstats.adapters.cpi.adapter import CpiAdapter
from nzstats.adapters.cpi.workbook import read_quarterly_tables
from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.release_page import classify_download, pick_downloads
from tests.conftest import fixture_bytes
from tests.cpi_support import files, page, workbook_with_cell


def workbook() -> bytes:
    return fixture_bytes("cpi_2026-06_workbook.xlsx")


def zipped(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return out.getvalue()


def test_reads_only_the_quarterly_single_base_blocks():
    tables = read_quarterly_tables(workbook())
    assert set(tables) == {
        *(f"SE9NS40{n}" for n in ("00", "05", "10", "15", "20", "25")),
        *(f"SE9NS41{n}" for n in ("00", "05", "10", "15", "20")),
        "SE9A",
    }
    assert min(tables["SE9NS4000"]) == "2022-03" and max(tables["SE9NS4000"]) == "2026-06"
    assert tables["SE9NS4000"]["2022-03"] == 1.9
    assert tables["SE9A"]["2026-06"] == 1.5
    assert all(p[5:] in ("03", "06", "09", "12") for p in tables["SE9NS4110"])


@pytest.mark.parametrize(
    "raw",
    [
        b"not a zip",
        zipped({"xl/workbook.xml": b"<x/>", "xl/vbaProject.bin": b"macro"}),
        zipped({"../evil": b"x"}),
        zipped({"xl/workbook.xml": b"0" * 200_000_000}),
        zipped({"xl/workbook.xml": b"<x/>"}),
    ],
)
def test_unsafe_or_unexpected_workbooks_are_rejected_as_layout_changes(raw):
    with pytest.raises(IngestError) as caught:
        read_quarterly_tables(raw)
    assert caught.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_underlying_series_are_official_percent_changes():
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})
    by_key = {s.definition.key: s for s in bundle.series}
    median = by_key["cpi.underlying.median"]
    assert median.definition.unit == "percent" and median.observations[-1].period == "2026-06"
    assert len([k for k in by_key if k.startswith("cpi.underlying.")]) == 11
    assert "core inflation" not in " ".join(s.definition.name.lower() for s in bundle.series)
    assert bundle.warnings == ()


@pytest.mark.parametrize("extra", [{}, {"cpi_workbook": b"junk"}])
def test_missing_or_unreadable_workbook_never_blocks_headline_cpi(extra):
    bundle = CpiAdapter().parse(page(), {**files(), **extra})
    assert not [s for s in bundle.series if ".underlying." in s.definition.key]
    assert any("underlying" in w for w in bundle.warnings)
    assert any(s.definition.key == "cpi.index.nsa.all_groups" for s in bundle.series)


def test_workbook_that_disagrees_with_the_index_is_dropped(monkeypatch):
    tables = read_quarterly_tables(workbook())
    tables["SE9A"] = {**tables["SE9A"], "2026-06": 2.5}
    monkeypatch.setattr(cpi_adapter, "read_quarterly_tables", lambda raw: tables)
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})
    assert not [s for s in bundle.series if ".underlying." in s.definition.key]
    assert any("does not reconcile" in w for w in bundle.warnings)


def test_workbook_for_a_different_quarter_is_dropped(monkeypatch):
    tables = {
        k: {p: v for p, v in d.items() if p < "2026-06"}
        for k, d in read_quarterly_tables(workbook()).items()
    }
    monkeypatch.setattr(cpi_adapter, "read_quarterly_tables", lambda raw: tables)
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})
    assert any("reference quarter" in w for w in bundle.warnings)
    assert replace(bundle, warnings=()).series


def test_a_workbook_with_dangling_string_references_is_a_layout_change():
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(workbook())) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "xl/sharedStrings.xml":
                data = (
                    b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"></sst>'
                )
            dst.writestr(item, data)
    with pytest.raises(IngestError) as caught:
        read_quarterly_tables(out.getvalue())
    assert caught.value.error_class is ErrorClass.LAYOUT_CHANGED


@pytest.mark.parametrize(
    "error", [IndexError("x"), NotImplementedError("x"), TypeError("x"), ZeroDivisionError("x")]
)
def test_no_workbook_failure_can_block_headline_cpi(monkeypatch, error):
    def explode(raw):
        raise error

    monkeypatch.setattr(cpi_adapter, "read_quarterly_tables", explode)
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})
    assert any(s.definition.key == "cpi.index.nsa.all_groups" for s in bundle.series)
    assert any("underlying" in w for w in bundle.warnings)


def _underlying_keys(bundle):
    return [s.definition.key for s in bundle.series if ".underlying." in s.definition.key]


def _assert_headline_survives_with_warning(bundle):
    keys = {s.definition.key for s in bundle.series}
    assert "cpi.index.nsa.all_groups" in keys and "cpi.contrib.q.transport" in keys
    assert not _underlying_keys(bundle)
    assert any("underlying" in w for w in bundle.warnings)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")], ids=str)
@pytest.mark.parametrize("ref", ["SE9NS4110", "SE9NS4000", "SE9A"])
@pytest.mark.parametrize("period", ["2026-06", "2022-03"])
def test_non_finite_workbook_values_drop_the_optional_series_without_blocking(
    monkeypatch, ref, period, bad
):
    tables = read_quarterly_tables(workbook())
    tables[ref] = {**tables[ref], period: bad}
    monkeypatch.setattr(cpi_adapter, "read_quarterly_tables", lambda raw: tables)
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})
    _assert_headline_survives_with_warning(bundle)


def _patched(monkeypatch, mutate):
    tables = read_quarterly_tables(workbook())
    mutate(tables)
    monkeypatch.setattr(cpi_adapter, "read_quarterly_tables", lambda raw: tables)
    return CpiAdapter().parse(page(), {**files(), "cpi_workbook": workbook()})


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t["SE9NS4110"].update({"2026-05": 1.0}),  # not a quarter-end month
        lambda t: t["SE9NS4110"].update({"2026-13": 1.0}),  # not a month at all
        lambda t: t.update({"SE9NS4110": {}}),  # empty series
        lambda t: t.pop("SE9NS4110"),  # missing series
        lambda t: t.update({"SE9NS4110": {"2026-06": 1.0}}),  # too little history
        lambda t: t["SE9NS4110"].update({"2026-06": "1.0"}),  # not a number
        lambda t: t["SE9NS4110"].update({"2026-06": True}),  # bool is not a measurement
        lambda t: t["SE9NS4110"].update({"2026-06": 1e9}),  # absurd magnitude
        lambda t: t.update({"SE9ZZ": {"2026-06": 1.0}}),  # unexpected extra series
    ],
    ids=[
        "off_quarter",
        "bad_month",
        "empty",
        "missing",
        "short",
        "string",
        "bool",
        "absurd",
        "extra",
    ],
)
def test_structurally_invalid_workbook_tables_drop_optional_series_without_blocking(
    monkeypatch, mutate
):
    _assert_headline_survives_with_warning(_patched(monkeypatch, mutate))


@pytest.mark.parametrize("text", ["NaN", "inf", "-inf", "1e999"])
def test_non_finite_cells_in_a_real_workbook_never_block_headline_cpi(text):
    raw = workbook_with_cell(text)
    # The mutation must reach the reader's output, or this test proves nothing.
    assert not math.isfinite(read_quarterly_tables(raw)["SE9NS4110"]["2026-06"])
    bundle = CpiAdapter().parse(page(), {**files(), "cpi_workbook": raw})
    _assert_headline_survives_with_warning(bundle)


def _workbook_url(pg):
    return next(u for u in pg.download_urls if classify_download(u) == "cpi_workbook")


def test_underlying_series_cite_the_workbook_they_came_from():
    pg = page()
    bundle = CpiAdapter().parse(pg, {**files(), "cpi_workbook": workbook()})
    cited = {s.definition.source_url for s in bundle.series if ".underlying." in s.definition.key}
    assert cited == {_workbook_url(pg)}


def test_underlying_series_cite_the_corrected_workbook_when_both_are_listed():
    pg = page()
    original = _workbook_url(pg)
    corrected = original.replace(".xlsx", "-corrected.xlsx")
    assert classify_download(corrected) == "cpi_workbook"
    urls = (original, corrected, *(u for u in pg.download_urls if u != original))
    assert pick_downloads(urls, ("cpi_workbook",)) == {"cpi_workbook": corrected}
    bundle = CpiAdapter().parse(
        replace(pg, download_urls=urls), {**files(), "cpi_workbook": workbook()}
    )
    cited = {s.definition.source_url for s in bundle.series if ".underlying." in s.definition.key}
    assert cited == {corrected}
