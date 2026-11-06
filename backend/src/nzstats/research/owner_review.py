"""One local owner-review package (Phase 4R): an index of the human decisions still open, linked to the review sheets.

Built from metadata only. It lists each existing local review sheet with its size and a short hash (the files are hashed, never
displayed), regenerates the gold sheet from the stored document alone, and asks the decisions the project has recorded as open.
Nothing here is a decision: every choice, the reviewer's name and the date are typed or clicked by the owner in the page, and the
page only downloads a file. It makes no network request, reads no model output and prefills no approval.

Blind until gold exists (PR 46 review). The gate is one decision, taken on the server before any HTML is built: `_gold_check` says
whether the owner's gold extension is saved, valid and bound to this document version. Without it the page is assembled from the
`BLIND_GROUPS` and the gold worksheet only. The paths, names, sizes, hashes and descriptions of model-derived files, and every
decision whose wording comes from model output, are not read, rendered, linked or hidden in the markup, script or metadata.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from nzstats.research.gold_extension import GoldExtensionError, load_extension, write_worksheet

PACKAGE_VERSION = 1
GOLD_EXTENSION_FILE = "annotations/gold-extension-v{version}.json"

# Where the sheets other phases wrote live, relative to the data directory.
EXISTING_SHEETS = {
    "periods": (
        "phase-4q/period-review-worksheet.html",
        "The five rejected facts and the year each one carries, for you to check against the PDF.",
    ),
}
AI_WRITTEN = {
    "phase4o": (
        "phase-4n/run-treasury-20261102/human-review.html",
        "Phase 4O Treasury output: all 18 claims with their evidence and the verifier's findings. It is MODEL OUTPUT. Rejected and unreviewed.",
    ),
    "ai_pack": (
        "annotations/phase-4q-feu-2026-10-29.json",
        "An AI reading of the 29 October report. It is not human gold. Open it only after you have finished your own marks.",
    ),
    "comparison": (
        "phase-4q/feu-comparison.md",
        "An AI comparison of the two Treasury reports. Not a review.",
    ),
}


# Everything below is read, listed and linked only after the owner's gold is saved, valid and bound (see `_gold_check`). Of these, only
# the review packet and the period worksheet are linked; the AI pack and the AI comparison are listed, never linked.
LINKED_AFTER_GOLD = {
    "phase-4n/run-treasury-20261102/human-review.html",
    "phase-4q/period-review-worksheet.html",
}


@dataclass(frozen=True)
class Decision:
    id: str
    ask: str
    options: tuple[str, ...]


def _who(item: str) -> tuple[str, ...]:
    return (
        f"{item}: the IMF's",
        f"{item}: the Treasury's",
        f"{item}: another organisation or the market's",
        f"{item}: cannot tell from the document",
    )


YEAR_OPTIONS = (
    "The year is stated for this figure",
    "The year is not stated: the model added it",
    "The year is stated only for a comparison, or in another sentence",
    "Cannot tell",
)

GROUPS: tuple[tuple[str, str, str, tuple[Decision, ...]], ...] = (
    (
        "C",
        "Treasury version 3 gold",
        "Mark the gold sheet in this package from the document alone: accepted-eligible, expected rejection, ambiguous, and third-party "
        "forecasts. Then download the file and save it where the status below says.",
        (
            Decision(
                "gold-done",
                "I finished the gold marks myself, without model output, and saved the file.",
                ("Yes", "Not yet"),
            ),
            Decision(
                "third-party-in-scope",
                "Third-party forecasts (other organisations, markets, banks) count toward recall.",
                ("Yes, they count", "No, author's own only"),
            ),
        ),
    ),
    (
        "A",
        "Phase 4O Treasury output: whose forecasts?",
        "Only after your gold marks in section A: open the Phase 4O packet. Five forecasts carry an IMF label, and two name the IMF only in the sentence before the figure.",
        tuple(
            Decision(
                f"imf-label-{n}",
                f"forecasts[{n}] is labelled IMF. Who made it?",
                _who(f"forecasts[{n}]"),
            )
            for n in range(1, 6)
        )
        + (
            Decision(
                "missing-content",
                "Is important content missing from the summary? Say what, in the note.",
                ("Yes, see note", "No", "Cannot tell"),
            ),
        ),
    ),
    (
        "B",
        "The years on the five rejected facts",
        "Only after your gold marks in section A: open the period worksheet. Facts 2 and 3 need you most: fact 2's period is only in the previous sentence and fact 3's year is only in its comparison.",
        tuple(
            Decision(f"year-fact-{n}", f"facts[{n}]: is its year in the report?", YEAR_OPTIONS)
            for n in range(5)
        ),
    ),
    (
        "D",
        "The unsupported OCR decision date",
        "The AI pack dates the OCR decision 28 October. The Treasury text does not state that day. RBNZ's own stored release (version 2) says Wednesday 28 October "
        "and the same 4:3 hold at 2.75%.",
        (
            Decision(
                "ocr-decision-date",
                "What should happen to the item?",
                (
                    "Accept 28 October, on the RBNZ version 2 evidence",
                    "Correct the date (write it in the note)",
                    "Move the item to a pack bound to version 2",
                    "Drop the item",
                ),
            ),
        ),
    ),
    (
        "E",
        "Documented false rejections and unknowns",
        "Nine true claims in the AI pack are rejected by design, and a few wordings pass that a person must judge. Keeping a rule as it is the default: "
        "it never loosens a check.",
        (
            Decision(
                "fr-period",
                "A true figure beside a comparison is rejected for its period (5 claims).",
                ("Keep rejecting", "Ask for a reviewed design"),
            ),
            Decision(
                "fr-forecast-as-fact",
                "A true outturn is rejected because its sentence mentions an expectation (3 claims).",
                ("Keep rejecting", "Ask for a reviewed design"),
            ),
            Decision(
                "fr-second-hand",
                "A decision reported second-hand cannot pass (1 claim).",
                ("Keep rejecting", "Ask for a reviewed design"),
            ),
            Decision(
                "fr-unit",
                "A price per barrel has no unit in the contract (1 claim).",
                ("Keep rejecting", "Ask for a contract change proposal"),
            ),
            Decision(
                "economists-author",
                "'Economists expect' and 'staff expect' are read as the author's own people, so an author label passes.",
                ("Accept as it is", "Treat as an outside group (a reviewed change)"),
            ),
            Decision(
                "wording-gaps",
                "The five listed wording gaps in the Phase 4Q record stay as documented limits.",
                ("Accept", "Ask for a reviewed fix"),
            ),
        ),
    ),
    (
        "F",
        "Rights and the next experiment",
        "Nothing here authorises a run. A hosted run needs a new version-specific consent bound to a new freeze.",
        (
            Decision(
                "treasury-page-checked",
                "I checked the Treasury publication page for the 29 October report in a browser.",
                ("Yes", "Not yet"),
            ),
            Decision(
                "third-party-pages",
                "For any hosted run of version 3: the table and third-party pages (4 and 5).",
                ("Exclude them: prose pages 1 to 3 only", "Include them", "Decide later"),
            ),
            Decision(
                "next-experiment",
                "Which one-attempt experiment should be prepared for review? (It uses the last lifetime attempt.)",
                ("A: Treasury version 3, prose pages 1 to 3", "B: RBNZ version 2", "Neither yet"),
            ),
        ),
    ),
)

# The one partition that decides what a page without valid gold may show: the gold group is source-derived, the rest is not.
BLIND_GROUPS = GROUPS[:1]
GATED_GROUPS = GROUPS[1:]

EXPORT_JS = r"""
function collect(meta, answers) {
  const errors = [];
  const t = (v) => (v === undefined || v === null ? "" : String(v).trim());
  if (!t(meta.reviewer)) errors.push("Type your own name.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(t(meta.reviewed_on))) errors.push("Type the date as YYYY-MM-DD.");
  const decisions = {};
  Object.keys(answers).forEach((id) => {
    const a = answers[id];
    if (t(a.choice) || t(a.note)) decisions[id] = { choice: t(a.choice) || null, note: t(a.note) || null };
  });
  if (!Object.keys(decisions).length) errors.push("Answer at least one question.");
  return {
    errors: errors,
    file: { kind: "owner-review-decisions", package_version: meta.package_version, reviewer: t(meta.reviewer),
            reviewed_on: t(meta.reviewed_on), decisions: decisions },
  };
}
"""
GLUE_JS = r"""
const meta0 = JSON.parse(document.getElementById("meta").textContent);
const STORE = "owner-review-" + meta0.package_id;
const q = (s) => document.querySelector(s);
function read() {
  const answers = {};
  document.querySelectorAll("[data-d]").forEach((box) => {
    const checked = box.querySelector("input[type=radio]:checked");
    answers[box.dataset.d] = { choice: checked ? checked.value : "", note: box.querySelector("textarea").value };
  });
  return { reviewer: q("#reviewer").value, reviewed_on: q("#reviewed_on").value, answers };
}
function save() { try { localStorage.setItem(STORE, JSON.stringify(read())); } catch (e) { /* optional */ } }
function restore() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE) || "null"); if (!s) return;
    // Your name and the date are typed again each session.
    document.querySelectorAll("[data-d]").forEach((box) => {
      const a = (s.answers || {})[box.dataset.d]; if (!a) return;
      box.querySelectorAll("input[type=radio]").forEach((r) => { r.checked = r.value === a.choice; });
      box.querySelector("textarea").value = a.note || "";
    });
  } catch (e) { /* ignore a damaged draft */ }
}
document.addEventListener("input", save); document.addEventListener("change", save);
q("#export").addEventListener("click", () => {
  const r = read();
  const out = collect({ reviewer: r.reviewer, reviewed_on: r.reviewed_on, package_version: meta0.package_version }, r.answers);
  const list = q("#problems"); list.textContent = "";
  out.errors.forEach((e) => { const li = document.createElement("li"); li.textContent = e; list.appendChild(li); });
  if (out.errors.length) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out.file, null, 2)], { type: "application/json" }));
  a.download = "owner-decisions-" + out.file.reviewed_on + ".json"; a.click();
});
restore();
"""

CSS = """
body{font:15px/1.55 system-ui,sans-serif;margin:1.5em auto;max-width:900px;padding:0 1em;color:#1a1a1a;background:#fff}
@media (prefers-color-scheme:dark){body{color:#e8e8e8;background:#161616}input,textarea{background:#222;color:#eee}a{color:#8ab4f8}}
section{border:1px solid #9995;border-radius:8px;padding:1em 1.2em;margin:1.2em 0}h2{margin-top:0}
.d{border-top:1px solid #9994;padding:.7em 0}.d label{display:block;margin:.15em 0}textarea{width:100%;box-sizing:border-box}
.warn{border:2px solid #b00020;border-radius:6px;padding:.6em .8em}table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border:1px solid #9995;padding:4px 6px;text-align:left}code{font-size:13px}
"""


def _short_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _inside(path: Path, root: Path) -> bool:
    """Whether `path` really lives under `root` once symbolic links are followed."""
    return path.resolve().is_relative_to(root.resolve())


def _file_row(label: str, why: str, path: Path, link: bool) -> str:
    if not path.is_file():
        return f"<tr><td>{html.escape(label)}</td><td colspan=3>not found at <code>{html.escape(str(path))}</code></td></tr>"
    stat = path.stat()
    when = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    name = html.escape(label)
    cell = f"<a href='file://{quote(str(path.resolve()))}'>{name}</a>" if link else name
    return (
        f"<tr><td>{cell}<br><small>{html.escape(why)}</small></td><td>{stat.st_size:,} bytes</td>"
        f"<td>{when}</td><td><code>{_short_hash(path)}</code></td></tr>"
    )


def _gold_check(conn: sqlite3.Connection, data_dir: Path, version: int) -> tuple[bool, str]:
    """Whether the owner's gold extension for this version is saved, valid and bound to it, with a status line. Reads no text from it."""
    path = data_dir / GOLD_EXTENSION_FILE.format(version=version)
    if not path.is_file():
        return False, f"not saved yet: expected at {path}"
    if not _inside(path, data_dir):
        return False, f"found at {path} but it is outside the data directory"
    try:
        extension = load_extension(path)
    except GoldExtensionError:
        return False, f"found at {path} but it is not a valid gold extension"
    row = conn.execute(
        "SELECT text_sha256 FROM research_document_version WHERE id = ?", (version,)
    ).fetchone()
    if (
        row is None
        or extension.version_id != version
        or extension.text_sha256 != row["text_sha256"]
    ):
        return False, f"found at {path} but it is not bound to this document version"
    return True, f"saved and valid: {len(extension.items)} items, bound to version {version}"


def gold_status(conn: sqlite3.Connection, data_dir: Path, version: int) -> str:
    """The status line of `_gold_check`."""
    return _gold_check(conn, data_dir, version)[1]


def _decision(d: Decision) -> str:
    radios = "".join(
        f"<label><input type=radio name='{html.escape(d.id)}' value='{html.escape(o)}'> {html.escape(o)}</label>"
        for o in d.options
    )
    return (
        f"<div class=d data-d='{html.escape(d.id)}'><b>{html.escape(d.ask)}</b>{radios}"
        "<label>Note (optional)<textarea rows=2></textarea></label></div>"
    )


WARNING_BLIND = (
    "<p class=warn>Private and local. An AI prepared this index and wrote none of the answers. Nothing here is a human review until you "
    "answer, type your own name and download the file. It approves no hosted run, no display and no promotion. "
    "Nothing on this page is sent anywhere.</p>"
)
WARNING_UNLOCKED = WARNING_BLIND.replace(
    "no promotion.", "no promotion of any AI-written annotation."
)
WITHHELD_NOTE = (
    "<p><small>The other review sections are withheld until your gold file is saved and valid. "
    "Save it, then build this package again.</small></p>"
)


def _sections(groups: tuple[tuple[str, str, str, tuple[Decision, ...]], ...], status: str) -> str:
    out = []
    for position, (_, title, intro, decisions) in enumerate(groups):
        letter = "ABCDEFGH"[position]
        extra = (
            f"<p><b>Gold file status:</b> {html.escape(status)}</p>"
            if decisions[0].id == "gold-done"
            else ""
        )
        out.append(
            f"<section><h2>{letter}. {html.escape(title)}</h2><p>{html.escape(intro)}</p>{extra}"
            + "".join(_decision(d) for d in decisions)
            + "</section>"
        )
    return "".join(out)


def _after_gold_table(data_dir: Path) -> tuple[str, int]:
    """The listing of model-derived and AI-written sheets. Only called once the gold check has passed."""
    rows = []
    found = 0
    for rel, why in (*EXISTING_SHEETS.values(), *AI_WRITTEN.values()):
        path = data_dir / rel
        if (path.is_symlink() or path.exists()) and not _inside(path, data_dir):
            # Not stat-ed, not hashed, not linked: a symlink out of the data directory is refused, whatever it points at.
            rows.append(
                f"<tr><td>{html.escape(Path(rel).name)}</td>"
                "<td colspan=3>not listed: it resolves outside the data directory</td></tr>"
            )
            continue
        found += path.is_file()
        rows.append(
            _file_row(
                Path(rel).name, why, path, rel in LINKED_AFTER_GOLD and _inside(path, data_dir)
            )
        )
    table = (
        "<h3>Open only after your own marks are finished</h3>"
        "<table><tr><th>File</th><th>Size</th><th>Modified</th><th>SHA-256 (start)</th></tr>"
        + "".join(rows)
        + "</table>"
    )
    return table, found


def build_package(
    conn: sqlite3.Connection, data_dir: Path, out_dir: Path, version: int
) -> dict[str, object]:
    """Write the package into `out_dir` (private) and return counts and statuses only.

    The gold check runs first and alone selects the page. Without valid gold, no model-derived path is read, stat-ed or hashed.
    """
    out_dir = out_dir.resolve()
    if not out_dir.is_relative_to(data_dir.resolve()):
        raise GoldExtensionError("the package must be written under the data directory")
    created = not out_dir.exists()
    out_dir.mkdir(parents=True, exist_ok=True)
    if created:
        os.chmod(out_dir, 0o700)
    for name in ("index.html", f"gold-worksheet-v{version}.html"):
        if (out_dir / name).is_symlink():
            raise GoldExtensionError("a package file is a symbolic link")
    gold_path = out_dir / f"gold-worksheet-v{version}.html"
    sentences = write_worksheet(conn, version, gold_path)
    unlocked, status = _gold_check(conn, data_dir, version)

    groups = GROUPS if unlocked else BLIND_GROUPS
    sheets = [
        _file_row(
            f"Gold worksheet, version {version} (this package)",
            "Interactive. From the document alone. Downloads your gold file.",
            gold_path,
            True,
        )
    ]
    sheets_found, sheets_expected = 1, 1
    after = WITHHELD_NOTE
    if unlocked:
        after, found = _after_gold_table(data_dir)
        sheets_found += found
        sheets_expected += len(EXISTING_SHEETS) + len(AI_WRITTEN)

    package_id = hashlib.sha256(f"{version}:{PACKAGE_VERSION}".encode()).hexdigest()[:16]
    meta = json.dumps({"package_id": package_id, "package_version": PACKAGE_VERSION})
    page = (
        "<!doctype html><meta charset=utf-8>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; form-action 'none'\">"
        "<meta name=viewport content='width=device-width,initial-scale=1'><meta name=robots content=noindex>"
        f"<title>Owner review package</title><style>{CSS}</style><h1>Owner review package</h1>"
        + (WARNING_UNLOCKED if unlocked else WARNING_BLIND)
        + "<h2>Sheets</h2><table><tr><th>Sheet</th><th>Size</th><th>Modified</th><th>SHA-256 (start)</th></tr>"
        + "".join(sheets)
        + "</table>"
        f"<p>Gold worksheet: {sentences} candidate sentences.</p>"
        + after
        + "<div style='margin-top:1em'><label>Your name <input id=reviewer autocomplete=off></label> "
        "<label>Date (YYYY-MM-DD) <input id=reviewed_on placeholder='YYYY-MM-DD'></label></div>"
        + _sections(groups, status)
        + "<p><button id=export type=button>Download my decisions</button></p><ul id=problems role=alert></ul>"
        "<p>Save the file under <code>data/phase-4r/owner-review/</code>. It records choices and notes, not a consent or a signature.</p>"
        f"<script type='application/json' id='meta'>{meta}</script><script>{EXPORT_JS}{GLUE_JS}</script>"
    )
    index = out_dir / "index.html"
    fd = os.open(index, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(page)
    return {
        "index": str(index),
        "gold_sentences": sentences,
        "decision_groups": len(groups),
        "decisions": sum(len(g[3]) for g in groups),
        "gold_status": status,
        "review_sections": "enabled"
        if unlocked
        else "withheld until your gold file is saved and valid",
        "sheets_found": sheets_found,
        "sheets_expected": sheets_expected,
    }
