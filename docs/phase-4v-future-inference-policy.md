# Future operator-controlled inference: policy proposal

> **Implemented in Phase 4W** ([phase-4w-policy-workflow.md](phase-4w-policy-workflow.md)), with differences: no signature (the file is local limits only, never evidence), the confirmation code binds the exact request, one audit table instead of two, and the ceiling is 8 attempts for `policy-*` scopes only. Nothing is enabled.

7 November 2026. **A proposal for review. Nothing here is implemented, enabled or authorised.** Phase 4V changes no limit, ledger row, permission or provider code.
The lifetime limit of 4 attempts (`LIFETIME_ATTEMPTS`) stays exactly as it is, and the US$0.6267107880 already spent (remaining US$4.3732892120 of the US$5.00 cap) is history that no
future policy may reset, reuse or edit. This describes what a separately reviewed change would have to build before any further paid request is allowed.

## Principles

1. **Permission is explicit and per source.** An institution is eligible only when its registry entry already allows LLM processing for internal use. A policy narrows that permission; it never widens it.
2. **One call per new document version.** The unit of permission is a document version (its content hash), not a series or a date range. A new version is a new decision.
3. **No unattended paid inference.** No scheduler, on-open refresh, API route or hook may start a request. Each call is an explicit operator command.
4. **No automatic retries**, including after a transport error or an unusable response. A failed call is spent.
5. **Everything is on the record.** Authorisation, reservation, outcome and cost are append-only. Nothing is deleted or rewritten to make a later run possible.
6. **Internal only.** Output reaches the dashboard solely through the existing internal-draft gate, labelled as an unreviewed draft. It never reaches the public, private or snapshot paths.

## The policy

A signed JSON file in the ignored `data/` directory, mode 0600, never committed. Its canonical hash is its identity.

| Field | Meaning |
|---|---|
| `policy_id`, `issued_by`, `issued_on` | who authorised it and when |
| `institution` and `series` | exactly one source and one series (for example Treasury fortnightly update) |
| `document_scope` | `one_call_per_document_version`; no other value is valid |
| `route` | model, provider, zero data retention, data collection denied, no fallbacks, reasoning effort, output-token cap: the reviewed route, matched exactly |
| `prompt_version`, `verifier_version` | pinned labels, each with its recorded hash (for example `outlook-v6`, `verify-5`) |
| `per_call_usd` | hard cap on the worst-case reservation of one call |
| `aggregate_usd` | cap on everything this policy may ever spend |
| `not_before`, `expires_on` | a window of at most 30 days, checked at call time |
| `max_calls` | an upper bound that can only be lower than the number of document versions in scope |

## The command

`nzstats research run-policy POLICY --version N --confirm HASH8`, interactive only. It refuses unless every check passes, in this order, each with a stable reason code and no document text in the message:

1. the policy file parses, its hash matches `HASH8` typed by the operator, and it has not expired;
2. the institution's registry permission still allows processing; the document is current, held, quotable and not purged;
3. no row exists for (policy hash, document content hash), whatever its outcome;
4. the request, body hash and prompt hash equal what a dry run printed;
5. worst-case cost is within `per_call_usd`, and spend so far plus that cost is within `aggregate_usd` and within the global remaining cap;
6. the key reading for the day is present and recent.

Only then does it write the reservation and make one request with zero retries.

## The ledger

A new append-only table (`BEFORE UPDATE` and `BEFORE DELETE` abort, like `research_llm_usage`):

`policy_authorisation` (policy hash, operator, issued and expiry dates, caps) and `policy_call` (policy hash, document version and content hash, request hash, reservation, outcome, cost, response id, verifier version, counts of errors and warnings).

It stores no prompt text, document text or model output. The existing `research_llm_*` tables stay as they are and are counted into cumulative spend, so the historical US$0.6267107880 and 4 attempts are carried forward, never zeroed. Raising or replacing the lifetime attempt limit is a code change reviewed on its own, not an effect of a policy file.

## Audit

A read-only `policy-audit` command lists policies, calls, spend against each cap, expiries and refusals. A refusal is itself logged (policy, version, reason code, time) so a missed or blocked call is visible.

## What a reviewer should require before approving this

- Tests that no scheduler, refresh, API or CLI route other than `run-policy` imports the provider, and that `run-policy` refuses without a terminal.
- Tests for each refusal reason, a second call on the same document version, an expired policy, a cap exactly reached, and a failed call that still consumes the version.
- A test that the append-only tables reject update and delete, and that cumulative spend includes the legacy rows.
- A dry run that prints the request hash, worst-case cost and every check result without contacting the provider.
- A decision by the owner on: the aggregate cap, whether RBNZ is in scope, who may sign, and whether the lifetime attempt limit is replaced or kept alongside the policy limits.

## Not proposed

Automatic runs on new releases; retries; widening any source permission; showing output outside the internal draft gate; a human-gold or per-claim approval requirement (Phase 4T made those optional for internal drafts and this proposal keeps it that way).
