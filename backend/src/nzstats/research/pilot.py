"""Explicit local frozen-request pilot. No ingestion, migration, display or implicit consent.

Freeze is offline and creates a proposal, never an approval. Execution needs a separately
signed, expiring approval binding that proposal, gold, exact section rights and account controls.
All sensitive artifacts stay in the caller's private data directory; stdout contains metadata only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from nzstats.clock import utc_now
from nzstats.research.contract import LlmLimits, SummaryRequest, build_request
from nzstats.research.hosted import HostedConsent, approved_sections, section_inventory_sha256
from nzstats.research.openrouter import OpenRouterProvider, input_token_bound
from nzstats.research.prompt import PROMPT_VERSION, input_sha256, render
from nzstats.research.providers import OPENROUTER_URL, LlmSettings, Pricing
from nzstats.research.registry import Institution
from nzstats.research.summarise import (
    PROCESSING_VERSION,
    SummariseResult,
    eligible_versions,
    load_sections,
    summarise_versions,
)
from nzstats.research.verify import VERIFIER_VERSION

MODEL = "anthropic/claude-opus-5.5"
CANONICAL_MODEL = "anthropic/claude-opus-5.5-20260921"
ROUTE = "google-vertex/europe"
PILOT_VERSIONS = {1: "treasury", 2: "rbnz"}


class PilotRefused(ValueError):
    """Fixed, content-free refusal safe for terminal output."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SectionRight(_Strict):
    ordinal: StrictInt
    rights_basis: str = Field(min_length=1)
    third_party_rights: str = Field(min_length=1)
    attribution: str = Field(min_length=1)


class DocumentRights(_Strict):
    version_id: StrictInt
    sections: tuple[SectionRight, ...]


class Approval(_Strict):
    state: Literal["approved"]
    approved_by: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime
    frozen_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_path: Path
    gold_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gold_review: str = Field(min_length=1)
    provider_review: str = Field(min_length=1)
    account_controls_evidence: str = Field(min_length=1)
    dedicated_key_confirmed: Literal[True]
    rights: tuple[DocumentRights, ...]


def file_sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def _bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise PilotRefused("artifact directory must not be a symlink")
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def _settings(key: str) -> LlmSettings:
    return LlmSettings(
        "openrouter",
        MODEL,
        key,
        OPENROUTER_URL,
        Pricing(4.4, 22),
        LlmLimits(
            max_input_chars=45000,
            max_output_tokens=6000,
            max_documents_per_run=2,
            max_retries=0,
            max_run_usd=5,
            max_period_usd=5,
        ),
        ROUTE,
    )


def _body(provider: OpenRouterProvider, request: SummaryRequest, boundary: str) -> dict:
    body = OpenRouterProvider.request_body(provider, request)
    framed = render(request, published_on=request.published_on, boundary=boundary)
    body["messages"] = [
        {"role": "system", "content": framed.system},
        {"role": "user", "content": framed.user},
    ]
    return body


def freeze(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    scopes: Mapping[int, tuple[int, ...]],
    output: Path,
) -> dict:
    """Create exact local frames and metadata, without network calls or database writes."""
    if not scopes or len(scopes) > 2 or any(type(v) is not int for v in scopes):
        raise PilotRefused("one or two exact pilot versions required")
    candidates, refusals = eligible_versions(
        conn,
        registry,
        hosted=True,
        version_ids=tuple(scopes),
        version_scoped_hosted=True,
    )
    if refusals or {c.version_id for c in candidates} != set(scopes):
        raise PilotRefused("source acquisition or exact version refused")
    settings = _settings("offline-freeze-no-transmission")
    with httpx.Client(trust_env=False) as client:
        provider = OpenRouterProvider(settings, client)
        documents = []
        for c in sorted(candidates, key=lambda c: c.version_id):
            ordinals = scopes[c.version_id]
            sections = load_sections(conn, c.version_id)
            if (
                PILOT_VERSIONS.get(c.version_id) != c.institution
                or not isinstance(ordinals, tuple)
                or not ordinals
                or any(type(n) is not int or n not in sections for n in ordinals)
                or tuple(sorted(set(ordinals))) != ordinals
                or (c.institution == "rbnz" and 0 in ordinals)
            ):
                raise PilotRefused("exact approved section scope required; RBNZ chrome excluded")
            request = build_request(
                c.version_id,
                {n: sections[n] for n in ordinals},
                prompt_version=PROMPT_VERSION,
                limits=settings.limits,
                published_on=c.published_on,
                institution=c.institution,
                author=registry[c.institution].name,
            )
            if not provider.input_fits(request):
                raise PilotRefused("input exceeds frozen pilot limits")
            row = conn.execute(
                "SELECT content_sha256,text_sha256 FROM research_document_version WHERE id=?",
                (c.version_id,),
            ).fetchone()
            boundary = secrets.token_hex(16)
            body = _bytes(_body(provider, request, boundary))
            documents.append(
                {
                    "version_id": c.version_id,
                    "institution": c.institution,
                    "content_sha256": row["content_sha256"],
                    "text_sha256": row["text_sha256"],
                    "sections_sha256": section_inventory_sha256(sections),
                    "approved_section_ordinals": list(ordinals),
                    "boundary": boundary,
                    "request_sha256": input_sha256(
                        request,
                        provider=provider.name,
                        model=MODEL,
                        parameters=provider.parameters(),
                    ),
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                    "worst_case_usd": settings.pricing.cost(input_token_bound(request), 6000),
                }
            )
            _write(output / f"v{c.version_id}-request.json", body)
    result = {
        "format": 1,
        "status": "proposal_only_requires_separate_approval",
        "model": MODEL,
        "canonical_model": CANONICAL_MODEL,
        "provider_id": ROUTE,
        "prompt_version": PROMPT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "contract_version": 2,
        "documents": documents,
    }
    _write(output / "freeze.json", _bytes(result))
    return result


class _FrozenProvider(OpenRouterProvider):
    def __init__(self, settings, client, frames, output):
        super().__init__(settings, client, capture=self._record)
        self.frames, self.output, self.active_version = frames, output, None

    def request_body(self, request):
        frame = self.frames[request.version_id]
        body = _body(self, request, frame["boundary"])
        if hashlib.sha256(_bytes(body)).hexdigest() != frame["body_sha256"]:
            raise PilotRefused("frozen request changed before transmission")
        self.active_version = request.version_id
        return body

    def _record(self, name, body):
        if self.active_version is None:
            raise PilotRefused("capture has no exact version")
        _write(self.output / f"v{self.active_version}" / name, body)


def _get(client: httpx.Client, path: str, *, key: str | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with client.stream(
            "GET", OPENROUTER_URL + path, headers=headers, timeout=20, follow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise PilotRefused("OpenRouter read-only preflight refused")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 4_000_000:
                    raise PilotRefused("preflight response too large")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise PilotRefused("preflight response invalid")
        return parsed
    except (httpx.HTTPError, ValueError) as exc:
        raise PilotRefused("OpenRouter read-only preflight failed") from exc


def _remote_checks(client: httpx.Client, key: str, bound: float) -> dict:
    metadata = _get(client, "/key", key=key).get("data", {})
    if not isinstance(metadata, dict):
        raise PilotRefused("dedicated key metadata invalid")
    numbers_valid = all(
        type(metadata.get(k)) in (int, float)
        and math.isfinite(metadata[k])
        and 0 <= metadata[k] <= 5
        for k in ("limit", "limit_remaining", "usage", "byok_usage")
    )
    if not (
        numbers_valid
        and metadata.get("byok_usage") == 0
        and abs(metadata["limit_remaining"] + metadata["usage"] - 5) <= 0.000001
        and metadata.get("limit") == 5
        and "limit_reset" in metadata
        and metadata["limit_reset"] is None
        and metadata.get("is_management_key") is False
        and type(metadata.get("limit_remaining")) in (int, float)
        and metadata["limit_remaining"] >= bound
    ):
        raise PilotRefused("dedicated key lifetime spending control refused")
    models = _get(client, "/models").get("data", [])
    if not isinstance(models, list) or any(not isinstance(m, dict) for m in models):
        raise PilotRefused("model catalogue invalid")
    matches = [m for m in models if m.get("id") == MODEL]
    if len(matches) != 1 or matches[0].get("canonical_slug") != CANONICAL_MODEL:
        raise PilotRefused("approved model alias identity changed")
    endpoints = _get(client, f"/models/{MODEL}/endpoints").get("data", {})
    zdr = _get(client, "/endpoints/zdr").get("data", [])
    if not isinstance(endpoints, dict) or not isinstance(zdr, list):
        raise PilotRefused("catalogue response invalid")
    selected = []
    for index, entries in enumerate((endpoints.get("endpoints", []), zdr)):
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise PilotRefused("catalogue endpoint list invalid")
        matches = [e for e in entries if e.get("model_id") == MODEL and e.get("tag") == ROUTE]
        if len(matches) != 1:
            raise PilotRefused("exact model/route not uniquely ZDR eligible")
        e = matches[0]
        try:
            prices = (Decimal(e["pricing"]["prompt"]), Decimal(e["pricing"]["completion"]))
            eligible = (
                e.get("provider_name") == "Google"
                and e.get("status") == 0
                # The ordinary catalogue omits this optional field (also in 4L's
                # saved response). ZDR's explicit false is mandatory; any explicit
                # conflicting/unknown ordinary-catalogue value still refuses.
                and (
                    e.get("safety_retention") is False
                    or (index == 0 and "safety_retention" not in e)
                )
                and e.get("supports_implicit_caching") is False
                and e.get("context_length", 0) >= 272000
                and e.get("max_completion_tokens", 0) >= 6000
                and {"max_tokens", "response_format", "reasoning", "reasoning_effort"}.issubset(
                    e.get("supported_parameters", [])
                )
                and prices == (Decimal("0.0000044"), Decimal("0.000022"))
            )
        except (KeyError, TypeError, InvalidOperation):
            eligible = False
        if not eligible:
            raise PilotRefused("provider price/parameters/privacy eligibility changed")
        selected.append(
            {k: e.get(k) for k in ("model_id", "tag", "provider_name", "safety_retention")}
        )
    return {
        "checked_at": utc_now().isoformat(),
        "canonical_model": CANONICAL_MODEL,
        "limit_usd": 5,
        "limit_reset": None,
        "remaining_usd": metadata["limit_remaining"],
        "catalogue_and_zdr": selected,
    }


def execute(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    data_dir: Path,
    frozen: Path,
    approval: Approval,
    output: Path,
    api_key: str,
    *,
    backup_check: Callable[[sqlite3.Connection, Path, Path, datetime], None],
    client: httpx.Client | None = None,
    now_fn: Callable[[], datetime] = utc_now,
) -> list[SummariseResult]:
    """Admit the entire frozen scope first; execute serially without retries or output approval."""
    try:
        approval = Approval.model_validate_json(approval.model_dump_json())
        now = now_fn()
        if (
            approval.approved_at.tzinfo is None
            or approval.expires_at.tzinfo is None
            or not approval.approved_at <= now < approval.expires_at
            or approval.expires_at - approval.approved_at > timedelta(days=1)
            or file_sha256(frozen / "freeze.json") != approval.frozen_sha256
            or file_sha256(approval.gold_path) != approval.gold_sha256
        ):
            raise PilotRefused("approval time, frozen scope or reviewed gold mismatched")
        manifest = json.loads((frozen / "freeze.json").read_bytes())
        expected = (
            1,
            MODEL,
            CANONICAL_MODEL,
            ROUTE,
            PROMPT_VERSION,
            PROCESSING_VERSION,
            VERIFIER_VERSION,
            2,
        )
        actual = tuple(
            manifest[k]
            for k in (
                "format",
                "model",
                "canonical_model",
                "provider_id",
                "prompt_version",
                "processing_version",
                "verifier_version",
                "contract_version",
            )
        )
        if actual != expected:
            raise PilotRefused("frozen execution versions or route changed")
        frames = {f["version_id"]: f for f in manifest["documents"]}
        rights = {d.version_id: d for d in approval.rights}
        if (
            not 1 <= len(frames) <= 2
            or len(frames) != len(manifest["documents"])
            or len(rights) != len(approval.rights)
            or set(rights) != set(frames)
        ):
            raise PilotRefused("rights do not cover the exact frozen document list")
        settings = _settings(api_key)
        grants = []
        for version, frame in frames.items():
            ordinals = tuple(frame["approved_section_ordinals"])
            if (
                PILOT_VERSIONS.get(version) != frame["institution"]
                or not re.fullmatch(r"[0-9a-f]{32}", frame["boundary"])
                or not re.fullmatch(r"[0-9a-f]{64}", frame["content_sha256"])
                or (frame["institution"] == "rbnz" and 0 in ordinals)
                or tuple(s.ordinal for s in rights[version].sections) != ordinals
                or file_sha256(frozen / f"v{version}-request.json") != frame["body_sha256"]
            ):
                raise PilotRefused("rights, section scope or frozen body mismatched")
            raw = data_dir / "raw" / frame["content_sha256"][:2] / frame["content_sha256"]
            if raw.is_symlink() or file_sha256(raw) != frame["content_sha256"]:
                raise PilotRefused("original raw document changed")
            grant = HostedConsent(
                version,
                frame["institution"],
                frame["content_sha256"],
                frame["text_sha256"],
                frame["request_sha256"],
                MODEL,
                ROUTE,
                approval.approved_by,
                approval.approved_at,
                approval.expires_at,
                rights[version].model_dump_json(),
                approval.provider_review,
                5,
                ordinals,
                frame["sections_sha256"],
            )
            approved_sections(load_sections(conn, version), grant)
            grants.append(grant)
    except (ValidationError, KeyError, TypeError, OSError, ValueError) as exc:
        raise PilotRefused("incomplete or mismatched execution approval") from exc
    owned = client is None
    http = client or httpx.Client(trust_env=False, follow_redirects=False, timeout=120)
    try:
        provider = _FrozenProvider(settings, http, frames, output)
        dry = summarise_versions(
            conn,
            registry,
            provider,
            pricing=settings.pricing,
            limits=settings.limits,
            version_ids=tuple(frames),
            dry_run=True,
            hosted_consents=grants,
            now_fn=now_fn,
        )
        if (
            dry.refusals
            or len(dry.items) != len(frames)
            or any(i.outcome != "would_summarise" for i in dry.items)
        ):
            raise PilotRefused("dry-run, existing attempt or budget refused")
        for version in frames:
            # Compare exact wire framing before any preflight network request or database write.
            c, refused = eligible_versions(
                conn, registry, hosted=True, version_ids=(version,), version_scoped_hosted=True
            )
            if refused or len(c) != 1:
                raise PilotRefused("source permission changed")
            request = build_request(
                version,
                approved_sections(
                    load_sections(conn, version), next(g for g in grants if g.version_id == version)
                ),
                prompt_version=PROMPT_VERSION,
                limits=settings.limits,
                published_on=c[0].published_on,
                institution=c[0].institution,
                author=registry[c[0].institution].name,
            )
            provider.request_body(request)
        remote = _remote_checks(http, api_key, sum(i.estimated_usd for i in dry.items))
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        _write(output / "preflight.json", _bytes(remote))
        _write(output / "approval.json", approval.model_dump_json().encode())
        backup_check(conn, data_dir, output, now)
        # One pipeline call preserves existing run/global/rolling reservations and consent rechecks.
        result = summarise_versions(
            conn,
            registry,
            provider,
            pricing=settings.pricing,
            limits=settings.limits,
            version_ids=tuple(frames),
            hosted_consents=grants,
            now_fn=now_fn,
        )
        _write(output / "result.json", _bytes(asdict(result)))
        return [result]
    finally:
        if owned:
            http.close()
