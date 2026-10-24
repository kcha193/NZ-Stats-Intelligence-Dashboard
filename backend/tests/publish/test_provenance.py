from nzstats.config import load_settings
from nzstats.publish.provenance import FIXTURE_MARKER, is_fixture_data
from nzstats.runtime import build_runtime
from tests.support import FakeSite


def test_a_runtime_with_an_injected_fetcher_marks_its_data_as_fixture_data(tmp_path):
    rt = build_runtime(
        load_settings({"NZSTATS_DATA_DIR": str(tmp_path)}), fetcher=FakeSite().fetcher()
    )
    rt.conn.close()
    assert (tmp_path / FIXTURE_MARKER).exists()
    assert is_fixture_data(tmp_path)


def test_a_production_runtime_does_not_mark_its_data(tmp_path):
    rt = build_runtime(load_settings({"NZSTATS_DATA_DIR": str(tmp_path)}))
    rt.conn.close()
    assert not is_fixture_data(tmp_path)


def test_the_fixture_flag_travels_inside_the_database_file(tmp_path):
    """A copy or a backup of the .db alone, without the marker file, is still fixture data."""
    import shutil
    import sqlite3

    src = tmp_path / "src"
    rt = build_runtime(load_settings({"NZSTATS_DATA_DIR": str(src)}), fetcher=FakeSite().fetcher())
    rt.conn.close()
    only_db = tmp_path / "only-db"
    only_db.mkdir()
    shutil.copy(src / "nzstats.db", only_db / "nzstats.db")
    assert not (only_db / FIXTURE_MARKER).exists() and is_fixture_data(only_db)

    backup = tmp_path / "backup"
    backup.mkdir()
    s, d = sqlite3.connect(src / "nzstats.db"), sqlite3.connect(backup / "nzstats.db")
    s.backup(d)
    d.close()
    s.close()
    assert is_fixture_data(backup)
