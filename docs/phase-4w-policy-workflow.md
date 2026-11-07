# Phase 4W: repeatable internal AI economic intelligence

7 November 2026, Pacific/Auckland. Baseline main `b1db034` (PR #50 merged). Codes, counts and structure only: no Treasury text, model output or key.
**No OpenRouter request was made in this phase.** Every test uses synthetic documents and a mocked provider. No policy file exists on the owner's machine, no registry permission changed, no crawl, deployment or Netlify action.

## What it is

One reusable, operator-run workflow for "one AI commentary request per newly imported Treasury Fortnightly Economic Update", replacing a new engineering phase per report:

```
manual import -> policy file (limits only) -> run-policy --dry-run (offline, read-only)
  -> run-policy --confirm CODE (real terminal, retype the code) -> pilot.freeze + pilot.execute (existing machinery)
  -> one OpenRouter request -> verify-5 -> stored + audited -> internal draft (Phase 4T gate)
```

| Command | What it does |
|---|---|
| `research policy-init FILE --issued-by NAME --policy-id ID` | Writes a private (0600) policy under `data/` with the pins filled in. Authorises nothing. |
| `research run-policy POLICY --version N [--sections 1,2] --dry-run` | Offline preflight. Opens the database `mode=ro`. Prints identity, scope, pins, route, request hash, worst-case cost, capacity, every refusal code and a confirmation code. No source text, request body, output or key. |
| `research run-policy POLICY --version N --confirm HASH8` | Needs a real terminal on stdin and stdout, the code from a dry run, `NZSTATS_LLM_API_KEY`, and the code retyped at a prompt. Then one request, no retry. |
| `research policy-audit` | Read-only: lifetime ledger, every audit event, and any policy reservation with no audit row. |
| `research policy-revoke POLICY --reason TEXT` | Appends a permanent revocation. |

## Limits (code ceilings; a policy file can only be stricter)

| | |
|---|---|
| Institution, series | Treasury, `FEU` only. **RBNZ is excluded** (its source-access and hosted-processing rights need their own review). |
| Scope | one call per document version; a version with any recorded attempt, or whose **content hash** has one, is ineligible |
| Per call | at most US$0.50 worst case (the 29 October FEU prices at **US$0.4247**, so little headroom) |
| Aggregate | at most US$2.00 per policy |
| Calls | at most 4 per policy |
| Window | at most 30 days, checked at call time |
| Global | lifetime ceiling **8 attempts** (was 4) and **US$5** (unchanged) |

**Ledger carried forward, not reset:** 4 of 8 attempts used, US$0.6267107880 of US$5.00 spent, **US$4.3732892120 remaining**. Summary 4 is still `failed_verification`, `unreviewed`, `outlook-v5`, `verify-4`. The live database hash was identical before and after every command run in this phase.

### The ceiling change, and a defect it would have caused

`LIFETIME_ATTEMPTS` 4 to 8 alone would have **reopened a spent experiment**: the Phase 4N scope used 1 of its 2 attempts, so a higher global ceiling lets it spend a second on RBNZ version 2. A test built on the real ledger shape caught this. The fix is at the ledger: every scope that existed before Phase 4W keeps the original ceiling of 4 (`LEGACY_LIFETIME_ATTEMPTS`) for ever; only a scope named `policy-<hash>` sees 8. Raising the number authorises nothing by itself, and a test pins that for every legacy scope and version.

## Gates, in order (each a stable code, none containing text)

1. Policy file: private regular file inside `data/` (no symlink, no group or world access), strict schema, route and privacy terms exactly the reviewed ones, prompt and verifier hashes equal to the code's, licence hash equal to the registry's.
2. Window, revocation, per-call cap, policy calls and dollars (the larger of the reservation ledger and the audit), global attempts and dollars.
3. Source, read from the registry and the store and **never from the file**: institution and series; `holds(acquisition)` and full-text policy; `llm_processing = hosted`; current, unsuperseded, not purged; manual-import provenance record; raw file present with a matching hash; stored licence terms equal the pinned ones; sections carrying an explicit third-party notice are excluded, and an operator cannot name one back in.
4. Confirmation code = hash of policy, version, content, sections and request, so any change after the dry run is a mismatch.
5. Real terminal, retyped answer, then the existing pilot machinery: frozen body hash, hosted consent, live key limit and usage equal to the ledger, live model price and ZDR route, a **verified backup**, one reservation, no retry.

Every refusal is appended to the audit and consumes nothing. An interrupted call keeps its worst-case reservation and is audited as `interrupted`.

## Prompt and verifier

Policies pin `outlook-v6` and `verify-5` with their hashes (the verifier hash is the sha256 of `verify.py`, so any edit to the verifier needs a new policy). `EXPERIMENTS` still lists no v6 experiment; policy experiments live in a separate runtime registry. Summary 4 stays `outlook-v5` and `verify-4`; an offline `verify-5` replay is a new assessment shown only by `diagnose`. **Nothing here shows v6 is better; that needs a real, authorised run.** The JSON contract is unchanged.

## Dashboard (Economic Outlook)

Most of the requested page already existed (Phase 4T). Added: the header no longer says every AI summary is "approved by a person" (it now separates internal, automated-checks-only drafts from the separate publishing workflow); older reports are labelled **Historical**; the latest card shows which verifier and prompt checked it; missing commentary says an AI request runs only when an operator starts one and that opening the page never starts one. No commentary is labelled verified, human-reviewed or endorsed.

## Audit and integrity

Migration 014 `research_policy_event`: append-only (update and delete abort), no column for text, output or credentials, one `executed` row per content hash whatever the policy or version row. Rollback script included and wired into the full research rollback. `research_llm_*` rows are untouched. `policy-audit` flags a policy reservation with no audit row.

## Real dry run (scratch copy of the real database)

Version 3 (29 October FEU, 5 sections, pages 1 to 5), real registry, un-migrated copy:

```
Worst case:    US$0.4247 for this call (per-call cap US$0.50)
Lifetime:      4 of 8 attempts used, US$0.6267107880 of US$5.00 (US$4.3732892120 left)
Status:        REFUSED
  - llm_processing_denied      (the registry gives Treasury no hosted-LLM permission)
  - version_attempted          (version 3 already used its attempt in Phase 4S)
  - database_not_migrated      (migration 014 not applied yet)
```

Non-interactive `--confirm` prints `Refused: ... Nothing was requested or reserved.` and exits 2.

## Known limits (stated plainly)

- The terminal check stops automation and honest mistakes; it is **not a sandbox** (a pseudo-terminal defeats it). The policy file is trusted only as local limits.
- The third-party tripwire is a regex over explicit notices, not a legal review; the operator's typed confirmation is the assertion that the document's own notices were read.
- `verify-5` is checked on constructed sentences and one stored summary; `outlook-v6` has never met a real model. Expect failed checks to remain possible.
- Per-call headroom is thin (US$0.4247 of US$0.50).
- Codex review could not run (model refused on this ChatGPT account); the independent review was done by a Claude agent.
- GitHub Actions billing block is an environment problem, separate from the local results.

## Owner activation guide

Nothing runs until you do all of these. None is done by this PR.

1. **Decide** the aggregate cap (proposed US$2), whether RBNZ stays out (proposed: yes), who signs (`issued_by`), and that the lifetime ceiling is 8 total attempts.
2. **Review and merge** this PR, then run `nzstats migrate` (applies 014; take a backup first).
3. **Grant the source permission yourself**, with a documented review: set `llm_processing = "hosted"` and its note for Treasury in `config/research_sources.toml`. Until then every dry run refuses `llm_processing_denied`. Confirm the provider's terms and the Crown licence for hosted processing.
4. **Import the new report manually** (existing `research import`), then check it for item-specific copyright notices.
5. `nzstats research policy-init data/policy-nov.json --issued-by "Kevin Chang" --policy-id treasury-feu-nov`, read the file.
6. `nzstats research run-policy data/policy-nov.json --version N --dry-run`; read every line.
7. Set `NZSTATS_LLM_API_KEY` to the dedicated key (US$5 lifetime limit, usage equal to the ledger), then in a terminal: `... --confirm CODE`, and retype the code.
8. Open the Economic Outlook page: the result appears as an unreviewed internal draft with its checks.

## Test and review evidence

- Backend: full suite passes; ruff check and format clean. New: `test_policy.py`, `test_policy_run.py`, `test_policy_cli.py`, `test_policy_isolation.py`, `test_policy_plumbing.py`, migration 014 and rollback tests. Guards were mutation-checked (a broken gate fails a named test).
- Frontend: 557 unit tests, typecheck and build pass. Browser: research config 18 passed; static-isolation 315 passed (24 skipped by design). The main Playwright run had 6 tablet/mobile failures on pages this phase did not touch, after stalls of about 17 minutes; the same specs passed on rerun with two workers (114 of 114). Treated as an environment stall, not proof of a fix.
- **Codex review: not obtained.** Codex refuses its default model on this ChatGPT account.
- **Independent Claude review (adversarial, read-only): no way found to spend extra money or bypass the gates.** Two medium defects found and fixed with tests: (1) revocation, expiry or a new attempt while the prompt was open did not stop the run (now re-checked after the prompt, with a 10-minute limit); (2) two concurrent runs on one version could audit the winner's reservation under the loser and raise after a paid call (now audited by the run's own id, one `executed` row, the loser records `attempt_consumed`). Also fixed: registry-level policy ceilings, `--sections ""`, refusals for unknown versions, SIGHUP/SIGTERM audited as interruptions, `policy-revoke` on an unmigrated database, terminal control characters in titles. Not changed: `key_reading` still reports `8 - n` attempts left, which overstates what legacy scopes may use.
- Residual: a SIGKILL after reservation leaves a reservation with no audit row; the ledger still blocks reuse and `policy-audit` flags it. There is no reconcile command.

## Verdict: GO WITH CONDITIONS

Go for merging the code: nothing is enabled and no call is authorised. Conditions before the first paid request: the owner grants Treasury hosted-LLM permission in the registry after a documented review (every dry run refuses until then); runs `nzstats migrate`; accepts that `outlook-v6` and `verify-5` are untested on a real model and that the per-call headroom is thin (US$0.4247 of US$0.50); and runs the first policy in a real terminal. Not GO for unattended or automatic use, which is out of scope by design.
