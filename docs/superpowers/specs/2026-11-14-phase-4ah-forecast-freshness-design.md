# Phase 4AH design: forecast freshness (and the ANZ pilot's status)

14 November 2026, Pacific/Auckland. Baseline: main `5934060` (PR #60 merged).

## Intent

Phase 4AG recorded a staleness gap: when a newer bank report's table cell is refused (a footnote, say), the bank's older
figure for that horizon still appears as the bank's latest forecast and enters the consensus. A refused cell stores only
a code and a position, never an identity, so the existing "newer claim unusable" rule (which works by identity) cannot
catch it. This phase closes that gap without guessing what a refused cell was.

The ANZ pilot (workstreams B and C) stays **BLOCKED**: the registry and the vault record no ANZ right and no owner
decision (`institutions.anz` unchanged since 4AG; no decision note). Nothing is imported, fetched or processed.

## Goals

1. Track, per bank, the newer relevant document vintages: the latest published report and the latest report whose
   figures were accepted.
2. A bank's older figure is not shown as current, and is not used in the consensus or divergence, when the bank has a
   newer relevant report that was not fully read and that does not restate the same measure.
3. Rejected-cell evidence, immutable rows and historical revisions are kept unchanged.

## Non-goals and anti-goals

- No identity is inferred for a refused cell (no "the row label says CPI, so the cell was CPI").
- No new forecast framework, no schema migration, no change to extraction rules or tolerances.
- No permission change, no live ingestion, no model call, no frontend redesign.
- Failure would be: an older figure shown as current next to a newer unread report; or a historical revision lost.

## Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| A. Store an identity on each rejection (schema migration, new columns) | needs the identity of a cell that was refused because its identity is unclear; violates "never infer" | rejected |
| B. Record reader refusals in a new table (migration) so a refused PDF is visible | useful, but the same outcome is reachable read-only: a held report with nothing read is already visible as "held, no current extraction, no admitted summary" | not needed |
| **C. Document-level freshness, read-only (chosen)** | a newer report that was not fully read hides the bank's older figures for any measure that report (or a later one) does not restate; may hide a little more than the one refused cell, which is the fail-closed direction | chosen: no migration, no inference, small diff |

## Design

### Document states (new, `table_view.document_states`)

For every bank publication's current version that is a bank's live, unique report (not purged, current version, not
superseded, not a duplicate), has a publication date and is a quarterly *outlook* report. (Amended after review: the
first draft also required the display gate `_shown`; a held report that may not be shown, because its route was revoked
or its content policy or host no longer allows it, is now `not_read`, so it still stops older figures appearing current.)

| State | When |
|---|---|
| `read` | its figures were read: a current-interpreter extraction with at least one accepted own forecast and no blocking rejection, or an admitted draft summary (and no blocking table rejection) |
| `incomplete` | a current-interpreter extraction has a non-scenario rejection, or an own forecast cell printed without a value (dash), in either display mode |
| `incomplete_scenario` | the only rejections are `scenario_table`, `scenario_row` or `scenario_column` (they cannot hide a central figure) |
| `not_read` | none of the above: may not be shown, never extracted, extracted only by an older interpreter (even with an admitted summary), refused by the reader (stores nothing), nothing accepted, or its summary is not admitted (withdrawn, unnamed) |

Table refusals for geography or scope (`unsupported_geography`, `unsupported_scope`) are blocking, by decision: the
geography of a table is read from its caption and header text, and a caption such as "Australia and New Zealand" could
hold New Zealand figures in a refused table. Treating them as scenario-like would trust that text to say what the
refused cells were, which this phase does not do. The cost is that a report with a foreign table is `incomplete` (and its
`vintages` row not `current`); in practice real reports already carry unmapped rows that have the same effect.

Table figures count as read only in the owner's automatic mode (the same rule that decides whether they show).
Undated documents cannot be placed in time and are not states (they are already excluded from vintage analysis).

`BankView` gains `documents: list[DocumentState]` (default empty, so existing constructors keep working).

### The rule (`bank_analytics._prepare`, current views only)

For a figure `n` of bank B with identity I (bank, adjustment, comparison group) published on date d: if B has an
`incomplete`/`not_read` document dated D > d (`incomplete_scenario`: only when I is a scenario group), and no eligible
figure of B with identity I is dated D or later, then `n` is excluded with a fixed code:

- `newer_report_incomplete`: "This bank's newer report has table cells that could not be read, so its older figure is
  not shown as current."
- `newer_report_not_read`: "This bank has a newer report whose figures have not been read, so its older figure is not
  shown as current."

Applies to the forecast comparison ("each bank's latest forecast"), the consensus and the divergence. It does not apply
to revisions (history: every accepted vintage stays, and the UI does not label a vintage "current") or to evaluation
(a forecast published before the outcome is scored on its own date and horizon band). `bank_exclusions` gains
`current: bool = True`; the revisions endpoint passes `False`.

### Latest published versus latest accepted

`GET /internal/bank-intelligence/forecasts` gains an additive `vintages` list, one row per bank with a dated outlook
document: `latest_published_on`, `latest_accepted_on` (newest outlook figure the view accepted), `state` of the newest
document, and `current` (`latest_published_on == latest_accepted_on` and the newest document is `read`). Internal API,
not in the generated schema; the frontend already lists each exclusion with its fixed server reason (`BankLeftOut`),
so no frontend change is needed to show the effect.

## Cases and expected outcomes (the tests)

| Case | Expected |
|---|---|
| Newer valid forecast | newer figure current; older kept as earlier vintage and in revisions |
| Newer invalid forecast (cell refused, e.g. footnote) | older figure excluded `newer_report_incomplete` from comparison/consensus; kept in revisions |
| Ambiguous rejected cell (`ambiguous_columns`) | same as above; no identity inferred |
| Duplicate publication | duplicate is not a state; changes nothing |
| Corrected publication | superseded version ignored; corrected version decides (`read` or `not_read`) |
| Withdrawn publication (purged, or summary withdrawn) | purged: no longer a state; withdrawn summary with no table: `not_read` |
| Missing forecast (dash) | `incomplete`: older figure for that measure excluded |
| Multiple target horizons | restated horizon: newer figure current, older is an earlier vintage; unrestated horizon: older excluded |
| Scenario-only rejection | central figures unaffected |
| Undated or weekly newer document | not a state; nothing changes |

## Limits (stated, accepted)

- Over-hiding: a newer report with any blocking rejection hides every older figure that report does not restate, not
  only the refused cell's. This is deliberate (the refused cell's identity is unknown).
- Same-day documents: only strictly newer reports trigger the rule.
- A model summary that omits a measure is treated as read (pre-existing 4AE behaviour; bank model processing is not
  authorised).
- Table figures dropped by an unresolved reconciliation with a model claim do not mark the report incomplete (no bank
  claims exist while `llm_processing` is denied).
