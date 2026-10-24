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
