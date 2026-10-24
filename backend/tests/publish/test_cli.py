import json

from nzstats.cli import main


def test_export_then_validate_for_publish_round_trip(full_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(full_dir))
    out = tmp_path / "snap"
    assert main(["export-snapshot", str(out)]) == 2  # fixture data is refused
    assert "test fixtures" in capsys.readouterr().err
    assert not out.exists()

    assert main(["export-snapshot", str(out), "--allow-fixtures"]) == 0
    assert "origin fixture" in capsys.readouterr().out
    assert main(["validate-snapshot", str(out)]) == 0
    assert main(["validate-snapshot", str(out), "--for-publish"]) == 1
    assert "only production data" in capsys.readouterr().err


def test_snapshot_id_prints_the_manifest_id(snapshot, capsys):
    assert main(["snapshot-id", str(snapshot)]) == 0
    assert (
        capsys.readouterr().out.strip()
        == json.loads((snapshot / "manifest.json").read_text())["snapshot_id"]
    )


def test_export_reports_missing_data_without_a_traceback(
    migration_only_dir, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(migration_only_dir))
    assert main(["export-snapshot", str(tmp_path / "o"), "--allow-fixtures"]) == 2
    assert "expected data is missing" in capsys.readouterr().err
