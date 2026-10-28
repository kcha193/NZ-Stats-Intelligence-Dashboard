"""Pilot readiness (Phase 3D-A): the four permissions a real source needs, each judged on its own.

1. automated discovery and fetching, 2. extraction and local storage of the text (through the crawler, or through a
separately approved manual import, Phase 3E), 3. processing by a language model (local or hosted), 4. public display. Each gate reports what the registry records, the evidence behind it, and the
first thing that blocks it. The report reads the registry, the environment and (optionally) the database only: it
makes no request, changes no setting and never prints a credential. Granting a gate is always a human edit to
`config/research_sources.toml`, recorded in git.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field

from nzstats.research.api import ENABLE_ENV, public_research_enabled
from nzstats.research.providers import LlmSettings, is_hosted
from nzstats.research.public import public_summaries
from nzstats.research.registry import ContentPolicy, Institution, LlmProcessing, PublicDisplay


@dataclass(frozen=True)
class Gate:
    name: str  # fetch, store, llm, publish
    title: str
    granted: bool
    detail: str
    evidence: tuple[str, ...] = ()
    blocker: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineState:
    publications: int
    current_versions: int
    summaries: dict[str, int] = field(default_factory=dict)  # by status
    approved: int = 0
    public: int = 0


@dataclass(frozen=True)
class Readiness:
    institution: str
    name: str
    gates: tuple[Gate, ...]

    @property
    def first_blocker(self) -> str | None:
        return next((g.blocker for g in self.gates if g.blocker), None)


def _waiting(number: int) -> str:
    return f"waits on decision {number}"


def _fetch(inst: Institution) -> Gate:
    evidence = (
        f"review_status: {inst.review_status.value}",
        f"terms_evidence: {inst.terms_evidence}",
        f"robots_evidence: {inst.robots_evidence}",
        f"landing_evidence: {inst.landing_evidence}",
        f"approved: {inst.approved_by or '-'} on {inst.approved_on or '-'}",
    )
    warnings = tuple(
        f"discovery {d.mechanism.value} at {d.url or '-'} is not verified"
        for d in inst.discovery
        if not d.verified
    )
    granted = inst.automated_access_allowed
    blocker = None
    if not granted:
        reason = inst.refusal_reason() or "not approved"
        if inst.terms_evidence != "direct":
            reason += (
                f"; the terms have not been read directly (terms_evidence: {inst.terms_evidence})"
            )
        blocker = reason
    return Gate("fetch", "Automated discovery and fetching", granted, inst.review_status.value, evidence, blocker,
                warnings)  # fmt: skip


def _store(inst: Institution, fetch: Gate) -> Gate:
    """Granted through the crawler (decision 1 and `full_text`) or a separately approved manual import (3E)."""
    policy = inst.content_policy.value
    evidence = (
        f"content_policy: {policy}",
        f"licence: {inst.licence or '-'}",
        f"licence_url: {inst.licence_url or '-'}",
        f"manual_import: {inst.manual_import.value}",
        f"manual import approved: {inst.manual_import_approved_by or '-'} on"
        f" {inst.manual_import_approved_on or '-'}",
    )
    title = "Extraction and local storage"
    if inst.manual_import_allowed:
        routes = "crawler and manual import" if fetch.granted else "manual import only"
        return Gate("store", title, True, f"{policy}; {routes}", evidence)
    if not fetch.granted:
        return Gate("store", title, False, policy, evidence,
                    f"{_waiting(1)}, or a separately approved manual import (manual_import)")  # fmt: skip
    if inst.content_policy is not ContentPolicy.FULL_TEXT:
        return Gate("store", title, False, policy, evidence,
                    f"content_policy is {policy}: no document text is stored, so nothing can be summarised")  # fmt: skip
    return Gate("store", title, True, f"{policy}; crawler", evidence)


def _llm(inst: Institution, store: Gate, llm: LlmSettings) -> Gate:
    level = inst.llm_processing.value
    configured = llm.provider != "disabled"
    hosted = configured and is_hosted(llm)
    where = (
        "none configured"
        if not configured
        else f"{llm.provider}/{llm.model} ({'hosted' if hosted else 'local'})"
    )
    evidence = (
        f"llm_processing: {level}",
        f"llm_processing_note: {inst.llm_processing_note or '-'}",
        f"provider: {where}",
        f"run budget: ${llm.limits.max_run_usd:.2f}; 30-day cap ${llm.limits.max_period_usd:.2f}",
    )
    detail = f"{level}; provider {where}"
    if not store.granted:
        return Gate("llm", "LLM processing", False, detail, evidence, _waiting(2))
    if inst.llm_processing is LlmProcessing.DENIED:
        return Gate("llm", "LLM processing", False, detail, evidence,
                    "llm_processing is denied: record what the terms say about third-party processing first")  # fmt: skip
    if not configured:
        return Gate("llm", "LLM processing", False, detail, evidence,
                    "no LLM provider is configured (NZSTATS_LLM_PROVIDER)")  # fmt: skip
    refusal = inst.llm_refusal(hosted=hosted)
    return Gate("llm", "LLM processing", refusal is None, detail, evidence, refusal)


def _publish(inst: Institution, env: Mapping[str, str]) -> Gate:
    level = inst.display_level()
    switch = "on" if public_research_enabled(env) else "off"
    evidence = (
        f"public_display: {inst.public_display.value} (effective {level.value})",
        f"approved: {inst.public_display_approved_by or '-'} on {inst.public_display_approved_on or '-'}",
        f"public_display_note: {inst.public_display_note or '-'}",
    )
    detail = f"{level.value}; {ENABLE_ENV} {switch}"
    if level is PublicDisplay.NONE:
        reason = (
            _waiting(2)
            if not inst.source_permitted
            else "public_display is none: a separate, recorded decision is needed"
        )
        return Gate("publish", "Public display", False, detail, evidence, reason)
    warnings = ()
    if level is not inst.public_display:
        warnings = (
            f"registry asks for {inst.public_display.value}; AI text is withheld while LLM processing is denied",
        )
    return Gate("publish", "Public display", True, detail, evidence, None, warnings)


def assess(inst: Institution, llm: LlmSettings, *, env: Mapping[str, str]) -> Readiness:
    fetch = _fetch(inst)
    store = _store(inst, fetch)
    gates = (fetch, store, _llm(inst, store, llm), _publish(inst, env))
    return Readiness(inst.key, inst.name, gates)


def pipeline_state(
    conn: sqlite3.Connection, inst: Institution, registry: Mapping[str, Institution]
) -> PipelineState:
    """What the pilot has stored so far for one institution (read-only)."""
    row = conn.execute(
        "SELECT COUNT(*) AS publications, COUNT(p.current_version_id) AS current_versions"
        " FROM research_publication p JOIN research_institution i ON i.id = p.institution_id WHERE i.key = ?",
        (inst.key,),
    ).fetchone()
    by_status: dict[str, int] = {}
    approved = 0
    for r in conn.execute(
        "SELECT s.status, s.review_status, COUNT(*) AS n FROM research_summary s"
        " JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE i.key = ? GROUP BY 1, 2",
        (inst.key,),
    ):
        by_status[r["status"]] = by_status.get(r["status"], 0) + r["n"]
        approved += r["n"] if r["review_status"] == "approved" else 0
    public = sum(1 for p in public_summaries(conn, registry) if p.institution.key == inst.key)
    return PipelineState(row["publications"], row["current_versions"], by_status, approved, public)
