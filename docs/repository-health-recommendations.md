# Repository health: recommendations (proposals only)

9 November 2026. Companion to [repository-health-review-2026-11-09.md](repository-health-review-2026-11-09.md). **Nothing here is
implemented or approved.** Each item names the finding it answers, what would change, the risk, and the decision needed. The
only code change made by the review is the `backup` fix (RH-09).

Order is by value for the effort. None expands automatic acquisition, changes a permission, or touches inference.

## R1. A pre-migration backup that cannot be skipped (RH-10, RH-09)

*Problem.* Any normal start after `git pull` migrates immediately; the operator has no chance to back up first, and an
earlier migration (014) was applied this way with no pre-migration backup.

*Option A (smallest).* When `migrate()` is about to apply a pending migration to a database that already holds data, write a
verified bundle first (`create_bundle` already supports older schemas) to `data/backups/pre-migrate-<from>-to-<to>-<UTC>`,
and refuse to migrate if that fails. New and empty databases are unaffected.
*Option B.* `serve` refuses to start when a migration is pending, printing "run `nzstats backup --bundle …` then
`nzstats migrate`".
*Trade-off.* A is invisible but copies the raw tree on every upgrade (about 4 MB database, tens of MB of raw files today) and
changes startup time; B is explicit but breaks the container's "migrates itself on start" contract.
*Decision.* Choose A, B or neither. *Verification.* Tests on a schema-13 fixture: backup exists, is schema 13, live is 14;
a failing backup leaves the live schema at 13; concurrent starts take one backup.

## R2. Seeing corrections without expanding acquisition (RH-05, RH-08)

Three options, in rising scope. Only D1 and D2 add no automatic requests.

* **D1. Dry-run check (owner-run, one release).** `nzstats ingest --release-key K --check` fetches that release once, computes
  the statistics digest and prints `identical` or `differs (N series)` without writing. Purely a convenience over today's
  `ingest`, which already writes only when the digest differs. Low risk.
* **D2. Record free signals the check already fetches.** The month listing is read on every check. For releases that have a
  vintage, store an event when the listed headline, title or publication time differs from what is stored, and show
  "Stats NZ changed this release's listing on …: check for a correction" in Data health. No new request, no ingestion.
  Needs one additive table (migration 015) and an offline fixture of a changed listing.
* **D3. A bounded re-check of the newest release per series.** Opt-in, once, N days after publication, inside the existing
  request budget, ingesting through `_ingest` as a correction. This **does** add requests and automatic ingestion: it needs an
  explicit decision and a live acceptance of its own. Not recommended before D2 shows the signals are insufficient.

*Invariants for all three.* Earlier vintages, source hashes, raw artifacts and release dates are never edited; a correction is
a new bundle, as `_ingest` already does. *Evidence needed to justify D3:* a real correction missed by D2.

## R3. Freeze the publication date once data exists (RH-06)

*Change.* In `upsert_release`, when the release already has a vintage, keep `published_at` and write the observed value to the
D2 event table instead. *Why not a hot fix.* A release's first row legitimately moves from a scheduled slot to its actual time,
and a rescheduled release moves later; only the post-vintage case is wrong, and it needs a rule for a genuine date correction.
*Verification.* Tests for scheduled → published (moves), published with vintage → later or earlier listing (stays, event
recorded), and an unpublished release (never moves earlier, as the existing test requires). Requires a backup rehearsal if a
migration is added.

## R4. Repository posture (RH-01, RH-02, RH-03) — owner actions

1. Decide whether the repository should stay public. If it should be private, change visibility yourself; if public, keep the
   rule "every committed byte is published" and the new Netlify wording.
2. Enable secret scanning, push protection, Dependabot security updates and private vulnerability reporting (free on public
   repositories). Protect `main` (require the `ci` jobs and a pull request); the project currently relies on convention.
3. Add `SECURITY.md` (how to report) and a `LICENSE` for the code. With no licence the code is "all rights reserved" even
   though the data attribution (CC BY 4.0, Stats NZ) is stated.
4. Personal email and local path in the 11 October plan: remove only if you are prepared to rewrite history; otherwise accept.
5. Keep `permissions: read` as the Actions default (already set) and leave workflow secrets empty.

## R5. Rollback story for migrations 011-013 (RH-11)

Either record in `docs/` that 011-013 are rolled back only by restoring the pre-migration bundle (honest, no code), or write
additive-drop scripts for the ops, refresh and catch-up tables and rehearse them on a restored copy as Phase 4X did for 014.
R1 makes the first option safe, so do R1 first.

## R6. Make the dormant category text true (RH-12)

Replace the `INACTIVE_CATEGORIES` reasons with text that is correct for a fresh install (for example "no release stored yet"),
regenerate frontend fixtures, and run the overview tests. Cosmetic; do it with the next API change, not alone.

## R7. Live proof that is already scheduled by events, not by code

Open issue #31's carry-forward: the new-release path for ECT (October, due 12 November 10:45 NZDT), CPI, GDP and migration has
no live proof, and the chart refetch in a browser was not recorded. Phase 4Y has the runbook. It needs the owner's authorised
bounded on-open run with a fresh verified backup (now taken correctly, RH-09) and independent reconciliation. This review does
not authorise or run it.

## R8. Issue hygiene

* Close #31 with the carry-forward as a new issue (R7), once the owner accepts the Phase 4R record.
* Resolve #9 by confirming whether Netlify replaces Pages; record that decision in the Netlify design document, which
  currently does not say why.
* Open one tracking issue for R1 and one for R2/R3, so the corrections gap has an owner and a decision date.

## Explicitly not recommended

* Automatic re-download of every release on every check (violates the request budget and the 10 second spacing intent).
* Rewriting historical vintages, hashes or release dates to repair drift; always add, never edit.
* Loosening any validation threshold to accept a corrected file without evidence from the real file.
* Using the Treasury listing 403 as a reason to automate around bot protection.
