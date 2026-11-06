"""The reviewer's gold worksheet as one local HTML file that exports a gold extension (Phase 4R).

The sheet holds sentences of one document and nothing else: no model output, no pre-filled marks, no reviewer name and no
attestation. A person marks sentences, types their own name and ticks the attestation themselves, and the page downloads a JSON file
that `load_extension` still validates. Nothing is sent anywhere: the page's policy blocks every network request.

The export logic is pure (`collect`) and is tested under Node. It checks what it can, but `load_extension` stays the authority: it runs again when the file is scored.
"""

from __future__ import annotations

import html
import json

CATEGORY_HELP = {
    "accepted_eligible": "A fact, forecast or decision of the author that a good summary should state, with its period as written.",
    "third_party_forecast": "A forecast the document reports from someone else (the IMF, markets, a bank). Name the issuer.",
    "expected_rejection": "A claim a careful verifier should refuse (a table cell with no period, a figure whose year is not stated). Say why.",
    "ambiguous": "You cannot tell, or the document is unclear. It is left out of every denominator.",
}
DIRECTIONS = ("up", "down", "flat", "unclear")

# Pure: no DOM. `meta` are the typed header fields, `rows` the marked rows. Mirrors the Python validation in gold_extension.py.
PURE_JS = r"""
/*PURE-START*/
function collect(meta, rows, fixed) {
  const errors = [];
  const text = (v) => (v === undefined || v === null ? "" : String(v).trim());
  const shape = /^\d{4}-\d{2}-\d{2}$/;
  const real = (v) => { // a real calendar day, as the validator needs it
    if (!shape.test(v)) return false;
    const d = new Date(v + "T00:00:00Z");
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
  };
  const day = { test: real };
  const ai = /\b(?:claude|codex|gpt|chatgpt|openai|anthropic|gemini|llm|ai)\b/i;
  const tomorrow = new Date(Date.now() + 36 * 3600 * 1000).toISOString().slice(0, 10);
  if (!text(meta.annotator)) errors.push("Type the name of the person who wrote the marks.");
  if (!text(meta.reviewed_by)) errors.push("Type the name of the person who reviewed them.");
  if (!day.test(text(meta.reviewed_on))) errors.push("Type the review date as a real day, YYYY-MM-DD.");
  else if (text(meta.reviewed_on) > tomorrow) errors.push("The review date is in the future.");
  if (ai.test(text(meta.annotator)) || ai.test(text(meta.reviewed_by))) errors.push("The annotator and reviewer must be people.");
  if (meta.written_without_model_output !== true) errors.push("Tick the attestation only if it is true.");
  const items = [];
  const seenIds = new Set();
  rows.forEach((r, i) => {
    if (!text(r.category)) return;
    const where = "Row " + (i + 1) + ": ";
    // The validator refuses repeated ids, so the sheet says so before it writes a file.
    if (seenIds.has(r.id)) errors.push(where + "two marked rows have the same row id.");
    seenIds.add(r.id);
    const terms = text(r.terms).split(",").map((t) => t.trim()).filter(Boolean);
    if (!terms.length) errors.push(where + "give at least one word a claim about this must use.");
    const item = { id: r.id, category: r.category, kind: r.kind, terms: terms };
    if (!text(r.kind)) errors.push(where + "say whether it is a fact, a forecast or a decision.");
    if (text(r.value) !== "") {
      const v = Number(text(r.value));
      if (!/^-?\d+(\.\d+)?$/.test(text(r.value)) || !Number.isFinite(v)) errors.push(where + "the value is not a plain number.");
      else item.value = v;
    }
    for (const k of ["unit", "scenario", "issuer", "expected_reason"]) if (text(r[k])) item[k] = text(r[k]);
    if (text(r.period_as_stated)) item.period_as_stated = text(r.period_as_stated);
    if (text(r.direction)) item.direction = text(r.direction);
    if (text(r.issuer_role)) item.issuer_role = text(r.issuer_role);
    if (r.category === "third_party_forecast") {
      if (!item.issuer) errors.push(where + "a third-party forecast must name its issuer.");
      if (r.kind !== "forecast") errors.push(where + "a third-party forecast must be a forecast.");
      item.issuer_role = "third_party";
    }
    if (r.kind === "forecast" && item.value === undefined && r.category !== "ambiguous" && !item.direction)
      errors.push(where + "a forecast without a number must say its direction.");
    if (r.category === "expected_rejection" && !item.expected_reason) errors.push(where + "say why it should be refused.");
    if (r.kind === "decision" && item.period_as_stated && !day.test(item.period_as_stated))
      errors.push(where + "write a decision's date as a real day, YYYY-MM-DD.");
    items.push(item);
  });
  if (!items.length) errors.push("Mark at least one sentence.");
  const extension = {
    annotator: text(meta.annotator), reviewed_by: text(meta.reviewed_by), reviewed_on: text(meta.reviewed_on),
    written_without_model_output: meta.written_without_model_output === true,
    version_id: fixed.version_id, text_sha256: fixed.text_sha256, items: items,
  };
  return { errors: errors, extension: extension };
}
// A sentence can hold several claims ("3% in 2029 and 4% in 2030"). The first claim keeps the sentence's own row id, and each further
// claim takes that id plus "x1", "x2", and so on, so every item stays independently identified.
const EXTRA_CLAIM = /^(p\d+s\d+n\d+)x(\d+)$/;
function nextClaimId(base, taken) {
  let k = 1;
  while (taken.indexOf(base + "x" + k) !== -1) k++;
  return base + "x" + k;
}
function extraClaimIds(ids) {
  const seen = new Set();
  return ids.map((id) => EXTRA_CLAIM.exec(id)).filter((m) => m && !seen.has(m[0]) && seen.add(m[0]))
    .sort((a, b) => (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : Number(a[2]) - Number(b[2]))).map((m) => m[0]);
}
function markedCounts(rows) {
  const marked = rows.filter((r) => r.category);
  return { claims: marked.length, sentences: new Set(marked.map((r) => r.id.replace(/x\d+$/, ""))).size };
}
/*PURE-END*/
"""

GLUE_JS = r"""
const fixed = JSON.parse(document.getElementById("fixed").textContent);
const STORE = "gold-sheet-" + fixed.text_sha256;
const q = (s, el) => (el || document).querySelector(s);
function read() {
  const meta = {
    annotator: q("#annotator").value, reviewed_by: q("#reviewed_by").value, reviewed_on: q("#reviewed_on").value,
    written_without_model_output: q("#attest").checked,
  };
  const rows = [...document.querySelectorAll("tr[data-row]")].map((tr) => {
    const o = { id: tr.dataset.row };
    tr.querySelectorAll("[data-f]").forEach((el) => { o[el.dataset.f] = el.value; });
    return o;
  });
  return { meta, rows };
}
function save() { try { localStorage.setItem(STORE, JSON.stringify({ rows: read().rows })); } catch (e) { /* storage may be unavailable */ } }
const rowOf = (id) => document.querySelector('tr[data-row="' + CSS.escape(id) + '"]');
function addClaim(base, id) {
  const anchor = rowOf(base);
  if (!anchor) return null;
  const taken = [...document.querySelectorAll("tr[data-row]")].map((tr) => tr.dataset.row);
  const rid = id || nextClaimId(base, taken);
  if (taken.includes(rid)) return null;
  let last = anchor;
  while (last.nextElementSibling && last.nextElementSibling.dataset.sentence === base) last = last.nextElementSibling;
  const tr = document.createElement("tr");
  tr.dataset.row = rid; tr.dataset.sentence = base; tr.className = "extra";
  const cell = document.createElement("td");
  cell.colSpan = 3;
  const title = document.createElement("b");
  title.textContent = "Another claim from the sentence above";
  const remove = document.createElement("button");
  remove.type = "button"; remove.dataset.remove = ""; remove.textContent = "Remove this claim";
  cell.append(title, " ", remove, q("#claim-controls").content.cloneNode(true));
  tr.appendChild(cell);
  last.after(tr);
  return tr;
}
function restore() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE) || "null");
    if (!s) return;
    extraClaimIds(s.rows.map((r) => r.id)).forEach((id) => addClaim(id.replace(/x\d+$/, ""), id));
    // Names, the date and the attestation are never restored: each session you type and tick them again.
    s.rows.forEach((r) => {
      const tr = document.querySelector('tr[data-row="' + CSS.escape(r.id) + '"]');
      if (tr) tr.querySelectorAll("[data-f]").forEach((el) => { if (r[el.dataset.f] !== undefined) el.value = r[el.dataset.f]; });
    });
  } catch (e) { /* ignore a damaged draft */ }
}
function refresh() {
  const counts = markedCounts(read().rows);
  q("#marked").textContent = counts.claims;
  q("#marked-sentences").textContent = counts.sentences;
  save();
}
function exportJson() {
  const { meta, rows } = read();
  const out = collect(meta, rows, fixed);
  const box = q("#problems");
  box.textContent = "";
  out.errors.forEach((e) => { const li = document.createElement("li"); li.textContent = e; box.appendChild(li); });
  const area = q("#json");
  if (out.errors.length) { area.value = ""; return; }
  area.value = JSON.stringify(out.extension, null, 2);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([area.value], { type: "application/json" }));
  a.download = "gold-extension-v" + fixed.version_id + ".json";
  a.click();
}
document.addEventListener("click", (ev) => {
  const button = ev.target.closest ? ev.target.closest("button") : null;
  if (!button || !button.closest("tr[data-row]")) return;
  const tr = button.closest("tr[data-row]");
  if ("add" in button.dataset) { addClaim(tr.dataset.row); refresh(); }
  else if ("remove" in button.dataset) { tr.remove(); refresh(); }
});
document.addEventListener("input", refresh);
document.addEventListener("change", refresh);
q("#export").addEventListener("click", exportJson);
restore(); refresh();
"""

CSS = """
body{font:15px/1.5 system-ui,sans-serif;margin:1.5em auto;max-width:1100px;padding:0 1em;color:#1a1a1a;background:#fff}
@media (prefers-color-scheme:dark){body{color:#e8e8e8;background:#161616}input,select,textarea{background:#222;color:#eee}}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #9995;padding:6px;vertical-align:top;text-align:left}
details{margin-top:.4em}summary{cursor:pointer;font-weight:600}label{display:block;margin:.3em 0;font-size:13px}
input,select,textarea{font:inherit;max-width:100%}.warn{border:2px solid #b00020;padding:.6em;border-radius:6px}
tr.extra td{background:#9991}.sticky{position:sticky;top:0;background:inherit;padding:.5em 0;border-bottom:1px solid #9995}
"""


def _select(field: str, options: tuple[str, ...], blank: str = "") -> str:
    opts = "".join(
        f"<option value='{html.escape(o)}'>{html.escape(o or blank)}</option>"
        for o in ("", *options)
    )
    return f"<select data-f='{field}'>{opts}</select>"


def _controls() -> str:
    """The fields that describe one claim. One source: the sentence row and the template for further claims both use it."""
    return (
        f"<label>Group {_select('category', tuple(CATEGORY_HELP), 'not a claim (skip)')}</label>"
        f"<label>Kind {_select('kind', ('fact', 'forecast', 'decision'))}</label>"
        "<label>Words a claim about this must use (comma separated)<input data-f='terms'></label>"
        "<label>Value<input data-f='value' inputmode='decimal'></label>"
        "<label>Unit (for example percent)<input data-f='unit'></label>"
        "<label>Period exactly as written (a decision: YYYY-MM-DD)<input data-f='period_as_stated'></label>"
        f"<label>Who made it {_select('issuer_role', ('author', 'third_party'))}</label>"
        "<label>Issuer name<input data-f='issuer'></label>"
        "<label>Scenario (leave empty for the baseline)<input data-f='scenario'></label>"
        f"<label>Direction, if no number {_select('direction', DIRECTIONS)}</label>"
        "<label>Why it should be refused (expected rejection only)<input data-f='expected_reason'></label>"
    )


def _row(n: int, page: int | None, ordinal: int, text: str) -> str:
    rid = html.escape(f"p{page or 0}s{ordinal}n{n}")
    return (
        f"<tr data-row='{rid}' data-sentence='{rid}'><td>{page or ''}</td><td>{ordinal}</td><td>{html.escape(text)}"
        f"<details><summary>Mark this sentence</summary>{_controls()}"
        "<p><button type=button data-add>Add another claim from this sentence</button> "
        "<small>For a sentence that holds more than one claim, such as two years.</small></p></details></td></tr>"
    )


def render(version_id: int, text_sha256: str, sentences: list[tuple[int | None, int, str]]) -> str:
    """The sheet for one document version. `sentences` are (page, section ordinal, text) from the stored document only."""
    rows = "\n".join(
        _row(n, page, ordinal, text) for n, (page, ordinal, text) in enumerate(sentences)
    )
    fixed = json.dumps({"version_id": version_id, "text_sha256": text_sha256})
    help_items = "".join(
        f"<li><b>{html.escape(k)}</b>: {html.escape(v)}</li>" for k, v in CATEGORY_HELP.items()
    )
    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; script-src 'unsafe-inline'; "
        "style-src 'unsafe-inline'; form-action 'none'\">"
        "<meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content=noindex>"
        f"<title>Gold review worksheet: version {version_id}</title><style>{CSS}</style>"
        f"<h1>Gold review worksheet: version {version_id}</h1>"
        "<p class=warn>Private and local. Built from the document alone. Read the original PDF, and do not open any model output first. "
        "Copy periods exactly as written, and leave out a sentence you are unsure of. Written without seeing model output: you tick that "
        "below only if it is true. Nothing on this page is sent anywhere.</p>"
        f"<ul>{help_items}</ul>"
        "<div class=sticky><label>Annotator (your name)<input id=annotator autocomplete=off></label>"
        "<label>Reviewer (your name, or the person who checked)<input id=reviewed_by autocomplete=off></label>"
        "<label>Review date (YYYY-MM-DD)<input id=reviewed_on placeholder='YYYY-MM-DD'></label>"
        "<label><input type=checkbox id=attest> Written without seeing model output</label>"
        "<p>Marked: <b id=marked>0</b> claims in <b id=marked-sentences>0</b> of "
        + str(len(sentences))
        + " sentences. "
        "<button id=export type=button>Check and download gold extension</button></p>"
        "<ul id=problems role=alert></ul></div>"
        f"<template id=claim-controls>{_controls()}</template>"
        f"<table><tr><th>Page</th><th>Section</th><th>Sentence</th></tr>{rows}</table>"
        "<h2>Export preview</h2><textarea id=json rows=10 cols=80 readonly></textarea>"
        "<p>Save the downloaded file under <code>data/annotations/</code>, then run "
        "<code>nzstats research score-gold</code> against the stored summary.</p>"
        f"<script type='application/json' id='fixed'>{fixed.replace('<', chr(92) + 'u003c')}</script>"
        f"<script>{PURE_JS}{GLUE_JS}</script>"
    )
