"""Phase 4W: preflight and explicit execution of an operator-run inference policy.

This is the only module besides `pilot` that can make a paid request, and it does so only from `execute_policy`, which needs
a policy file, a confirmation code printed by a dry run, a real terminal and a typed answer. It reuses the existing machinery
instead of adding another authorisation framework: `pilot.freeze` and `pilot.execute` (frozen request and body hashes, hosted
consent, live key/price/ZDR checks, a verified backup, one reservation, no retries) run unchanged, with an
`InternalDraftApproval` that this module builds from verified facts. Nothing in the policy file is read as an attestation.

Nothing here prints source text, a request body, model output or a key. A dry run is read-only and offline.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import logging
import re
import secrets
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import httpx

from nzstats.clock import utc_now
from nzstats.research import pilot
from nzstats.research import policy as pol
from nzstats.research.contract import build_request
from nzstats.research.openrouter import (
    Experiment,
    OpenRouterProvider,
    input_token_bound,
    register_policy_experiment,
)
from nzstats.research.policy import (
    Capacity,
    Check,
    InferencePolicy,
    PolicyRefused,
    SourceAssessment,
)
from nzstats.research.prompt import input_sha256
from nzstats.research.registry import Institution
from nzstats.research.summarise import SummariseResult
from nzstats.research.summary_store import PilotScope

log = logging.getLogger(__name__)

FREEZE_FORMAT = 4  # a policy freeze: format 2 and 3 freezes belong to the Phase 4N and 4S plans and cannot run here
AUDIT_TABLE = "research_policy_event"
NO_REQUEST_OUTCOMES = frozenset(
    {"attempt_consumed", "exists", "budget_exhausted", "input_too_long", "purged"}
)
PROMPT_TIMEOUT = timedelta(
    minutes=10
)  # the confirmation is for the request shown, not for whenever it is typed


def experiment_for(policy: InferencePolicy, sha: str) -> Experiment:
    """The experiment a policy spends in: its own caps, never wider than the code ceilings."""
    scope = PilotScope(
        pol.scope_name(sha), max_attempts=policy.max_calls, max_usd=policy.aggregate_usd
    )
    return Experiment(
        scope,
        policy.prompt_version,
        policy.route.reasoning_effort,
        policy.route.max_output_tokens,
        pol.TIMEOUT_SECONDS,
    )


def plan_for(policy: InferencePolicy, sha: str, version_id: int) -> pilot.PilotPlan:
    """A one-version plan: the version must carry no attempt, and only an internal-draft authorisation is accepted."""
    return pilot.PilotPlan(
        experiment_for(policy, sha),
        MappingProxyType({version_id: policy.institution}),
        FREEZE_FORMAT,
        0,
        frozenset({"internal_draft"}),
        policy.verifier_version,
    )


@dataclass(frozen=True)
class Preflight:
    policy: InferencePolicy
    sha: str
    version_id: int
    source: SourceAssessment
    capacity: Capacity
    window: Check
    request_sha256: str
    worst_case_usd: float
    audit_ready: bool
    refusal_codes: tuple[str, ...]
    confirm_code: str | None

    @property
    def eligible(self) -> bool:
        return not self.refusal_codes

    @property
    def ordinals(self) -> tuple[int, ...]:
        return self.source.ordinals

    @property
    def page_range(self) -> tuple[int | None, int | None]:
        return self.source.page_range

    @property
    def content_sha256(self) -> str:
        return self.source.content_sha256

    @property
    def prompt_version(self) -> str:
        return self.policy.prompt_version

    @property
    def verifier_version(self) -> str:
        return self.policy.verifier_version


def _confirm_code(sha: str, version_id: int, source: SourceAssessment, request_sha: str) -> str:
    scope = ",".join(map(str, source.ordinals))
    parts = [
        sha,
        str(version_id),
        source.content_sha256,
        source.sections_sha256,
        scope,
        request_sha,
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]


def preflight(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    policy: InferencePolicy,
    sha: str,
    version_id: int,
    data_dir: Path,
    *,
    now: datetime,
    ordinals: tuple[int, ...] | None = None,
) -> Preflight:
    """Everything a dry run reports, computed offline and read-only. Builds the request in memory; sends nothing."""
    window = pol.window_check(policy, now)
    source = pol.assess_source(
        conn, dict(registry), policy, sha, version_id, data_dir, ordinals=ordinals
    )
    request_sha, worst, fits = "", 0.0, True
    inst = registry.get(policy.institution)
    if (
        source.ordinals
        and inst is not None
        and not any(c.code == "version_not_found" for c in source.failures)
    ):
        experiment = experiment_for(policy, sha)
        register_policy_experiment(experiment)
        settings = pilot._settings("offline-preflight-no-transmission", experiment)
        sections = pol.load_sections(conn, version_id)
        with httpx.Client(
            trust_env=False
        ) as client:  # never used to send: the provider object only prices and hashes
            provider = OpenRouterProvider(settings, client)
            request = build_request(
                version_id,
                {n: sections[n] for n in source.ordinals},
                prompt_version=experiment.prompt_version,
                limits=settings.limits,
                published_on=source.published_on,
                institution=policy.institution,
                author=inst.name,
            )
            fits = not request.truncated and provider.input_fits(request)
            request_sha = input_sha256(
                request, provider=provider.name, model=pilot.MODEL, parameters=provider.parameters()
            )
            worst = settings.pricing.cost(
                input_token_bound(request), settings.limits.max_output_tokens
            )
    audit_ready = pol.audit_ready(conn)
    capacity = (
        pol.capacity_checks(conn, policy, sha, worst)
        if audit_ready
        else _capacity_without_audit(conn, policy, worst)
    )
    codes: list[str] = []
    codes += [] if window.ok else [window.code]
    codes += [c.code for c in source.failures if not c.ok]
    codes += [c.code for c in capacity.failures]
    codes += [] if fits else ["input_too_long"]
    codes += [] if audit_ready else ["database_not_migrated"]
    unique = tuple(dict.fromkeys(codes))
    code = (
        None if unique or not request_sha else _confirm_code(sha, version_id, source, request_sha)
    )
    return Preflight(
        policy,
        sha,
        version_id,
        source,
        capacity,
        window,
        request_sha,
        worst,
        audit_ready,
        unique,
        code,
    )


def _capacity_without_audit(
    conn: sqlite3.Connection, policy: InferencePolicy, worst: float
) -> Capacity:
    """Read-only fallback for a database that predates migration 014: the ledger alone, and the audit gap is its own refusal."""
    attempts = int(
        conn.execute(
            "SELECT COUNT(*) FROM research_llm_reservation WHERE provider='openrouter'"
        ).fetchone()[0]
    )
    spent = pol.lifetime_spent(conn)
    checks = (
        Check("per_call_cap_exceeded", worst <= policy.per_call_usd + 1e-9),
        Check("lifetime_attempts_exhausted", attempts < pol.LIFETIME_ATTEMPTS),
        Check("lifetime_budget_exhausted", spent + worst <= pol.LIFETIME_USD + 1e-9),
    )
    return Capacity(checks, 0, 0.0, attempts, spent)


def render_preflight(pf: Preflight) -> str:
    """The dry-run report: identities, scope, versions, route, hashes, cost, capacity and every check. No text of any kind."""
    p, s, c = pf.policy, pf.source, pf.capacity
    first, last = s.page_range
    pages = f"pages {first}-{last}" if first is not None else "pages unknown"
    lines = [
        "Policy dry run. Read-only and offline: nothing was requested, reserved or changed.",
        f"Policy:        {p.policy_id}  (hash {pf.sha[:8]}, issued by {_clean(p.issued_by)}, valid to {p.expires_at.date()})",
        f"Document:      {_clean(s.title) or 'unknown'}  (version id {pf.version_id}, version no {s.version_no},"
        f" published {s.published_on or 'unknown'})",
        f"Source:        {p.institution} / {p.series}, content {s.content_sha256[:12] or 'unknown'}",
        f"Sections:      ordinals {list(s.ordinals)}  ({pages}); excluded by rights tripwire: {list(s.excluded)}",
        f"Prompt:        {p.prompt_version}  (hash {p.prompt_sha256[:12]})",
        f"Verifier:      {p.verifier_version}  (hash {p.verifier_sha256[:12]})",
        f"Route:         {p.route.model} via {p.route.provider_id}, reasoning {p.route.reasoning_effort},"
        f" at most {p.route.max_output_tokens} output tokens",
        "Privacy:       zero data retention, data collection denied, no fallbacks, parameters required",
        f"Request hash:  {pf.request_sha256 or 'not built'}",
        f"Worst case:    US${pf.worst_case_usd:.4f} for this call (per-call cap US${p.per_call_usd:.2f})",
        f"Policy:        {c.calls_used} of {p.max_calls} calls used, US${c.spent_usd:.4f} of US${p.aggregate_usd:.2f}",
        f"Lifetime:      {c.lifetime_attempts_used} of {pol.LIFETIME_ATTEMPTS} attempts used,"
        f" US${c.lifetime_spent_usd:.10f} of US${pol.LIFETIME_USD:.2f}"
        f" (US${pol.LIFETIME_USD - c.lifetime_spent_usd:.10f} left)",
        "Live checks:   key limit and usage, model price and ZDR route are re-checked at execution only",
    ]
    if pf.eligible:
        lines += ["Status:        ELIGIBLE. No source rights are inferred from the policy file.",
                  f"Confirmation code: {pf.confirm_code}"]  # fmt: skip
    else:
        lines += ["Status:        REFUSED", *(f"  - {code}" for code in pf.refusal_codes)]
    return "\n".join(lines)


# --- execution ------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RunOutcome:
    outcome: str
    summary_id: int | None
    cost_usd: float
    errors: int
    warnings: int
    run_dir: Path


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _clean(text: object) -> str:
    """Document titles and names are metadata from outside: no terminal control characters reach the report or prompt."""
    return _CONTROL.sub("", str(text))


def _prompt_text(pf: Preflight) -> str:
    first, last = pf.page_range
    p = pf.policy
    return (
        f"\nYou are about to send ONE request: {_clean(pf.source.title)}, sections {list(pf.ordinals)}"
        f" (pages {first}-{last}), to {p.route.model} via {p.route.provider_id}, zero data retention.\n"
        f"Worst case US${pf.worst_case_usd:.4f}; there is no automatic retry, and a failed or unusable reply uses the attempt.\n"
        "Typing the code confirms that you read the dry run and the document's own copyright and licence notices,"
        " and that the listed sections hold no third-party material.\n"
        f"Retype the confirmation code ({pf.confirm_code}) to proceed, or anything else to stop: "
    )


def _refuse(
    conn: sqlite3.Connection,
    policy: InferencePolicy,
    sha: str,
    codes: tuple[str, ...],
    *,
    version_id: int,
    operator: str,
    now: datetime,
) -> None:
    """Log a refusal (it consumes nothing) and raise it. The log never blocks the refusal itself."""
    try:
        if pol.audit_ready(conn):
            known = conn.execute(
                "SELECT 1 FROM research_document_version WHERE id=?", (version_id,)
            ).fetchone()
            pol.record_event(
                conn, "refused", policy, sha, operator=operator, now=now, version_id=version_id if known else None,
                refusal_code=codes[0], detail=",".join(codes)[:200],
            )  # fmt: skip
    except sqlite3.Error:
        log.exception(
            "could not record the policy refusal %s", codes[0]
        )  # the refusal itself still stands
    raise PolicyRefused(codes[0])


def execute_policy(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    data_dir: Path,
    policy_path: Path,
    version_id: int,
    *,
    confirm: str,
    interactive: bool,
    ask: Callable[[str], str],
    api_key: str,
    ordinals: tuple[int, ...] | None = None,
    backup_check: Callable[
        [sqlite3.Connection, Path, Path, datetime], None
    ] = pilot.verified_backup,
    client: httpx.Client | None = None,
    now_fn: Callable[[], datetime] = utc_now,
    operator: str | None = None,
) -> RunOutcome:
    """One explicit, interactive, confirmed paid request for one document version, or a refusal that reserves nothing."""
    operator = operator or getpass.getuser()
    if not pol.audit_ready(conn):
        raise PolicyRefused("database_not_migrated")
    policy, sha = pol.load_policy(policy_path, data_dir)

    def refuse(*codes: str) -> None:
        _refuse(conn, policy, sha, codes, version_id=version_id, operator=operator, now=now_fn())

    if not interactive:
        refuse("not_interactive")
    asked_at = now_fn()
    pf = preflight(
        conn, registry, policy, sha, version_id, data_dir, now=asked_at, ordinals=ordinals
    )
    if not pf.eligible:
        refuse(*pf.refusal_codes)
    assert pf.confirm_code is not None
    if not hmac.compare_digest(confirm.strip().lower().encode(), pf.confirm_code.encode()):
        refuse("confirmation_mismatch")
    if not api_key or not api_key.strip():
        refuse("api_key_missing")
    answer = ask(_prompt_text(pf))
    if not hmac.compare_digest(answer.strip().lower().encode(), pf.confirm_code.encode()):
        refuse("not_confirmed")
    # The prompt can sit open: revocation, expiry, a new attempt or a source change meanwhile must still stop the run.
    now = now_fn()
    if now - asked_at > PROMPT_TIMEOUT:
        refuse("confirmation_expired")
    again = preflight(conn, registry, policy, sha, version_id, data_dir, now=now, ordinals=ordinals)
    if not again.eligible:
        refuse(*again.refusal_codes)
    if again.confirm_code != pf.confirm_code:
        refuse("request_changed")
    plan = plan_for(policy, sha, version_id)
    register_policy_experiment(plan.experiment)
    root = data_dir / "policy-runs"
    root.mkdir(mode=0o700, exist_ok=True)
    work = root / f"{sha[:12]}-v{version_id}-{now:%Y%m%dT%H%M%S}-{secrets.token_hex(3)}"
    try:
        manifest = pilot.freeze(
            conn, dict(registry), {version_id: pf.ordinals}, work / "freeze", plan
        )
        (doc,) = manifest["documents"]
        if doc["request_sha256"] != pf.request_sha256 or doc["content_sha256"] != pf.content_sha256:
            refuse("request_changed")
        if doc["worst_case_usd"] > policy.per_call_usd + 1e-9:
            refuse("per_call_cap_exceeded")
    except pilot.PilotRefused:
        refuse("freeze_refused")
    approval = _approval(policy, sha, plan, pf, doc, work / "freeze", now)
    error: BaseException | None = None
    results: list = []
    try:
        results = pilot.execute(
            conn, dict(registry), data_dir, work / "freeze", approval, work / "run", api_key,
            backup_check=backup_check, client=client, now_fn=now_fn, plan=plan,
        )  # fmt: skip
    except (
        BaseException
    ) as exc:  # recorded below, then re-raised: an interrupted call must still be audited
        error = exc
    outcome = _audit_after(
        conn, policy, sha, pf, operator, now_fn(), error, results[0] if results else None
    )
    if error is not None:
        raise error
    if outcome is None:  # another process consumed the version first: this one made no request
        raise PolicyRefused("attempt_consumed")
    return RunOutcome(outcome[0], outcome[1], outcome[2], outcome[3], outcome[4], work / "run")


def _approval(
    policy: InferencePolicy,
    sha: str,
    plan: pilot.PilotPlan,
    pf: Preflight,
    doc: dict,
    freeze_dir: Path,
    now: datetime,
) -> pilot.InternalDraftApproval:
    """Built here from verified facts, never read from a file. Its wording says where each fact was actually checked."""
    rights = tuple(
        pilot.SectionRight(
            ordinal=n,
            rights_basis=(
                f"Registry licence terms pinned by policy {policy.policy_id} ({sha[:8]}); manual-import provenance record"
                " present; operator confirmed at the terminal"
            ),
            third_party_rights=(
                "Sections carrying an explicit third-party notice are excluded by a tripwire; operator confirmed having"
                " read the document's own notices"
            ),
            attribution="The Treasury (Crown copyright); AI interpretation labelled an unreviewed internal draft",
        )
        for n in pf.ordinals
    )
    return pilot.InternalDraftApproval(
        state="authorised",
        purpose="internal_draft",
        experiment=plan.experiment_id,
        experiment_spend_limit_usd=plan.experiment.scope.max_usd,
        approved_by=policy.issued_by,
        approved_at=now,
        expires_at=now + timedelta(hours=1),
        frozen_sha256=pilot.file_sha256(freeze_dir / "freeze.json"),
        model=pilot.MODEL,
        provider_id=pilot.ROUTE,
        privacy=pilot.PrivacyTerms(
            zdr=True, data_collection="deny", allow_fallbacks=False, require_parameters=True
        ),
        provider_review=f"Route pinned by policy {policy.policy_id}; catalogue identity, price and ZDR endpoint re-checked live at execution",
        account_controls_evidence=(
            "Not asserted by the policy file: the dedicated key's US$5 lifetime limit, zero BYOK usage and usage equal to the"
            " ledger are checked live against OpenRouter at execution"
        ),
        dedicated_key_confirmed=True,
        documents=(
            pilot.DocumentAuthorisation(
                version_id=pf.version_id,
                request_sha256=doc["request_sha256"],
                body_sha256=doc["body_sha256"],
                sections=rights,
            ),
        ),
    )


def _audit_after(
    conn: sqlite3.Connection,
    policy: InferencePolicy,
    sha: str,
    pf: Preflight,
    operator: str,
    now: datetime,
    error: BaseException | None,
    result: SummariseResult | None = None,
) -> tuple[str, int | None, float, int, int] | None:
    """Append what happened. A reservation made by THIS run is an `executed` row whatever the outcome; otherwise a refusal.

    The run is identified by its own run id (from the pipeline result), never by "the latest reservation for the version":
    when another process wins the version, this one made no request and must not claim the winner's row.
    """

    def refused(code: str, detail: str = "") -> None:
        pol.record_event(
            conn, "refused", policy, sha, operator=operator, now=now, refusal_code=code, detail=detail[:200],
            version_id=pf.version_id,
        )  # fmt: skip

    item = result.items[0] if result is not None and result.items else None
    # "exists" and "attempt_consumed" both mean another process used this version first: this one made no request.
    if result is not None and (item is None or item.outcome in NO_REQUEST_OUTCOMES):
        refused(
            "attempt_consumed"
            if item and item.outcome in ("exists", "attempt_consumed")
            else (item.outcome if item else "no_item")
        )
        return None
    scope = pol.scope_name(sha)
    res = conn.execute(
        "SELECT x.id, x.run_id, x.state, x.reserved_usd, x.actual_usd FROM research_llm_reservation x"
        " JOIN research_llm_run r ON r.id = x.run_id WHERE x.provider='openrouter' AND x.version_id=?"
        " AND (? IS NULL OR x.run_id = ?) AND json_extract(r.limits, '$.experiment') = ? ORDER BY x.id DESC LIMIT 1",
        (
            pf.version_id,
            result.run_id if result else None,
            result.run_id if result else None,
            scope,
        ),
    ).fetchone()
    if res is None:  # no reservation of ours: nothing was requested
        code = "pilot_refused" if isinstance(error, pilot.PilotRefused) else "execution_failed"
        refused(code, str(error) if isinstance(error, pilot.PilotRefused) else "")
        return None
    summary = conn.execute(
        "SELECT id, status, verification FROM research_summary WHERE run_id=? AND version_id=? ORDER BY id DESC LIMIT 1",
        (res["run_id"], pf.version_id),
    ).fetchone()
    usage = (
        conn.execute(
            "SELECT input_tokens, output_tokens FROM research_llm_usage WHERE summary_id=? ORDER BY id LIMIT 1",
            (summary["id"],),
        ).fetchone()
        if summary
        else None
    )
    cost = float(res["actual_usd"] if res["state"] == "settled" else res["reserved_usd"])
    errors = warnings = 0
    if summary and summary["verification"]:
        report = json.loads(summary["verification"])
        errors, warnings = len(report.get("errors", [])), len(report.get("warnings", []))
    outcome = summary["status"] if summary else "interrupted"
    try:
        pol.record_event(
            conn, "executed", policy, sha, operator=operator, now=now, content_sha256=pf.content_sha256,
            request_sha256=pf.request_sha256, model=pilot.MODEL, provider_id=pilot.ROUTE,
            prompt_version=policy.prompt_version, prompt_sha256=policy.prompt_sha256,
            verifier_version=policy.verifier_version, verifier_sha256=policy.verifier_sha256,
            attempt_no=pol.policy_usage(conn, sha)[0], outcome=outcome,
            summary_id=summary["id"] if summary else None, run_id=res["run_id"],
            reserved_usd=float(res["reserved_usd"]), cost_usd=cost,
            input_tokens=usage["input_tokens"] if usage else None,
            output_tokens=usage["output_tokens"] if usage else None,
            errors=errors, warnings=warnings, version_id=pf.version_id,
        )  # fmt: skip
    except sqlite3.IntegrityError:
        # An executed row for this content already exists. The ledger (authoritative) holds this run's cost; say so.
        log.exception("audit conflict for run %s", res["run_id"])
        refused(
            "audit_conflict",
            "an executed row already exists for this content; see the reservation ledger",
        )
    return outcome, (summary["id"] if summary else None), cost, errors, warnings
