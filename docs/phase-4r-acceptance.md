# Phase 4R: economic intelligence acceptance and production readiness

5 November 2026, Pacific/Auckland. Baseline: main `1c021c9db647f4eb4acb021ab02aa1e2beabf8ad`, equal to the expected baseline. PRs #43, #44 and
#45 are all in it (`5d182a3` merged #45 into #44's branch; `b117e9b` and `1c021c9` merged the rest). No work was merged after it. CI on main
was green for the merge of #43.

**No OpenRouter request, crawl, scheduler, deployment, approval or merge happened in this phase.** This record holds metadata only: counts,
codes, hashes and public report titles and dates. Report text, model output, gold contents and the key stay in ignored `data/`.

## Verdicts

| Subsystem | Verdict | Why |
|---|---|---|
| Stats NZ on-open refresh, labour | **GO WITH CONDITIONS** | One real new release was ingested and reconciled (below). CPI, GDP, card spending and migration have no live new-release proof |
| Official statistics display | **GO** (unchanged) | No code changed. Frontend and browser suites pass |
| Latest Treasury report, internal draft view | **GO**, loopback only | Newest report listed correctly, older draft marked historical, access controls hold |
| Economic intelligence, private and public display | **NO-GO** | No complete, verified, human-reviewed summary exists. Human gold is still missing |
| Verifier `verify-4` | **GO WITH CONDITIONS** | Material gap closed, 0 new acceptances in 657,024 cases. Known wording limits remain, listed below |
| Next hosted experiment | **NOT READY** | Owner decisions and a reviewed code change come first. Proposal below |
| Public site, Netlify | **NO-GO** (unchanged) | Not touched |

## Stats NZ live refresh: the first real new-release acceptance

Phase 4H's tracker (issue #31) still said live acceptance awaited a supported release. The local record shows one happened and was not written
down. It is read-only evidence from `data/nzstats.db` and the pre-refresh backup.

| Check | Result |
|---|---|
| Trigger | Refresh run 16, `open`, 4 Nov 2026 06:08:42 to 06:09:46 UTC. Completed, 1 discovered, 1 ingested, 0 unchanged, 0 pending, 0 failures, 6 logical requests (limit 40) |
| Release | Labour market statistics, September 2026 quarter, published 3 Nov 21:45 UTC (4 Nov 10:45 NZDT) |
| Ingestion | `ingest_run` 23 `ingested` (the design commits each release in one transaction). 11 new vintages (8 household labour force survey series, 3 labour cost index series), one bundle hash |
| Backup first | `pre-refresh-20261104T060920Z`, created 06:09:20, one second before the ingest began. `nzstats status` reports it verified, 46 raw artifacts, 0 problems |
| Only additions | Against that backup: +1 `ingest_run`, +11 `vintage`, +11 `vintage_series_definition`, +1,635 `observation`, +2 `raw_artifact`. Every earlier observation is identical (same digest) |
| Raw files | Both new artifacts exist and match their stored SHA-256 and size. Host `www.stats.govt.nz`, HTTP 200 |
| Reconciliation, independent of the adapter | Unemployment 5.7 percent (June 5.6), underutilisation 13.8 percent: match the release headline. Employed 2,891 + unemployed 174 = labour force 3,065, and the three rates recompute to 5.7, 66.4 and 70.4. The three labour cost index series match the official file's own references (index 1,467, 0.5 percent a quarter, 2.1 percent a year) and the changes recompute to 0.55 and 2.09 from the index |
| Integrity | `PRAGMA integrity_check` ok, no foreign key problems, schema 13. `nzstats status`: overall ok, calendar current, next release card spending on 12 Nov |

**Not proven.** Only the latest quarter's headline series were checked against the official file, not every historical row. The browser
showing refreshed charts was seen by the owner but not recorded, so cache invalidation rests on the frontend tests. One release family
(labour) is not CPI, GDP, card spending or migration. The refresh ran on the owner's Mac under the existing authorisation, so no
further live action was taken here.

**Issue #31.** Stage A's exit criteria (verified backup, one bounded live refresh, correct status, independent reconciliation) are met for
labour. Stage B's (two verified documents, annotation and extraction report, source gates, a private preview design) were met by Phases 4I to 4Q.
The issue can close once the owner accepts this record and the GO WITH CONDITIONS above. It was not closed from here.

## The newest Treasury report

| Version | Title | Published | Pages | Source hash | Local file hash |
|---|---|---|---|---|---|
| 1 | Fortnightly Economic Update, 15 Oct 2026 | 19 Oct | 7 | `63aaa9df15` | matches |
| 3 | Fortnightly Economic Update, 29 Oct 2026 | 2 Nov | 5 | `f39f10d7ee` | matches |
| RBNZ 2 | OCR held at 2.75% | 28 Oct | none (HTML) | `ee38b509c0` | matches |

Version 3 has its own `research_manual_import` row, raw artifact and hashes. Version 1 is intact and current. There are 3 summary rows, none for version 3,
and 3 usage and 3 reservation rows, none for version 3. The internal draft feed lists version 3 as "Newest" by publication date, with no draft, and
version 1's draft says a newer report exists. Table and third-party content and the Crown crest stay recorded in `phase-4q-treasury-feu-refresh.md`.
The 29 October page itself still needs the owner's own check in a browser (automated access got HTTP 403).

## Phase 4Q findings

| Finding | Class | Action |
|---|---|---|
| An outside group of forecasters ("Analysts expect", "Investors anticipate", "according to analysts", "expected by analysts") labelled as Treasury's | **Confirmed bug** | Fixed, failing first. See below |
| A reporter that only "said" the figure ("The IMF said growth will be 3%") labelled as Treasury's | **Confirmed bug** | Fixed |
| Gold scoring: a right period or issuer repeated raises period exactness and issuer accuracy (3/4 where 1/2 is right) | **Confirmed bug** | Fixed, failing first |
| True figure beside a comparison rejected for its period (5 claims) | Known conservative limitation | Unchanged. It fails closed |
| A true outturn rejected because its sentence mentions an expectation (3) | Known conservative limitation | Unchanged |
| A decision reported second-hand cannot pass (1); no unit for a price per barrel (1) | Known limitation | Unchanged. Contract change needs its own review |
| "Economists", "staff", "officials expect" are read as the author's own people | Human-review dependency | Left as designed. Owner decision `economists-author` |
| Treasury versus IMF labels on five Phase 4O forecasts; the years on five facts | Human-review dependency | In the owner package |
| `ocr-decision` date not stated in the Treasury text, though RBNZ's own release gives it | Human-review dependency | In the owner package |
| "since 2028" taking a start date as a period; wordings 4Q listed for the owner | Known limitation | Unchanged. Not patched, per the brief |
| Table cells, and groups beside a table row label, get the older checks only | Known limitation | Prose only for the new wording |
| Pack scoring tools had no way to record a human's marks | Test and tooling gap | Gold form below |
| Verifier and scoring changes had only tests from the author's own model family | Test coverage gap | Two independent review cycles, below |
| Wording gaps still open: lead-ins such as "Last month analysts", "Westpac analysts", "Fitch", "The central bank said", "analysts continue to expect", forms after the figure ("..., analysts expect") | Known limitation | Listed. Not patched. These pass under `verify-3` and `verify-4` alike |

## Code and tooling changes

- **`reported_more()` in `issuers.py`.** Outside groups (analysts, forecasters, investors, banks, commentators, rating agencies, survey respondents),
  "according to" and "expected by" them, and an organisation that "said", "noted" or "warned" a figure now block an author label. The older wording is
  byte-identical to `1c021c9`. The new wording is computed apart, can only add a rejection, never credits the author, and is never waived by a credit the older
  wording found. The author's own people ("our economists and analysts", possessives) are skipped, but not investors, banks or "analysts at ANZ".
- **Evidence it only tightens.** Old code against new code on 657,024 invented sentence, claim and label cases, author and third-party: **0 newly pass, 52,995 newly rejected.** 297
  honest pairings (the subject matches the label): 0 newly rejected. The real-data probes are identical before and after: 59 corruptions caught, 0 missed,
  45 not measurable, 9 true claims rejected, one gold problem (`decided_on_not_supported`).
- **Gold scoring.** A repeated right period or issuer counts once, a repeated wrong one every time. Nothing else changed in the scorers.
- **Gold form.** `gold-worksheet` now writes a local page from the document alone. The reviewer marks sentences, types their own name and date and ticks the
  attestation, and the page downloads a file that `load_extension` still checks. Nothing is prefilled or restored from a draft, the page blocks the network,
  and the file is mode 0600. Node tests run the export logic against the same validator.
- **`research owner-review-package`.** One local index: sheets with size and a short hash (never their content), the gold form, the gold file's status, and 23
  decisions in six groups. Gold comes first and model output is linked only after it. Output must stay under the data directory.
- **`scripts/openrouter_key_reading.py`.** Owner-run and read-only. One GET to the key metadata endpoint, no inference, no spend. It prints numbers and
  booleans, never the key, and compares the key's usage with the ledger.
- No threshold changed, no prompt changed, and `verify-4` keeps its label because no stored row has used it.

### Independent review

Two cycles, of at most three, by a fresh reviewer working only on invented text.

| Cycle | Finding | Outcome |
|---|---|---|
| 1 | A third-party label could be waived by the new wording (P0), and the first version changed the older code's control flow | Fixed by moving the new wording apart. The invariant became structural |
| 1 | Honest claims newly rejected: "our economists and forecasters", possessives | Fixed |
| 1 | Common-wording gaps (lead-ins, verb forms, passives, "according to a survey of") | Partly closed. The rest is listed above |
| 2 | **Invariant holds: 0 regressions across about 118,000 comparisons, every label role.** Verdict APPROVE for the verifier | Recorded |
| 2 | P3: unvalidated server fields in the key reading, `--out` chmod and overwrite, model output linked beside the blind gold sheet, a draft restoring the attestation, a weaker JS check than the validator | All fixed, with tests |

An automated security review of the pushed commits raised four points: a group-name exemption not scoped to third-party labels (fixed, with a test),
the new wording not applied to table cells (a documented limit), the own-people skip being too wide (narrowed), and the new wording being waivable by an
older credit (fixed). The reviews are independent of this session's reasoning, but their model family is the author's. No Codex review ran on these commits.

## The internal draft view

Checked on the real data on loopback, offline, counts and codes only. The stored `research_summary` rows were unchanged by reading.

| Requirement | Result |
|---|---|
| Newest Treasury report shown correctly | Yes: 29 Oct, published 2 Nov, "Newest", no draft |
| Older commentary marked historical | Yes: the 15 Oct draft carries "covers an earlier report" naming the newer one |
| Failed claims labelled | 7 of 18 failed, each with its problem codes and evidence, 1 warning, 10 with no problem found. Same counts as Phase 4O under `verify-4` |
| Never labelled verified | `official`, `approved` and `reviewed` flags all false |
| Source, publication and reference period distinguishable | "Published by the institution", "Document version, stored", and each claim's own "Period" and "Horizon" |
| Access | Without the client header, a foreign host or cross-site: 403. Public and private research routes: 404 |
| Desktop and mobile | Research browser suite 18 passed, 3 skipped (screenshot specs), phone and desktop. No UX defect found, so none changed |

## The ledger

| Item | Local record |
|---|---|
| Runs, summaries, usage, reservations | 2, 3, 3, 3. Every reservation settled on reported billing |
| Spend | US$0.508462812 of US$5, so US$4.491537188 remains. Run totals and usage totals agree |
| Attempts | Treasury v1: 2 (consumed). RBNZ v2: 1. Version 3: 0. **3 of 4 lifetime attempts used** |
| Key reading | **Not done here.** The key stays out of this session. The owner runs `scripts/openrouter_key_reading.py` once, which compares the key's usage with the ledger without printing the key |

## The next experiment

Both options cost less than the remaining budget. The binding limit is attempts: **either one uses the last of the four.** Neither resets anything.

| | A. Treasury version 3, prose pages 1 to 3 | B. RBNZ version 2, HTML |
|---|---|---|
| Evidence readiness | Newest report. AI gold pack, probes and the new gold form exist. 130 candidate sentences | Bound to the older gold only. No new-format gold, no probes and no pack |
| Expected value | Fortnightly source and the report the dashboard calls newest. Tests prompt `outlook-v5` where it matters most (added years) | Tests `outlook-v5` on the document that truncated twice, but the OCR decision is already known and short |
| Remaining factual risks | Issuer attribution (tested by the fixes above), years, comparisons. Not a clean before and after against version 1 | The same, plus thin prose. RBNZ's attempt would be its second |
| Accuracy measurable | Yes, once the owner's gold exists | Not yet |
| Rights readiness | Crown copyright, CC BY 4.0, third-party material and logos excluded. Prose pages 1 to 3 avoid the credited tables and charts on pages 4 and 5 | Copyright permitting accurate reproduction with acknowledgement. Hosted processing is a separate owner decision. Automated access needs the Bank's written permission, so import stays manual |
| Estimated input | About 9,400 tokens, from the section sizes (13,141 characters) and the two recorded runs | About 11,200 tokens (17,011 characters) |
| Bound, with the output cap of 12,000 | About US$0.31 at list price, about US$0.40 reserved by the Phase 4O method | About US$0.31, about US$0.42 reserved |
| Likely actual | US$0.10 to 0.16 (Phase 4O: US$0.126 for 16,693 in, 2,455 out) | US$0.10 to 0.18 |

**Recommendation: A, and not yet.** It is the only option whose accuracy can be measured, and its rights position is the clearer one. It waits for these, in order:
the owner's human gold for version 3 (written without model output), the owner's decisions on third-party pages and the Treasury page check, the key reading, a reviewed
code change that adds version 3 to `PILOT_VERSIONS` and an experiment scope (today `freeze` on version 3 refuses), and a fresh, expiring, version-specific
consent bound to a new freeze. The experiment stays one request, no retry, effort low, cap 12,000. The scoring targets stay as `phase-4q-evidence-grounding.md`
sets them, fixed by the owner before the run. If the verifier rejects the summary, the raw measures still answer the question and it is not retried.

## Owner review package

Run `research owner-review-package`, then open `data/phase-4r/owner-review/index.html`. It lists 23 open decisions in six groups: the gold form first, then the
Phase 4O IMF labels, the five fact years, the OCR decision date, the documented false rejections and the rights and next-experiment questions. It does
not complete any of them. A person must answer, type their own name and download the file. Nothing in it is a signature, a consent or a promotion of the AI pack.

## Verification

Run on the final tree of this branch (head `881ab01` plus documentation), in a clean worktree, Python 3.14.6.

| Check | Result |
|---|---|
| Backend suite | **4,580 passed**, 1 existing warning, 8 min 44 s |
| Ruff lint, format | Clean |
| Frontend tests, typecheck, build | 546 passed, clean, built |
| Browser suite, research browser suite | 174 passed. 18 passed, 3 skipped |
| Static and public isolation | 315 passed, 24 skipped on the rerun. **The first run had 1 failure**: a full-page pixel parity spec (card spending, desktop) that then passed alone and in the full rerun. It is recorded as a visual-timing flake and not hidden. No frontend or API code changed |
| Dependency audit, npm | 0 vulnerabilities |
| Dependency audit, Python | `pypdf` 6.21.2 and `certifi` 2026.7.22 in the **local venv** have fixed releases. The repository already requires `pypdf>=6.21.4`, so CI is not affected. The PDF tests pass on pypdf 6.21.4 and certifi 2026.10.23. The owner should run `pip install -U pypdf certifi` in the venv |
| Source-permission, verifier and gold tests | Part of the backend suite |

## Remaining owner decisions

1. Finish the human gold for version 3 in the gold form, blind to every model output and to the AI pack, and save it where the package says.
2. Answer the Phase 4O IMF-label and fact-year questions, and the `ocr-decision` date.
3. Check the Treasury 29 October publication page in a browser, and say whether any hosted run excludes pages 4 and 5.
4. Accept or reject the limits above, including `economists-author`.
5. Run the key reading once.
6. Choose whether to prepare Option A. That chooses a plan for review. It authorises no run.
7. Update the local venv, and decide whether to close issue #31.

## Next milestone

Phase 4S: with the owner's gold and decisions in hand, score the AI pack against it (`score-gold`), then build the reviewed code change for the version 3 experiment and
its freeze. Do not run it. A run needs a new consent.
