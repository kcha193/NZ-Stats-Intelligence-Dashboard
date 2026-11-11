# Phase 4AE: multi-bank economic intelligence

10 November 2026, Pacific/Auckland. Baseline main `86a4515` (backend 5932 passed, 5 skipped). Design:
[spec](superpowers/specs/2026-11-10-phase-4ae-bank-research-design.md); plan:
[plan](superpowers/plans/2026-11-10-phase-4ae-bank-research.md); permissions: [matrix](phase-4ae-permissions-matrix.md);
operation: [runbook](phase-4ae-bank-runbook.md).

**No live ingestion exists for any bank.** All five (ANZ, ASB, BNZ, Westpac, Kiwibank) stay permission-denied, so the
capability is built and proven **offline on synthetic documents** and is dormant against the real registry. No bank contact,
hosted model call, paid inference, permission change, deployment or schedule was made.

## What it adds

An internal-only comparison of bank economic outlooks in the Economic Outlook page ("Bank outlooks"): the newest report and
the AI's reading of it per bank, forecasts by bank and target period, a median and range chart (a "consensus" only from three
banks, always "not a market consensus"), revisions across successive outlook reports, where banks disagree, a source-evidence
drawer, and source health. Official Stats NZ figures are unchanged; bank figures are never mixed into them.

## Reused unchanged

The registry and its gates, fetcher, discovery, ingest and versioning, manual import, extraction, contract v2, `verify-5`,
issuer attribution, summarise and policy workflow, the internal draft gate and its caveats, `compare`, `consensus`, `history`,
`evaluate`, `outcomes`, `health`, and the existing `research_*` tables. **No database migration.**

## Added

| Piece | File |
|---|---|
| Per-bank series, report kind and cadence (no permissions) | `backend/src/nzstats/research/banks.py` |
| Normalized forecast (raw value kept, adjustment and geography derived) | `bank_forecast.py` |
| Read-only view over gated, clean, own-issuer claims; reference markers | `bank_view.py` |
| Analytics wrapper: adjustment split, outlook-only aggregates, divergence, evaluation | `bank_analytics.py`, `bank_models.py` |
| Source states, metrics, `bank-status` | `bank_status.py`, `cli.py`, `health` JSON |
| Internal routes `/api/internal/bank-intelligence/{summary,forecasts,revisions,consensus,evaluation,freshness}` | `bank_api.py`, mounted by `drafts_api.py` only |
| Frontend section, hooks, chart | `frontend/src/components/outlook/bank/`, `src/api/bank.ts`, `src/charts/bankConsensus.ts` |
| Registry: BNZ and Kiwibank owner-supplied landing URLs; cadence for ANZ/ASB/Westpac | `config/research_sources.toml` (descriptive fields only) |

## Rules the analytics keep

- Only claims with no automated issue and no warning enter any aggregate; others are listed by fixed code.
- Seasonally adjusted, unadjusted and unstated figures are never aggregated together; quarterly, annual, calendar, fiscal,
  average and end-of-period figures stay apart as `compare.py` already ensures; a third party's forecast is never the bank's.
- Adjustment wording is taken out of the label the comparison reads once the adjustment is settled (`canonical_label`), so a
  bank that says "unadjusted" in its label and one that says it in its evidence are the same measure; `measure` keeps the label
  as stated and the evidence is untouched. A label that contradicts its evidence is left as stated.
- Only quarterly *outlook* reports feed consensus, divergence, revisions and evaluation; weekly notes are shown, labelled.
- Different values from a bank on one date for one measure and adjustment are a conflict, whether in one document or two: none
  is used. A conflict (or a conflicting pair of failed or warned claims) in a newer report also hides the bank's older figure.
- Missing stays missing: no interpolation, extrapolation, carry-forward or filling. When a bank's newer report has a claim for a
  measure that failed its checks, warned, or conflicted with another report of the same date, that bank's older figure for the
  measure is **not shown in its place** (code `newer_claim_unusable`): the table shows a dash, the group counts one fewer
  bank, and a "Left out" list names the bank and the reason under the table, the consensus and the revisions.
- Forecast versus actual uses stored Stats NZ vintages and the first-published actual; look-ahead is excluded. OCR is not
  evaluated (no authorized source). The official series is chosen with the bank layer's derived adjustment (label and evidence
  quote), not the label alone: a seasonally adjusted annual CPI, an unadjusted GDP or unemployment rate (only the seasonally
  adjusted series is stored) and a label that contradicts its evidence are excluded with a reason, never scored against another series.

## Verification

Backend, frontend, browser, static and isolation results are recorded in the pull request and in `progress.md`. The offline
replay (`backend/tests/research/test_bank_e2e.py`) imports synthetic reports through the real manual-import path, summarises
them through the real pipeline with a scripted local stand-in, reads the internal routes, includes one deliberately wrong claim
that is excluded, runs twice from scratch for byte-identical output, and shows the real bank keys stay permission-denied.

## Not done

Live ingestion (blocked by missing permissions); a deterministic PDF table parser (built in Phase 4AF, see [phase-4af-pdf-tables.md](phase-4af-pdf-tables.md)); any hosted or paid inference; deployment; unattended polling. Findings during the build: a visually-hidden element
inside a scrolling table widened the page at phone width (fixed and covered by a browser test).
