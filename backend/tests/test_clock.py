from datetime import UTC, datetime

import pytest

from nzstats.clock import AKL, from_utc_iso, parse_akl_naive, to_akl_iso, to_utc_iso


def test_nzst_conversion() -> None:
    dt = parse_akl_naive("2026-09-14 10:45:00")
    assert to_utc_iso(dt) == "2026-09-13T22:45:00Z"


def test_nzdt_conversion_after_dst_starts() -> None:
    dt = parse_akl_naive("2026-10-14 10:45:00")
    assert to_utc_iso(dt) == "2026-10-13T21:45:00Z"


def test_round_trip_and_akl_iso() -> None:
    utc = "2026-10-13T21:45:00Z"
    assert from_utc_iso(utc) == datetime(2026, 10, 13, 21, 45, tzinfo=UTC)
    assert to_akl_iso(utc) == "2026-10-14T10:45:00+13:00"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        to_utc_iso(datetime(2026, 1, 1))


def test_text_ordering_survives_dst_boundary() -> None:
    before = to_utc_iso(parse_akl_naive("2026-09-26 10:45:00"))  # NZST
    after = to_utc_iso(parse_akl_naive("2026-09-28 10:45:00"))  # NZDT
    assert before < after
    assert AKL.key == "Pacific/Auckland"
