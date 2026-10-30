# PR #27 review remediation

Scope: Phase 4F native monitoring into `main`, on the existing
`feat/phase-4f-native-monitoring` branch. No deployment, scheduler activation,
production migration, live fetch, or production-data operation is part of this work.

## Actionable findings ledger

The initial fresh sweep found two actionable findings, both P2, reviewed at
`bb065243e4763820e92164ed55850eb0fa06061e`. Review submissions, inline comments,
thread resolution state, conversation comments and check runs were inspected.
REST collections were fetched with pagination. Final head-specific review and
verification evidence is recorded in the PR conversation, including any subsequent
findings; the initial review is not validation of the remediation commit.

| ID / location | Root cause | Fix | Regression coverage | Resolution |
| --- | --- | --- | --- | --- |
| [4420622906](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/27#discussion_r4420622906), `backend/src/nzstats/ops/health.py` | Successful notifications were pooled across notifier names, masking another channel's failures. | Evaluate recent sent/failed counts per recorded notifier; report failing if any channel has failures and no success in the window. Preserve the response schema, aggregate counters, historical timestamps and separation from overall application health. | 16 new cases in `tests/ops/test_health.py`: all-success, both mixed directions, repeated failures, all-failure, empty/stale history, rate-limited-only, log-only/file-only success and failure, same-channel recovery, and window isolation. Six cases failed before the fix. | Fixed locally; thread reply/resolution and fresh GitHub review follow the verified push. |
| [4420622909](https://github.com/kcha193/NZ-Stats-Intelligence-Dashboard/pull/27#discussion_r4420622909), `frontend/src/pages/Health.tsx` | The legacy health query's error/loading boundary suppressed the Operations panel. | Place the page heading and live Operations success/error/loading states outside the legacy boundary. Keep snapshot mode free of operational queries and content. | Five new cases in `Health.test.tsx`: critical database recovery with legacy HTTP 500 or pending request; both queries failing; ops pending with legacy success or pending. Existing successful-health and ops-failure tests remain. All five new cases failed before the fix. | Fixed locally; thread reply/resolution and fresh GitHub review follow the verified push. |

Channel choice belongs to each `alert-check` invocation (`--channels` or environment),
and is not persisted as configuration. The status reader therefore uses recorded
notifier names, rather than assuming both default channels were selected. Old
attempts and rate-limited entries alone do not prove recent delivery:
`none_recorded` is used when there is no sent/failed evidence in the window.
Historical attempt/success timestamps remain available. Success on the same
channel within the window retains the existing recovery semantics.
The Operations panel describes this as no attempts within the window, rather
than claiming nothing was ever sent; one additional failing-first UI regression
covers historical successful delivery.

## Verification and limitations

All tests use an isolated checkout, migrated temporary databases and fixture-only
browser data. Production `data/`, `.env`, scheduler state, backup artifacts and
databases are outside the test workspace. Monitoring remains read-only and offline;
the operations tests reject external DNS and network connections.

The PR conversation records actual final suite counts, Ruff, API type parity,
frontend typecheck/lint/build, dependency audit, browser results and the pushed SHA.
Local results: Python 3.12 full pytest **3,055 passed**; operations subset **162
passed**; frontend **493 passed**, including **15 Health page tests**. Ruff lint and
format, API type parity, typecheck, lint, build, dependency audit (zero reported
vulnerabilities) and staged Gitleaks pass. Browser checks: **150 live**, **312 static
plus 3 expected skips**, **18 synthetic research plus 3 expected skips**. After the
final delivery-history copy change, the rebuilt Health page passes all **3**
desktop/tablet/mobile browser checks; full Vitest/typecheck/lint also pass again.
Existing Fast Refresh, bundle-size and Starlette/httpx deprecation warnings are
reported separately from failures.

Hosted CI on the initial head cannot execute backend/frontend/static-site jobs:
GitHub's check annotation says recent account payments failed or the spending limit
must be increased (run `41006435392`). Docker is skipped as a dependent job;
the local Docker daemon is unavailable. These are unavailable checks, not passes.
The branch-protection API returns HTTP 403 (GitHub requires Pro or a public
repository), so required-check configuration cannot be independently inspected.
The final sweep must refresh these states for the pushed head.
