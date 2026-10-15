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
