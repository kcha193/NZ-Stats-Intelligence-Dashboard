# Ingestion health behavioural specification

Approved scope: one focused implementation and verification cycle on PR #1,
starting at `e087c40`; no merge. Specify behaviour first, reproduce defects with
real SQLite and lifecycle tests, then implement and verify.

## State model

Health is a projection of persisted attempts and **current** release status.
Classify attempts before selecting the latest meaningful one by ingest-run ID.
Timestamps do not order outcomes. Each release is evaluated independently; a
series is degraded if any of its releases has an outstanding failure.

| Outcome | Current release status | Meaning |
|---|---|---|
| `ingested`, `unchanged` | Any | Success; clears prior failure of this release |
| `failed` | Any | Failure; persists across neutral observations |
| `not_available` | `scheduled`, `delayed` | Neutral; does not supersede success or failure |
| `not_available` | `published`, `corrected`, `unavailable` | Failure: unresolved data gap |
| `skipped_no_adapter` | Any | Neutral; never evidence of recovery |

No meaningful outcome means neutral, not a successful source check. Existing
healthy series stay healthy across neutral observations; no health row is needed
for a series with only neutral observations.

## Behavioural table

Histories run left to right. `404` means `not_available`; `skip` means
`skipped_no_adapter`. Healthy means no outstanding failure, not necessarily a
new successful-check timestamp.

| Current status | History | Expected |
|---|---|---|
| Scheduled / delayed | 404; repeated 404; skip | Neutral |
| Published / corrected / unavailable | 404; repeated 404 | Degraded |
| Any | failed | Degraded |
| Scheduled / delayed | failed → 404 → 404 → skip | Degraded; original failure retained |
| Any | failed → skip | Degraded |
| Any | failed → unchanged / ingested | Healthy |
| Published | 404 → ingested | Healthy |
| Scheduled / delayed | failed → 404 → ingested → 404 | Healthy |
| Published / corrected / unavailable | failed → ingested → 404 | Degraded |
| Published | ingested → failed → unchanged → skip | Healthy |
| Published | ingested → failed → 404 → unchanged → failed | Degraded; newest failure |
| Series with A and B | failed A → neutral A → successful B | Degraded; A remains |
| Series with A and B | failed A → failed B → recovered B | Degraded; A remains |
| Series with A and B | failed A → failed B → recovered B → recovered A | Healthy |

## Status transitions without a new attempt

| Transition | Persisted history | Expected |
|---|---|---|
| Scheduled/delayed → published/corrected | 404 only | Immediately degraded |
| Poll budget exhausted → unavailable | 404 only | Immediately degraded |
| Unavailable → delayed through a valid later calendar slot | 404 only | No outstanding failure; polling resets |
| Unavailable → delayed through a valid later calendar slot | failed → 404 | Still degraded by the genuine failure |
| Delayed → published after rescheduling | 404 only | Degraded again until ingestion recovers |
| Any status transition | failed → ingested | Healthy; old failures remain superseded |

Historical 404s are reinterpreted against current status, not frozen at attempt
time: publication/unavailability activates a gap, rescheduling makes it neutral.
A reschedule cannot erase an independent `failed` outcome. A later success
supersedes all earlier outcomes, including gaps that status changes reactivate.
No attempt snapshots or schema migration are needed for these semantics.

## Refresh and timestamp contract

Repository writes own the projection: recording an ingest outcome, updating a
release status, and discovery upserts that change status refresh series health.
This covers scheduler, discovery, backfill and explicit ingestion without a
scheduler-to-pipeline dependency or duplicated orchestration.

Only a meaningful ingest attempt advances `last_checked_at`. Only an actual
`ingested`/`unchanged` result with no outstanding series failure advances
`last_success_at` (preserving the existing aggregate-health meaning). Status-only
recalculation and neutral attempts preserve both timestamps, even when the
recalculation clears a gap. A newly materialised degraded row may have null
timestamps if prior observations were neutral. Calendar source timestamps remain
independent. Health evaluation never modifies observations, vintages or retries.

## Verification sequence

1. Add outcome/status tables and transition tests, including equal and reversed
   timestamps to prove run-ID ordering. Confirm failures on the original code.
2. Implement the meaningful-outcome projection and repository refresh hooks.
3. Run regressions, full backend suite, Ruff lint/format, frontend tests/lint,
   typecheck/build, API type freshness, Playwright and available Docker checks.
4. Inspect final diff, commit/push once local checks pass, check final-head CI,
   reply/resolve the three confirmed defects, and perform one Codex review cycle.
   Report new findings without another implementation cycle.
