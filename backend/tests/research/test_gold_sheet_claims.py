"""Phase 4R review round 5: one sentence can hold several claims, so the gold worksheet lets a reviewer mark each one.

A sentence such as "We expect growth of 3% in 2029 and 4% in 2030" holds two value/period pairs. The form used to give each sentence one
set of fields, so only one gold item could be exported for it, which understated the recall denominator and made a correct claim for the
other year look unmatched. The extension format and the scorer already work per item, so only the form changes (SYNTHETIC FIXTURE text).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nzstats.research import gold_sheet
from nzstats.research.gold_extension import GoldExtension

from .test_gold_extension import DIGEST, META

TWO_CLAIMS = "We expect growth of 3% in 2029 and 4% in 2030."
OTHER = "The IMF expects growth of 2.9% in 2027."
SENTENCES = [(1, 1, TWO_CLAIMS), (1, 1, OTHER)]
FIXED = {"version_id": 1, "text_sha256": DIGEST}
FIRST = "p1s1n0"
JSDOM = Path(__file__).resolve().parents[3] / "frontend" / "node_modules" / "jsdom"


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _pure(tmp_path, expression):
    script = tmp_path / "pure.js"
    script.write_text(gold_sheet.PURE_JS + f"\nconsole.log(JSON.stringify({expression}));")
    out = subprocess.run(
        [_node(), str(script)], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(out.stdout)


def _row(id, **over):
    base = {"id": id, "category": "accepted_eligible", "kind": "forecast", "terms": "growth",
            "unit": "percent"}  # fmt: skip
    return {**base, **over}


# --- the export logic, which has no DOM ---------------------------------------------------------


def test_two_claims_from_one_sentence_export_as_two_distinct_valid_items(tmp_path):
    rows = [
        _row(FIRST, value="3", period_as_stated="2029"),
        _row(FIRST + "x1", value="4", period_as_stated="2030"),
    ]
    result = _pure(
        tmp_path, f"collect({json.dumps(META)}, {json.dumps(rows)}, {json.dumps(FIXED)})"
    )
    assert result["errors"] == []
    extension = GoldExtension.model_validate(result["extension"])
    assert [(i.id, i.value, i.period_as_stated) for i in extension.items] == [
        (FIRST, 3, "2029"),
        (FIRST + "x1", 4, "2030"),
    ]


def test_the_export_refuses_a_repeated_row_id_as_the_validator_does(tmp_path):
    rows = [_row(FIRST, value="3"), _row(FIRST, value="4")]
    result = _pure(
        tmp_path, f"collect({json.dumps(META)}, {json.dumps(rows)}, {json.dumps(FIXED)})"
    )
    assert any("same row id" in e for e in result["errors"])


def test_a_repeated_id_on_a_row_left_blank_is_no_error(tmp_path):
    rows = [_row(FIRST, value="3"), _row(FIRST, category="")]
    result = _pure(
        tmp_path, f"collect({json.dumps(META)}, {json.dumps(rows)}, {json.dumps(FIXED)})"
    )
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("taken", "expected"),
    [
        ([], FIRST + "x1"),
        ([FIRST, FIRST + "x1"], FIRST + "x2"),
        (
            [FIRST, FIRST + "x2"],
            FIRST + "x1",
        ),  # the first free number, so a removed claim's id is reused
        ([FIRST, "p1s1n1x1"], FIRST + "x1"),  # another sentence's extra does not count
    ],
)
def test_a_new_claim_takes_the_first_free_id_of_its_own_sentence(tmp_path, taken, expected):
    assert _pure(tmp_path, f"nextClaimId({json.dumps(FIRST)}, {json.dumps(taken)})") == expected


def test_only_well_formed_extra_ids_are_read_back_from_a_draft_in_order(tmp_path):
    ids = [
        FIRST + "x2",
        "x1",
        FIRST,
        FIRST + "xfoo",
        FIRST + "x1",
        "p1s1n0x1x1",
        "p1s1n1x10",
        "p1s1n1x2",
    ]
    assert _pure(tmp_path, f"extraClaimIds({json.dumps(ids)})") == [
        FIRST + "x1",
        FIRST + "x2",
        "p1s1n1x2",
        "p1s1n1x10",
    ]


def test_the_count_shows_claims_and_the_sentences_that_hold_them(tmp_path):
    rows = [
        _row(FIRST),
        _row(FIRST + "x1"),
        _row("p1s1n1", category=""),
        _row("p1s1n2"),
        _row("p1s1n2x1", category=""),
    ]
    assert _pure(tmp_path, f"markedCounts({json.dumps(rows)})") == {"claims": 3, "sentences": 2}


# --- the page ------------------------------------------------------------------------------------


def _page():
    return gold_sheet.render(1, DIGEST, SENTENCES)


def test_every_sentence_can_take_another_claim_from_one_copy_of_the_controls():
    page = _page()
    assert page.count("data-add") >= 2 and "Add another claim from this sentence" in page
    template = re.search(r"<template id=claim-controls>(.*?)</template>", page, re.S)
    assert template is not None
    fields = re.findall(r"data-f='(\w+)'", template.group(1))
    assert sorted(fields) == sorted(set(fields)) and "category" in fields and "value" in fields
    # The controls of the sentence row itself are the same markup, so a claim never lacks a field.
    row = re.search(r"<tr data-row='p1s1n0'.*?</tr>", page, re.S).group(0)
    assert re.findall(r"data-f='(\w+)'", row) == fields


def test_extra_claims_add_no_prefill_no_network_and_no_restored_header():
    page = _page()
    assert "http://" not in page.replace("http-equiv", "") and "https://" not in page
    assert "default-src 'none'" in page and "form-action 'none'" in page
    assert "{ rows: read().rows }" in page
    assert 'q("#attest").checked =' not in page and 'q("#annotator").value =' not in page
    assert not re.search(r"<input[^>]* (?:value|checked)\b", page) and " selected" not in page


# --- the page, run in a DOM ----------------------------------------------------------------------

DRIVER = r"""
const { JSDOM } = require(process.argv[2]);
const html = require("fs").readFileSync(process.argv[3], "utf8");
const dom = new JSDOM(html, {
  runScripts: "dangerously", url: "http://localhost/",
  beforeParse(w) {
    w.URL.createObjectURL = () => "blob:test";
    w.HTMLAnchorElement.prototype.click = function () {};
    if (!w.CSS) w.CSS = { escape: (s) => String(s).replace(/[^\w-]/g, "\\$&") };
  },
});
const { window } = dom, { document } = window;
const rowOf = (id) => document.querySelector('tr[data-row="' + id + '"]');
const field = (id, f, v) => {
  const el = rowOf(id).querySelector('[data-f="' + f + '"]');
  el.value = v;
  document.dispatchEvent(new window.Event("input", { bubbles: true }));
};
const add = (id) => rowOf(id).querySelector("[data-add]").click();
const header = () => {
  document.querySelector("#annotator").value = "Test Person";
  document.querySelector("#reviewed_by").value = "Test Reviewer";
  document.querySelector("#reviewed_on").value = "2026-11-03";
  document.querySelector("#attest").checked = true;
};
const ids = () => [...document.querySelectorAll("tr[data-row]")].map((tr) => tr.dataset.row);
const exported = () => {
  document.querySelector("#export").click();
  return {
    problems: [...document.querySelectorAll("#problems li")].map((li) => li.textContent),
    json: document.querySelector("#json").value ? JSON.parse(document.querySelector("#json").value) : null,
  };
};
"""


def _dom(tmp_path, scenario):
    if not (JSDOM / "package.json").is_file():
        pytest.skip("jsdom is not installed (frontend dependencies)")
    page = tmp_path / "sheet.html"
    page.write_text(_page())
    script = tmp_path / "dom.js"
    script.write_text(DRIVER + scenario)
    out = subprocess.run(
        [_node(), str(script), str(JSDOM), str(page)],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout)


def test_in_the_page_a_reviewer_adds_marks_and_exports_both_claims_of_a_sentence(tmp_path):
    result = _dom(
        tmp_path,
        """
const base = "p1s1n0";
field(base, "category", "accepted_eligible"); field(base, "kind", "forecast");
field(base, "terms", "growth"); field(base, "value", "3"); field(base, "period_as_stated", "2029");
add(base);
const second = ids().find((i) => i.startsWith(base + "x"));
field(second, "category", "accepted_eligible"); field(second, "kind", "forecast");
field(second, "terms", "growth"); field(second, "value", "4"); field(second, "period_as_stated", "2030");
header();
console.log(JSON.stringify({ ids: ids(), out: exported(), marked: document.querySelector("#marked").textContent }));
""",
    )
    assert result["ids"] == [
        FIRST,
        FIRST + "x1",
        "p1s1n1",
    ]  # the new claim sits under its own sentence
    assert result["out"]["problems"] == []
    items = GoldExtension.model_validate(result["out"]["json"]).items
    assert [(i.id, i.value, i.period_as_stated) for i in items] == [
        (FIRST, 3, "2029"),
        (FIRST + "x1", 4, "2030"),
    ]
    assert result["marked"] == "2"


def test_in_the_page_each_new_claim_has_its_own_id_and_a_removed_one_leaves_no_item(tmp_path):
    result = _dom(
        tmp_path,
        """
const base = "p1s1n0";
add(base); add(base); add("p1s1n1");
const afterAdds = ids();
rowOf(base + "x1").querySelector("[data-remove]").click();
const afterRemove = ids();
add(base);
console.log(JSON.stringify({ afterAdds, afterRemove, afterReAdd: ids() }));
""",
    )
    assert result["afterAdds"] == [FIRST, FIRST + "x1", FIRST + "x2", "p1s1n1", "p1s1n1x1"]
    assert result["afterRemove"] == [FIRST, FIRST + "x2", "p1s1n1", "p1s1n1x1"]
    assert sorted(result["afterReAdd"]) == sorted(
        [FIRST, FIRST + "x1", FIRST + "x2", "p1s1n1", "p1s1n1x1"]
    )


def test_in_the_page_an_unmarked_extra_claim_exports_nothing(tmp_path):
    result = _dom(
        tmp_path,
        """
const base = "p1s1n0";
field(base, "category", "accepted_eligible"); field(base, "kind", "forecast");
field(base, "terms", "growth"); field(base, "value", "3"); field(base, "period_as_stated", "2029");
add(base); header();
console.log(JSON.stringify({ out: exported() }));
""",
    )
    assert [i["id"] for i in result["out"]["json"]["items"]] == [FIRST]


def test_in_the_page_a_saved_draft_brings_back_the_extra_claims_and_never_the_header(tmp_path):
    result = _dom(
        tmp_path,
        """
const base = "p1s1n0";
add(base); field(base + "x1", "category", "accepted_eligible"); field(base + "x1", "value", "4");
add(base); field(base + "x2", "value", "9");
header();
document.dispatchEvent(new window.Event("input", { bubbles: true }));
rowOf(base + "x1").remove(); rowOf(base + "x2").remove();   // as after a reload
document.querySelector("#annotator").value = ""; document.querySelector("#attest").checked = false;
window.restore();
console.log(JSON.stringify({
  ids: ids(),
  value1: rowOf(base + "x1").querySelector('[data-f="value"]').value,
  category1: rowOf(base + "x1").querySelector('[data-f="category"]').value,
  value2: rowOf(base + "x2").querySelector('[data-f="value"]').value,
  annotator: document.querySelector("#annotator").value,
  attest: document.querySelector("#attest").checked,
}));
""",
    )
    assert result["ids"] == [FIRST, FIRST + "x1", FIRST + "x2", "p1s1n1"]
    assert (result["value1"], result["category1"], result["value2"]) == (
        "4",
        "accepted_eligible",
        "9",
    )
    assert result["annotator"] == "" and result["attest"] is False


def test_in_the_page_a_draft_row_for_a_sentence_that_is_gone_is_ignored(tmp_path):
    result = _dom(
        tmp_path,
        """
window.localStorage.setItem("gold-sheet-" + JSON.parse(document.getElementById("fixed").textContent).text_sha256,
  JSON.stringify({ rows: [{ id: "p9s9n9x1", value: "1" }, { id: "p1s1n0x1", value: "2" }] }));
window.restore();
console.log(JSON.stringify({ ids: ids() }));
""",
    )
    assert result["ids"] == [FIRST, FIRST + "x1", "p1s1n1"]


def test_the_file_the_form_writes_for_two_claims_loads_and_counts_both_in_the_denominator(
    tmp_path,
):
    from nzstats.research.gold_extension import load_extension

    rows = [
        _row(FIRST, value="3", period_as_stated="2029"),
        _row(FIRST + "x1", value="4", period_as_stated="2030"),
    ]
    result = _pure(
        tmp_path, f"collect({json.dumps(META)}, {json.dumps(rows)}, {json.dumps(FIXED)})"
    )
    path = tmp_path / "gold-extension-v1.json"
    path.write_text(json.dumps(result["extension"]))
    extension = load_extension(path)  # the authority: it validates again when the file is scored
    assert len(extension.items) == 2
    assert {i.period_as_stated for i in extension.items} == {"2029", "2030"}
