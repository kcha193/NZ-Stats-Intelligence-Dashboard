import pytest

from xlsxinspect.guard import emit


def test_emit_accepts_counts_booleans_codes_and_int_lists():
    out = emit(
        {
            "status": "ok",
            "sheets": [{"rows": 3, "state": "hidden", "label_columns": [1, 2]}],
            "archive": {"vba_part": False},
        }
    )
    assert '"rows": 3' in out


@pytest.mark.parametrize(
    "data",
    [
        {"status": "Fictional label"},  # a document string as a value
        {"Indicator": 1},  # a document string as a key
        {"sheets": [{"rows": "3"}]},
        {"archive": {"max_ratio": float("nan")}},
        {"sheets": [{"label_columns": ["A"]}]},
        {"sha256": "not-a-hash"},
        {"sha256": "z" * 64},
    ],
)
def test_emit_refuses_anything_that_could_carry_document_text(data):
    with pytest.raises(ValueError):
        emit(data)


def test_emit_allows_a_sha256_only_under_its_own_key():
    digest = "a" * 64
    assert digest in emit({"sha256": digest})
    with pytest.raises(ValueError):
        emit({"status": digest})
