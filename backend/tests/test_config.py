from pathlib import Path

import pytest

from nzstats.config import load_settings


def test_defaults(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path)})
    assert s.data_dir == tmp_path
    assert s.db_path == tmp_path / "nzstats.db"
    assert s.raw_dir == tmp_path / "raw"
    assert s.base_url == "https://www.stats.govt.nz"
    assert s.min_interval_seconds == 10.0
    assert "NZStatsDashboard" in s.user_agent
    assert s.poll_offsets_minutes[0] == 0
    assert s.country_window_months == 36


def test_contact_is_added_to_user_agent(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_CONTACT": "a@b.co"})
    assert "a@b.co" in s.user_agent


def test_interval_below_crawl_delay_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="crawl-delay"):
        load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_MIN_INTERVAL_SECONDS": "5"})


def test_base_url_override_for_tests(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_BASE_URL": "http://x.test/"})
    assert s.base_url == "http://x.test"


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "1e999"])
def test_nonfinite_crawl_interval_is_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="finite"):
        load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_MIN_INTERVAL_SECONDS": value})


def test_on_open_refresh_defaults_are_bounded(tmp_path: Path) -> None:
    r = load_settings({"NZSTATS_DATA_DIR": str(tmp_path)}).refresh
    assert r.fresh_window_minutes == 30
    assert r.failure_cooldown_minutes == 10
    assert r.manual_min_interval_seconds == 60
    assert 1 <= r.max_releases <= 10
    # The calendar takes four to nine requests; a budget must leave room for at least one release.
    assert 12 <= r.max_requests <= 60


def test_the_recent_check_window_is_configurable(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_REFRESH_WINDOW_MINUTES": "120"})
    assert s.refresh.fresh_window_minutes == 120


@pytest.mark.parametrize("value", ["0", "-5", "nan", "x"])
def test_an_invalid_recent_check_window_is_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="NZSTATS_REFRESH_WINDOW_MINUTES"):
        load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_REFRESH_WINDOW_MINUTES": value})
