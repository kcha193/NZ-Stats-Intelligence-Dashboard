"""The institutional source registry: what may be fetched, from where, and under whose approval.

Fail closed: a source is fetched automatically only when it is `approved`, with a named approver, a
date and a note, a non-empty host allowlist and a content policy other than `none`. Storing an
owner-supplied copy (`manual_import`, Phase 3E) is a separate recorded approval that never grants
automated access. Everything the file records about a source (mechanism, terms, evidence) is data for
that human decision; nothing in this module reaches the network.
"""

from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MIN_RESEARCH_DELAY_SECONDS = 10.0  # the same floor as the Stats NZ crawl delay
PRIORITY = ("rbnz", "treasury", "anz", "asb", "westpac")

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_EVIDENCE = ("direct", "direct_blocked", "search", "none")
_KINDS = ("central_bank", "government", "bank", "consultancy")


class RegistryError(ValueError):
    pass


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    RESTRICTED = "restricted"


class ContentPolicy(StrEnum):
    FULL_TEXT = "full_text"  # store extracted text and sections
    METADATA_ONLY = "metadata_only"  # title, date, link; the document body is never downloaded
    NONE = "none"  # no automated access at all


class LlmProcessing(StrEnum):
    """Whether this source's text may be sent to a language model (third-party processing)."""

    DENIED = "denied"  # the default: never sent to any model
    LOCAL_ONLY = "local_only"  # a model running on this machine only (loopback), never a hosted API
    HOSTED = "hosted"  # a hosted provider as well; the terms must allow third-party processing


class ManualImport(StrEnum):
    """Whether an owner-supplied copy of a document may be stored (Phase 3E). Separate from automated access."""

    DENIED = "denied"  # the default
    APPROVED = "approved"  # the terms, read directly, permit storing a copy obtained by a person


class PublicDisplay(StrEnum):
    """What this site may show about a source, to anyone (Phase 3C). Each level includes the one before."""

    NONE = "none"  # the default: nothing about the source is shown
    LINK_ONLY = "link_only"  # title, institution, publication date and a link to the original
    SUMMARY = "summary"  # plus the AI interpretation, forecast claims and evidence locations
    EXCERPT = "excerpt"  # plus the short verbatim quotes the verifier matched

    @property
    def rank(self) -> int:
        return _DISPLAY_ORDER.index(self)


_DISPLAY_ORDER = tuple(PublicDisplay)


class Mechanism(StrEnum):
    RSS = "rss"
    SITEMAP = "sitemap"
    HTML_LINKS = "html_links"
    MANUAL = "manual"


@dataclass(frozen=True)
class Discovery:
    mechanism: Mechanism
    url: str | None = None
    link_pattern: str | None = None  # regex an absolute URL must match (html_links)
    series: str | None = None
    verified: bool = False
    note: str = ""


@dataclass(frozen=True)
class Institution:
    key: str
    name: str
    kind: str
    allowed_hosts: tuple[str, ...]
    allowed_path_prefixes: tuple[str, ...]
    blocked_path_prefixes: tuple[str, ...]
    landing_urls: tuple[str, ...]
    categories: tuple[str, ...]
    discovery: tuple[Discovery, ...]
    review_status: ReviewStatus
    content_policy: ContentPolicy
    public_display: PublicDisplay
    licence: str
    licence_url: str | None
    robots_evidence: str
    landing_evidence: str
    terms_evidence: str
    verified_on: date | None
    polling: str
    access_notes: str
    crawl_delay_seconds: float = MIN_RESEARCH_DELAY_SECONDS
    max_documents_per_run: int = 5
    min_text_chars: int = 500
    expected_publication_days: int | None = (
        None  # health only: a new publication is due at least this often
    )
    url_date_regex: str | None = None
    url_date_format: str | None = None
    approved_by: str | None = None
    approved_on: date | None = None
    approval_note: str | None = None
    discovery_probe: bool = False
    llm_processing: LlmProcessing = LlmProcessing.DENIED
    llm_processing_note: str | None = None
    public_display_approved_by: str | None = None
    public_display_approved_on: date | None = None
    public_display_note: str | None = None
    manual_import: ManualImport = ManualImport.DENIED
    manual_import_approved_by: str | None = None
    manual_import_approved_on: date | None = None
    manual_import_note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def automated_access_allowed(self) -> bool:
        return (
            self.review_status is ReviewStatus.APPROVED
            and self.content_policy is not ContentPolicy.NONE
        )

    @property
    def manual_import_allowed(self) -> bool:
        return self.manual_import is ManualImport.APPROVED

    @property
    def source_permitted(self) -> bool:
        """Material from this source may be held here: fetched by the crawler or stored from a manual import."""
        return self.automated_access_allowed or self.manual_import_allowed

    def holds(self, acquisition: str | None) -> bool:
        """Whether material obtained this way may still be used. Each approval covers only what it let in: crawled
        versions need the crawler approval and imported ones the manual-import approval, so revoking one route is
        never undone by the other. `None` (no version in view) asks whether any route is open."""
        if acquisition is None:
            return self.source_permitted
        return (
            self.manual_import_allowed if acquisition == "manual" else self.automated_access_allowed
        )

    def import_refusal(self) -> str | None:
        """Why an owner-supplied copy may not be stored, in fixed wording (None when allowed)."""
        return None if self.manual_import_allowed else "manual import not approved for this source"

    def refusal_reason(self) -> str | None:
        """Why automated access is refused, in fixed wording (None when allowed)."""
        if self.review_status is ReviewStatus.RESTRICTED:
            return "restricted: automated access is not permitted"
        if self.review_status is ReviewStatus.NEEDS_REVIEW:
            return "needs review: no recorded approval"
        if self.content_policy is ContentPolicy.NONE:
            return "content policy none: automated access is not permitted"
        return None

    def llm_refusal(self, *, hosted: bool, acquisition: str | None = None) -> str | None:
        """Why this source's text (a version obtained by `acquisition`) may not go to a model, in fixed wording."""
        if not self.holds(acquisition) or self.llm_processing is LlmProcessing.DENIED:
            return "llm processing denied for this source"
        if hosted and self.llm_processing is not LlmProcessing.HOSTED:
            return "source permits local models only"
        return None

    def display_level(self, acquisition: str | None = None) -> PublicDisplay:
        """What may be shown now. AI text needs the source's LLM permission too: revoking it withdraws the text."""
        if not self.holds(acquisition):
            return PublicDisplay.NONE
        if (
            self.public_display.rank > PublicDisplay.LINK_ONLY.rank
            and self.llm_processing is LlmProcessing.DENIED
        ):
            return PublicDisplay.LINK_ONLY
        return self.public_display

    def licence_snapshot(self) -> dict[str, Any]:
        return {
            "institution": self.key,
            "licence": self.licence,
            "licence_url": self.licence_url,
            "terms_evidence": self.terms_evidence,
            "content_policy": self.content_policy.value,
            "review_status": self.review_status.value,
            "approved_by": self.approved_by,
            "approved_on": self.approved_on.isoformat() if self.approved_on else None,
            "public_display": self.public_display.value,
            "llm_processing": self.llm_processing.value,
            "manual_import": self.manual_import.value,
            "manual_import_approved_by": self.manual_import_approved_by,
            "manual_import_approved_on": (
                self.manual_import_approved_on.isoformat()
                if self.manual_import_approved_on
                else None
            ),
        }


def default_registry_file() -> Path:
    override = os.environ.get("NZSTATS_RESEARCH_SOURCES_FILE")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "research_sources.toml"
        if candidate.exists():
            return candidate
    raise RegistryError("config/research_sources.toml not found; set NZSTATS_RESEARCH_SOURCES_FILE")


def load_registry(path: Path | None = None) -> dict[str, Institution]:
    file = Path(path) if path is not None else default_registry_file()
    if not file.exists():
        raise RegistryError(f"registry file not found: {file.name}")
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RegistryError(f"registry file is not valid TOML: {exc}") from exc
    institutions = data.get("institutions")
    if not isinstance(institutions, dict) or not institutions:
        raise RegistryError("registry has no [institutions.*] tables")
    return {key: build_institution(key, raw) for key, raw in institutions.items()}


def _enum(enum: type[StrEnum], value: object, field_name: str, key: str) -> Any:
    try:
        return enum(value)
    except ValueError:
        raise RegistryError(f"{key}: invalid {field_name} {value!r}") from None


def _date(value: object, field_name: str, key: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise RegistryError(f"{key}: {field_name} is not an ISO date") from None


def _hosts(values: object, key: str) -> tuple[str, ...]:
    hosts = tuple(values or ())
    for host in hosts:
        if not isinstance(host, str) or not _HOST.match(host):
            raise RegistryError(
                f"{key}: invalid host {host!r} (lowercase DNS name, no scheme or wildcard)"
            )
    return hosts


def _prefixes(values: object, key: str) -> tuple[str, ...]:
    prefixes = tuple(values or ())
    for prefix in prefixes:
        if not isinstance(prefix, str) or not prefix.startswith("/"):
            raise RegistryError(f"{key}: path prefix {prefix!r} must start with '/'")
    return prefixes


def _check_url(url: str, hosts: tuple[str, ...], prefixes: tuple[str, ...], key: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise RegistryError(f"{key}: {url} must be https")
    try:
        port = parts.port
    except ValueError:  # not a number, or outside 0-65535
        raise RegistryError(f"{key}: {url} is not on an allowed host") from None
    if parts.hostname not in hosts or parts.username or port not in (None, 443):
        raise RegistryError(f"{key}: {url} is not on an allowed host")
    if prefixes and not any(parts.path.startswith(p) for p in prefixes):
        raise RegistryError(f"{key}: {url} is outside allowed_path_prefixes")


def _discovery(
    raw: dict[str, Any], hosts: tuple[str, ...], prefixes: tuple[str, ...], key: str
) -> Discovery:
    mechanism = _enum(Mechanism, raw.get("mechanism"), "mechanism", key)
    url, pattern = raw.get("url"), raw.get("link_pattern")
    if mechanism is not Mechanism.MANUAL:
        if not url:
            raise RegistryError(f"{key}: {mechanism.value} discovery needs a url")
        _check_url(url, hosts, prefixes, key)
    if mechanism is Mechanism.HTML_LINKS:
        if not pattern:
            raise RegistryError(f"{key}: html_links discovery needs a link_pattern")
        try:
            re.compile(pattern)
        except re.error:
            raise RegistryError(f"{key}: link_pattern does not compile") from None
    return Discovery(mechanism, url, pattern, raw.get("series"), bool(raw.get("verified", False)),
                     str(raw.get("note", "")))  # fmt: skip


def build_institution(key: str, raw: dict[str, Any]) -> Institution:
    """Validate one `[institutions.<key>]` table. Raises `RegistryError` on anything doubtful."""
    if not isinstance(key, str) or not _KEY.match(key):
        raise RegistryError(f"invalid institution key {key!r} (lowercase letters, digits, '_')")
    review = _enum(ReviewStatus, raw.get("review_status"), "review_status", key)
    policy = _enum(ContentPolicy, raw.get("content_policy"), "content_policy", key)
    kind = raw.get("kind")
    if kind not in _KINDS:
        raise RegistryError(f"{key}: invalid kind {kind!r}")
    display = _enum(PublicDisplay, raw.get("public_display", "none"), "public_display", key)
    manual = _enum(ManualImport, raw.get("manual_import", "denied"), "manual_import", key)
    probe = raw.get("discovery_probe", False)
    if not isinstance(probe, bool):
        raise RegistryError(f"{key}: discovery_probe must be a boolean")
    if (
        display is not PublicDisplay.NONE
        and review is not ReviewStatus.APPROVED
        and manual is not ManualImport.APPROVED
    ):
        raise RegistryError(
            f"{key}: public_display requires an approved source or an approved manual import"
        )
    hosts = _hosts(raw.get("allowed_hosts"), key)
    allowed_prefixes = _prefixes(raw.get("allowed_path_prefixes"), key)
    blocked = _prefixes(raw.get("blocked_path_prefixes"), key)
    landing = tuple(raw.get("landing_urls") or ())
    for url in landing:
        _check_url(url, hosts, allowed_prefixes, key)
    discovery = tuple(_discovery(d, hosts, allowed_prefixes, key) for d in raw.get("discovery", ()))
    evidence = {n: raw.get(f"{n}_evidence", "none") for n in ("robots", "landing", "terms")}
    for name, value in evidence.items():
        if value not in _EVIDENCE:
            raise RegistryError(f"{key}: invalid {name}_evidence {value!r}")
    try:
        delay = float(raw.get("crawl_delay_seconds", MIN_RESEARCH_DELAY_SECONDS))
    except (TypeError, ValueError, OverflowError):
        raise RegistryError(f"{key}: crawl_delay_seconds must be a number") from None
    if not math.isfinite(delay) or delay < MIN_RESEARCH_DELAY_SECONDS:  # NaN would compare False
        raise RegistryError(f"{key}: crawl_delay_seconds must be >= {MIN_RESEARCH_DELAY_SECONDS:g}")
    max_docs = _bounded_int(raw, "max_documents_per_run", 5, 1, 100, key)
    min_chars = _bounded_int(raw, "min_text_chars", 500, 1, 100_000, key)
    cadence = (
        _bounded_int(raw, "expected_publication_days", 0, 1, 730, key)
        if "expected_publication_days" in raw
        else None
    )
    pattern, fmt = raw.get("url_date_regex"), raw.get("url_date_format")
    if pattern is not None:
        try:
            compiled = re.compile(pattern)
        except re.error:
            raise RegistryError(f"{key}: url_date_regex does not compile") from None
        if compiled.groups != 1 or not fmt:
            raise RegistryError(
                f"{key}: url_date_regex needs exactly one group and url_date_format"
            )
    approved_on = _date(raw.get("approved_on"), "approved_on", key)
    llm = _enum(LlmProcessing, raw.get("llm_processing", "denied"), "llm_processing", key)
    inst = Institution(
        key=key, name=str(raw.get("name") or key), kind=kind, allowed_hosts=hosts,
        allowed_path_prefixes=allowed_prefixes, blocked_path_prefixes=blocked, landing_urls=landing,
        categories=tuple(raw.get("categories") or ()), discovery=discovery, review_status=review,
        content_policy=policy, public_display=display, licence=str(raw.get("licence", "")),
        licence_url=raw.get("licence_url"), robots_evidence=evidence["robots"],
        landing_evidence=evidence["landing"], terms_evidence=evidence["terms"],
        verified_on=_date(raw.get("verified_on"), "verified_on", key),
        polling=str(raw.get("polling", "")), access_notes=str(raw.get("access_notes", "")),
        crawl_delay_seconds=delay, max_documents_per_run=max_docs,
        min_text_chars=min_chars, expected_publication_days=cadence, url_date_regex=pattern,
        url_date_format=fmt, approved_by=raw.get("approved_by"), approved_on=approved_on,
        approval_note=raw.get("approval_note"), discovery_probe=probe, llm_processing=llm,
        llm_processing_note=raw.get("llm_processing_note"),
        public_display_approved_by=raw.get("public_display_approved_by"),
        public_display_approved_on=_date(
            raw.get("public_display_approved_on"), "public_display_approved_on", key
        ),
        public_display_note=raw.get("public_display_note"), manual_import=manual,
        manual_import_approved_by=raw.get("manual_import_approved_by"),
        manual_import_approved_on=_date(
            raw.get("manual_import_approved_on"), "manual_import_approved_on", key
        ),
        manual_import_note=raw.get("manual_import_note"),
    )  # fmt: skip
    if review is ReviewStatus.APPROVED:
        _check_approval(inst)
    if manual is ManualImport.APPROVED:
        _check_manual_import(inst)
    if llm is not LlmProcessing.DENIED:
        _check_llm_permission(inst)
    if display is not PublicDisplay.NONE:
        _check_display_permission(inst)
    return inst


def _bounded_int(
    raw: dict[str, Any], name: str, default: int, low: int, high: int, key: str
) -> int:
    value = raw.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RegistryError(f"{key}: {name} must be a whole number from {low} to {high}")
    return value


def _check_approval(inst: Institution) -> None:
    key = inst.key
    for name in ("approved_by", "approved_on", "approval_note"):
        if not getattr(inst, name):
            raise RegistryError(f"{key}: approved source needs {name}")
    if inst.content_policy is ContentPolicy.NONE:
        raise RegistryError(f"{key}: approved source cannot have content_policy 'none'")
    if not inst.allowed_hosts or not (inst.landing_urls or inst.discovery):
        raise RegistryError(f"{key}: approved source needs allowed hosts and a start url")
    if inst.terms_evidence != "direct":
        raise RegistryError(f"{key}: an approved source requires terms_evidence = 'direct'")


def _check_manual_import(inst: Institution) -> None:
    key = inst.key
    for name in ("manual_import_approved_by", "manual_import_approved_on", "manual_import_note"):
        if not getattr(inst, name):
            raise RegistryError(
                f"{key}: manual_import needs {name} (a separate, recorded decision)"
            )
    if inst.review_status is ReviewStatus.RESTRICTED:
        # Restricted means the institution's terms refuse use without permission: record the permission and
        # move the source to needs_review first, so the change is a reviewable edit.
        raise RegistryError(f"{key}: manual_import is not allowed for a restricted source")
    if inst.content_policy is not ContentPolicy.FULL_TEXT:
        raise RegistryError(f"{key}: manual_import needs content_policy 'full_text'")
    if inst.terms_evidence != "direct":
        raise RegistryError(f"{key}: manual_import requires terms_evidence = 'direct'")
    if not inst.allowed_hosts:
        raise RegistryError(
            f"{key}: manual_import needs allowed hosts (the document's address is checked)"
        )


def _check_llm_permission(inst: Institution) -> None:
    key = inst.key
    if not inst.source_permitted:
        raise RegistryError(
            f"{key}: llm_processing needs an approved source or an approved manual import"
        )
    if inst.content_policy is not ContentPolicy.FULL_TEXT:
        raise RegistryError(f"{key}: llm_processing needs content_policy 'full_text'")
    if not inst.llm_processing_note:
        raise RegistryError(f"{key}: llm_processing needs llm_processing_note (what the terms say)")


def _check_display_permission(inst: Institution) -> None:
    key = inst.key
    for name in ("public_display_approved_by", "public_display_approved_on", "public_display_note"):
        if not getattr(inst, name):
            raise RegistryError(
                f"{key}: public_display needs {name} (a separate, recorded decision)"
            )
    if (
        inst.public_display.rank > PublicDisplay.LINK_ONLY.rank
        and inst.content_policy is not ContentPolicy.FULL_TEXT
    ):
        raise RegistryError(
            f"{key}: public_display {inst.public_display.value!r} needs content_policy 'full_text'"
        )
