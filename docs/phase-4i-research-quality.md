# Phase 4I: economic intelligence quality and private preview readiness

31 October 2026, from main `8a60872` (after Phase 4H, PR #32), branch `feat/phase-4i-research-quality`. Inputs:
[phase-4h-execution.md](phase-4h-execution.md), [data-sources/research.md](data-sources/research.md).

**Local-model pilot: GO WITH CONDITIONS.** The deterministic layers are ready for a two-document local pilot. It
cannot start until the owner records the approvals listed under [Outstanding permissions](#outstanding-permissions).

## Boundaries kept

- Neither report was sent to any model, hosted or local. Nothing was downloaded, no model server was started, and no
  institutional page was fetched. `llm_processing` stays `denied` and `public_display`/`private_display` stay `none`
  for every source. `config/research_sources.toml` is unchanged.
- Report text was not read into the agent session either. The real-document checks print only item numbers, verifier
  codes and counts. Page layout was established from masked shapes (letters replaced by `x`, digits by `9`, line
  breaks kept) and from flags saying whether an organisation's name appears on a line.
- The Stats NZ on-open refresh, Netlify, Docker, public publishing and the ingestion schedulers are untouched.

## 1. Research contract version 2

`OutlookSummary.contract_version` is `2` for new summaries. Each kind of content now has its own place:

| Category | Contract field | Notes |
|---|---|---|
| Reported economic facts | `facts[]` (`ReportedFact`) | `source` (who produced the figure, as written), `value`, `unit`, `period`, `definition.measure`, `definition.adjustment` (`seasonally_adjusted`, `unadjusted`, `trend`, `not_stated`) |
| Institutional interpretations | `outlook`, `drivers[]`, `risks[]`, `uncertainty` | unchanged |
| Institution-authored forecasts | `forecasts[]` with `issuer_role = "author"` | `issuer` names the author |
| Third-party forecasts | `forecasts[]` with `issuer_role = "third_party"` | `issuer` names the forecaster (the IMF, the OECD, market pricing) |
| Monetary policy decisions | `decisions[]` (`PolicyDecision`) | `instrument` (`ocr`), `action` (`hold`/`increase`/`decrease`), `rate`, `decided_on` (ISO date), `vote_for`/`vote_against` (both or neither), `decision_maker` |
| Forward guidance | `guidance[]` | `text`, `issuer` |
| Assumptions and scenarios | `assumptions[]` | `text`, `scenario` (null for a baseline assumption) |

Every forecast needs an issuer. The verifier reports `missing_issuer` for any version 2 forecast without one.

**Backward compatibility.** A summary stored under version 1 loads unchanged. The new lists are empty and its
forecasts have no issuer. The verifier treats such a forecast as the author's own and checks it as that, so an IMF
figure stored as an unattributed v1 forecast is still caught. The prompt is `outlook-v3`: rules 10 to 13 cover the
categories, issuers, decisions and layout. The request now names the document's author, which changes the input hash.

The public API (Phase 3C) gains no fields. It now leaves a third party's forecast out of the institution's
forecasts, comparisons, history and evaluation, so an IMF number in a Treasury document can never be shown as a
Treasury forecast.

## 2. Verifier `verify-3`

Each Phase 4H finding has a failing-first test. Synthetic fixtures in `tests/research/test_verify_*.py` copy the
real layouts.

| Phase 4H finding | Rule (code) | How |
|---|---|---|
| IMF forecasts attributed to Treasury | `issuer_mismatch`, `issuer_not_in_evidence`, `issuer_unclear` (warning) | `research/issuers.py` knows the organisations and their publications (IMF/WEO, Treasury/PEU/HYEFU, RBNZ/MPS, OECD, the banks, market pricing). A figure is credited to whoever the table row label, the table's titled caption, its clause or sentence, or (when the sentence names nobody) the sentence before it credits. Naming the subject of a forecast ("the RBNZ is expected to cut") does not credit it. "We" and "our" are the author. |
| Negative numbers split across PDF lines | `value_not_in_evidence`, `quote_truncated` | A sign left alone at a line end joins the number that starts the next line (`-\n7%` is -7%). A quote that renders the break as a space (`- 7%`) still matches. A quote that starts after the sign is truncated. |
| Table values under the wrong column heading | `table_column_mismatch`, `table_column_unverified`, `table_heading_unverified` (warning) | Lines are classified as a row of years, labelled rows of cells, numbers only, or text. A cell's column is read from the row of years directly above the rows. A wrong year is an error. When years repeat across groups of columns, the group labels are detached from the rows, so the column is unverifiable and refused: in the real Treasury file the group labels come out in the opposite order to the columns. A single-group table asks the reviewer to confirm the heading. |
| Chart-axis residue | `axis_residue` | Three or more number-only lines in a row, or a number-only line with three or more numbers, are residue. A value, or a statement number, found only there is refused. |
| Decisions misclassified as predictions | `decision_as_forecast`; for decisions `decision_not_in_evidence`, `decision_action_contradiction`, `decision_date_not_supported`, `vote_not_in_evidence`, `vote_not_captured`, `decision_date_assumed` (warning) | An OCR forecast whose clause says what was decided ("agreed to hold", "voted", "held the OCR") before any forward-looking word is an error. A decision needs decision wording, a rate stated in percent, the action, a date stated near the quote (or the publication date, warned unless "today"), and the vote whenever the evidence states one ("voted 4–3", "four members … three members"). |
| Missing or ambiguous statistical definitions | `definition_not_in_evidence`, `definition_not_stated`, `definition_ambiguous`, `definition_omitted` (warnings except the first) | A claimed adjustment basis or "average" measure must be stated in the evidence. A fact with a value and no stated basis is reported: show it as the institution's figure and do not compare it with an official series. Facts also get `forecast_as_fact`, `period_not_supported`, the unit rules and `source_not_named` (warning). |

**Regressions found on the real documents and fixed failing-first** (each narrows a rule only where the stored text
proved it wrong):

1. "US$96/b" read as the self-reference "us", which made an IMF-credited clause look ambiguous. Self-references are
   now case-sensitive.
2. "October 2026" followed by a chart-axis label "-10" read as the fiscal year 2026-10, a false
   `fiscal_calendar_mismatch` on Treasury's own forecasts. A fiscal pair is now `2026/27`, `2026–27` or `2026-27`,
   never a year followed by a spaced, signed number. The year-stated check uses the same rule.
3. "Annual CPI inflation … in the December quarter" was read as a quarterly change (`period_basis_mismatch`). When
   the evidence names the same quarter as the horizon, the basis now comes from the label. A "June 2027 quarter"
   horizon for evidence that says "year to June 2027" is still an error.
4. "A net 40% of respondents expected conditions to improve" is a survey outturn, not a forecast. "X is estimated
   to be 3.7 percent" is still refused as a fact.

No existing rule was removed. All 26 verify-2 rules still have their tests, and the synthetic replay floors were met
or raised.

**Known limits.** One of the four IMF prose forecasts (Treasury item 28) is credited to the IMF only after the
figure. Presented as the Treasury's, it draws `issuer_unclear`, a warning for the reviewer, not an error.
Value-free facts are judged on their whole sentence.

## 3. Evaluation against the real-document annotations

Run offline from `backend/`. The outputs and annotations are git-ignored:

```sh
python ../scripts/check_research_baseline.py ../data/phase-4h/annotations/baseline-2026-10-31.json \
    --gold ../data/annotations/phase-4i-evaluate.json      # writes nothing; counts and codes only
```

| Check | Result |
|---|---|
| 46 anchored reference items | 46/46 quotes equal their section slice at the recorded offsets (whitespace-normalised) and are found cleanly by verify-3; 46/46 pages inside their section |
| Issuer, annotated issuer kept | no issuer finding on any of the 9 forecasts |
| Issuer swapped (IMF to Treasury, or the reverse) | 8/9 errors; Treasury item 28 a warning (above) |
| Gold forecasts, as written | Treasury net migration 21,900 and RBNZ CPI 4.4% (December quarter) verify cleanly. Treasury's four GDP and CPI forecasts are table cells under repeated year columns: refused as `table_column_unverified`, by design |
| Split minus sign (Treasury item 5) | signed value verifies; dropping the sign is caught |
| RBNZ decision (hold at 2.75%, 28 October 2026, 4–3) | verifies; omitting the vote, a wrong vote and reporting it as a forecast are each caught |
| Monthly net migration (3,190; 1,530) | unstated basis reported (`definition_not_stated`); an invented seasonally adjusted basis is an error |
| Stats NZ comparisons, at the vintage published by each document's date | 16 match and 2 not comparable, all as Phase 4H recorded. Treasury's monthly migration is refused (`not_comparable`: no stated adjustment basis, and Stats NZ publishes the measure on more than one basis), never compared with the unadjusted `mig.m.net` |
| Scoring a contract v2 reference output | raw precision and recall 1.0, numerical fidelity 1.0, issuer accuracy 1.0, decision recall and fidelity 1.0; accepted recall 0.167 because the Treasury table forecasts are refused |

The vintage comparison is `research/official_compare.py`. The official value comes from the newest stored release
published on or before the document's date (Pacific/Auckland), never a later revision. A figure is compared only on
the same adjustment basis, and the official value is rounded to the precision the document states, half away from
zero. Tests use real excerpts. GDP growth in the March 2026 quarter was first published as 0.8 and revised to 0.9:
a document dated 1 August is compared with 0.8, one dated 15 October with 0.9.

Comparison callers should pass the figure as written (a string or `Decimal`) to preserve fractional precision:
numeric floats lose trailing decimal zeros. Whole-number trailing zeros indicate rounding to tens or hundreds.

**Gold corrections.** The Phase 4H gold file (`phase-4h-evaluate.json`, SHA-256 `74d4d9fd…`) used the unit `people`,
which the contract does not have, so numerical fidelity would have marked a faithful `persons` claim wrong. The
annotation loader now refuses units the contract lacks, and `research evaluate` refuses that file. The corrected copy
`data/annotations/phase-4i-evaluate.json` (git-ignored, SHA-256 `f04d64f0…`) uses `persons`, marks each gold forecast
`issuer_role = "author"`, and adds the RBNZ decision. It records the RBNZ horizon as written ("December quarter"):
Phase 4H had added "2026", a year the document does not state there. Both annotation files were written by Claude Code
and are marked "owner review pending".

**Evaluation tooling.** Gold forecasts may carry `issuer_role`, and gold decisions are scored. New metrics are
`issuer_accuracy`, `decision_recall` and `decision_fidelity`. When gold covers only the author's forecasts, an
unmatched third-party forecast is excluded. A third-party claim matching an author's annotated indicator, horizon,
value and unit is scored as a possible issuer error. Gold lacks evidence identities, so a coincidentally identical
third-party forecast is ambiguous and its issuer score needs human interpretation.
The synthetic replay gains case 13 (attribution and decisions), a faithful contract v2 output plus nine probes, one
for each new error. Replay, prompt `outlook-v3`, verifier `verify-3`: raw precision and recall 0.913, accepted
precision 0.944 and recall 0.739, numerical fidelity 0.952, scenario accuracy 1.0, indicator F1 0.947, citation
correctness 0.959, completeness 0.875, verified 0.786, issuer accuracy 1.0, decision recall and fidelity 1.0, and 38
of 38 probes behaving as labelled. This replay measures the deterministic layers, not a model.

## 4. Private research preview (foundation, disabled)

Built and tested, but off. No source has a `private_display` approval, so it shows nothing even when switched on.

| Requirement | Design |
|---|---|
| Separate permission per source | `private_display` (`none` or `summary`) with `private_display_approved_by`, `_on` and `_note`: its own recorded decision, separate from access, manual import, LLM processing and public display. Refused unless the source is approved or has an approved manual import, and has `content_policy = "full_text"`. Shows nothing while `llm_processing` is `denied`. Public display never grants it, and it never grants public display |
| Explicit operator enablement | `nzstats serve --private-research`. Without the flag the routes are not mounted. Off by default |
| Loopback only | The flag refuses any non-loopback bind and exits 2 before the app exists. `NZSTATS_RESEARCH_ALLOW_NONLOOPBACK` does not override it. Each request needs a loopback `Host` (no DNS rebinding), a same-origin `Origin` when sent, `Sec-Fetch-Site: same-origin` when sent, and `X-NZStats-Client: dashboard`. No CORS. GET only. `Cache-Control: no-store`, `X-Robots-Tag: noindex` |
| No leakage into public or static snapshots | Separate gate (`research/private.py`) and router (`research/private_api.py`). The snapshot exporter's app has no research routes (tested). Nothing writes research into a snapshot |
| No unreviewed AI summary shown as verified | Only verified, reviewer-approved summaries are shown, the newest approved one per current, non-duplicate, unpurged version, re-verified with the current verifier on every request. Unreviewed and rejected summaries are never shown, labelled or not |
| Attribution, dates, evidence | Institution name, document title, link (https on the institution's allowed hosts), document date, version, stored date, licence and licence URL. Every block has its evidence: section, page and quote |
| Separation from official statistics | Every item is labelled "Institutional commentary … Not an official statistic". Every block has a badge: institutional view, the institution's own forecast, third-party forecast, policy decision, forward guidance, assumption, or "figure as reported by the institution (not the official series)". No Stats NZ value is mixed in |

`research summary ID` shows `private preview: yes`, or the reason it is not. The browser page is not built yet:
it is the next PR, once a reviewed summary exists to show. It should read only these routes and keep the badges and
the label.

## 5. Local AI pilot readiness

**Provider.** The existing `openai_compatible` adapter is suitable. Only an `http://127.0.0.1`, `::1` or `localhost`
base URL counts as local. Redirects are not followed and proxy variables are ignored. It sends `temperature: 0` and
`max_tokens` and parses strictly. A hosted or paid call is impossible while `llm_processing` is `local_only`.

**Machine.** An Apple M4 with 24 GB of unified memory. Phase 4H suggested 20–35B parameters, but a 32B model at 4-bit
(about 19 GB) leaves too little memory for a 32k-token context. The input for one document is about 9k tokens for
the FEU plus about 4k for the rules and schema. Recommended:

- **Runtime:** `llama.cpp`'s `llama-server`, bound to `127.0.0.1` on a port other than the dashboard's (8081, say).
  Avoid wrappers that can route a local-looking model name to a hosted service.
- **Model:** an Apache-2.0 instruction-tuned model of about 14B parameters at Q5 (about 10 GB), with a 24k–32k
  context and a quantised KV cache, for example Qwen3-14B with its reasoning mode switched off. Reasoning output
  before the JSON would fail the strict parse. A 24B model at Q4 (for example Mistral Small 3.x) is the alternative,
  with a context of 16k or less. Confirm the current release, licence and file hash when downloading. Record the
  weights file name, SHA-256, quantisation and `llama-server --version` in `docs/progress.md`.
- **Network:** confirm no outbound connection during the run (for example `lsof -nP -iTCP -sTCP:ESTABLISHED`
  filtered on the server process, or an outbound firewall rule).

**Settings** (environment only; nothing is stored):

```sh
NZSTATS_LLM_PROVIDER=openai_compatible
NZSTATS_LLM_BASE_URL=http://127.0.0.1:8081/v1
NZSTATS_LLM_MODEL=<the model name llama-server reports>
NZSTATS_LLM_INPUT_USD_PER_MTOK=0
NZSTATS_LLM_OUTPUT_USD_PER_MTOK=0
NZSTATS_LLM_MAX_OUTPUT_TOKENS=6000      # contract v2 output is longer than v1
NZSTATS_LLM_TIMEOUT_SECONDS=900          # a 13k-token prompt and 6k output on a laptop GPU
NZSTATS_LLM_MAX_RETRIES=0                # one attempt per document in the pilot
NZSTATS_LLM_MAX_DOCUMENTS=1
```

**Registry change, per source, as one reviewed edit each** (not applied):

```toml
llm_processing = "local_only"
llm_processing_note = "<the owner's reading of the terms, the approver and the date>"
```

Treasury: Crown copyright under CC BY 4.0 unless indicated, with credit to the Treasury. RBNZ: reproduction is
permitted with acknowledgement, if accurate and not misleading. Automated access is prohibited without written
permission, which this does not change: the document was imported by a person. Never `hosted`.

**Two-document evaluation** (Treasury version 1, RBNZ version 2):

```sh
nzstats research summarise treasury --dry-run && nzstats research summarise rbnz --dry-run
nzstats research summarise treasury --limit 1 && nzstats research summarise rbnz --limit 1
nzstats research summaries && nzstats research summary <ID>
nzstats research evaluate --annotations ../data/annotations/phase-4i-evaluate.json --model <model>
```

**Acceptance** (against the 4I gold):

- No hosted call and no outbound connection.
- Citation correctness at least 0.95. Numerical fidelity 1.0 on aligned gold forecasts. Issuer accuracy 1.0.
- No IMF figure credited to the Treasury in any accepted output.
- RBNZ decision found with rate, date and vote (decision recall and fidelity 1.0), and no `decision_as_forecast`.
- Treasury's table forecasts either omitted or refused as `table_column_unverified`, never accepted under a column.
- Monthly migration, if reported, carries `adjustment = "not_stated"` and is never compared.
- Raw recall of the six gold forecasts at least 5/6.
- A reviewer reads every summary before any approval. Showing it privately needs its own approval.

The expected ceiling: until PDF extraction keeps column positions, the verifier refuses Treasury summaries that
include the table forecasts, so at most the RBNZ summary and a Treasury summary without them can be approved.

## 6. Verification

- Failing-first: every new rule and each real-layout regression has a test that failed before the change (recorded
  per rule in the PR).
- Backend (Python 3.14 venv): **3,340 passed** (Phase 4H: 3,203); `tests/research` 1,595. Ruff lint and format
  clean.
- Frontend: no API model used by the frontend changed (`CapabilitiesOut` and the public research models are
  unchanged; the private routes are not in the published OpenAPI). The frontend suites were not rerun.
- Security: private routes tested for off-by-default (indistinguishable from an unknown path), non-loopback binds
  (refused, no override), Host, Origin, `Sec-Fetch-Site` and client-header checks, GET only, no-store, private fields
  absent, an unreadable registry showing nothing, and absence from the exporter's app.
- Hosted Actions remain billing-blocked, so local results are the only test evidence.

## Outstanding permissions

1. `llm_processing = "local_only"`, separately for Treasury and for RBNZ, with the owner's note. Never `hosted`.
2. The runtime and the model: approve the choice, download the weights, and record the hash.
3. Owner review of the two Claude-written annotation files (the 4H baseline and the 4I gold) before their scores
   count as acceptance.
4. `private_display = "summary"` per source when a preview is wanted, plus approval to build the browser page.
5. Unchanged: `public_display = none`, `NZSTATS_PUBLIC_RESEARCH` off, automated access refused (`needs_review`),
   and RBNZ automated access needing the Bank's prior written permission.
6. A follow-up for column-aware PDF extraction (word positions), so Treasury's table forecasts can be verified.
