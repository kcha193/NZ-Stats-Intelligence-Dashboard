import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import synth

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": f"{ROOT}{os.pathsep}{ROOT.parents[1] / 'backend' / 'src'}"}
    return subprocess.run(
        [sys.executable, "-m", "xlsxinspect", *args], check=False, capture_output=True, text=True, env=env, cwd=ROOT
    )


def test_cli_prints_one_guarded_json_line(tmp_path):
    path = synth.save(synth.forecast_book(), tmp_path / "f.xlsx")
    r = _run(str(path))
    assert r.returncode == 0 and r.stderr == ""
    assert json.loads(r.stdout)["status"] == "ok"
    assert synth.SECRET_LABEL not in r.stdout


def test_cli_refuses_a_hash_mismatch_without_reading_the_workbook(tmp_path):
    path = synth.save(synth.forecast_book(), tmp_path / "f.xlsx")
    r = _run(str(path), "--expect-sha256", "0" * 64)
    assert r.returncode == 2
    assert json.loads(r.stdout) == {"status": "refused"}


def test_cli_missing_file_is_a_fixed_code_and_no_path(tmp_path):
    r = _run(str(tmp_path / "secret-name.xlsx"))
    assert r.returncode == 2
    assert json.loads(r.stdout) == {"status": "error"}
    assert "secret-name" not in r.stdout + r.stderr


def test_cli_unexpected_failure_is_a_fixed_code_with_silent_stderr(tmp_path):
    path = synth.save(synth.forecast_book(), tmp_path / "secret-name.xlsx")
    raw = bytearray(path.read_bytes())
    raw[-30:] = b"\0" * 30  # damage the central directory end
    path.write_bytes(bytes(raw))
    r = _run(str(path))
    assert r.returncode == 2 and r.stderr == ""
    assert json.loads(r.stdout)["status"] in {"refused", "error"}
    assert "secret-name" not in r.stdout


def test_cli_refuses_an_oversized_file_before_reading_it(tmp_path):
    path = tmp_path / "big.xlsx"
    path.write_bytes(b"\0" * (16 * 1024 * 1024 + 1))
    r = _run(str(path))
    assert r.returncode == 2 and json.loads(r.stdout) == {"status": "refused"}


def test_cli_layout_prints_masked_geometry_only(tmp_path):
    path = synth.save(synth.vertical_book(), tmp_path / "v.xlsx")
    r = _run(str(path), "--layout")
    assert r.returncode == 0 and r.stderr == ""
    out = json.loads(r.stdout)
    assert out["status"] == "ok" and out["layout"][1]["marker_rows"] == [11]
    assert synth.SECRET_LABEL not in r.stdout and "Fictional" not in r.stdout


def test_cli_unit_coverage_is_masked(tmp_path):
    wb = synth.forecast_book()
    ws = wb.active
    ws.title = "PRIVATE-TITLE percent"
    ws["C6"] = "=1+123456789"
    ws.oddHeader.center.text = "PRIVATE-HEADER per cent"
    ws.oddFooter.left.text = "PRIVATE-FOOTER per annum"
    path = synth.save(wb, tmp_path / "PRIVATE-PATH.xlsx")
    drawing = synth.drawing("<a:p><a:r><a:t>PRIVATE-DRAWING p.a.</a:t></a:r></a:p>")
    synth.rewrite(path, {}, {"xl/drawings/drawing1.xml": drawing})

    for args in ((), ("--layout",)):
        r = _run(str(path), *args)
        assert r.returncode == 0 and r.stderr == ""
        out = json.loads(r.stdout)
        assert out["header_unit_hints"]["percent"] == 1
        assert out["footer_unit_hints"]["annual"] == 1
        if args:
            assert out["drawing"]["drawing_unit_hints"]["annual"] == 1
        assert "PRIVATE-" not in r.stdout
        assert synth.SECRET_LABEL not in r.stdout and "987.654321" not in r.stdout and "123456789" not in r.stdout


@pytest.mark.parametrize(
    "drawing",
    [
        b"<PRIVATE-XML></mismatch>",
        b"<PRIVATE-XML>" * 65 + b"</PRIVATE-XML>" * 65,
        b'<!DOCTYPE x [<!ENTITY unit "PRIVATE-ENTITY per cent">]><x>&unit;</x>',
    ],
)
def test_cli_layout_refuses_bad_drawing_xml_without_diagnostics(tmp_path, drawing):
    path = synth.save(synth.forecast_book(), tmp_path / "PRIVATE-PATH.xlsx")
    synth.rewrite(path, {}, {"xl/drawings/PRIVATE-PART.xml": drawing})
    r = _run(str(path), "--layout")
    assert r.returncode == 2 and r.stderr == ""
    out = json.loads(r.stdout)
    assert out == {"sha256": out["sha256"], "status": "refused"}
    assert "PRIVATE-" not in r.stdout
