"""The owner's private research preview (Phase 4I): read-only routes, mounted only by `nzstats serve --private-research`.

The server mounts them only when the operator passes the flag, and refuses that flag on any bind but loopback, with
no override. Every request must also come from the local dashboard: a loopback `Host` (which defeats DNS
rebinding), an `Origin` equal to that host when one is sent, `Sec-Fetch-Site: same-origin` when sent, and the
`X-NZStats-Client: dashboard` header, which a cross-origin page cannot add without a CORS preflight that this app
never answers. Disabled routes answer exactly like an unknown path. Every item comes from `private.private_summaries`,
the one private gate, re-checked on each request against a registry read on each request (unreadable: nothing is
shown), over a read-only database connection. Responses are not cached or indexed.

The models are an allowlist: raw model output, reviewer names and notes, parameters, usage and cost have no field.
Each block says what it is (the institution's view, its own forecast, a third party's forecast, a policy decision,
forward guidance, an assumption, or a figure as the institution reports it), and each item says it is institutional
commentary, not an official statistic. No official Stats NZ figure is mixed into these responses.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict

from nzstats.clock import to_akl_iso
from nzstats.research.api import _date, _is_loopback, _read_only
from nzstats.research.contract import EvidenceRef, IssuerRole, Statement
from nzstats.research.private import PrivateSummary, private_summaries
from nzstats.research.registry import Institution, RegistryError, load_registry
from nzstats.research.verify import SCOPE, VERIFIER_VERSION

log = logging.getLogger(__name__)
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
CLIENT_HEADER = "x-nzstats-client"
CLIENT_VALUE = "dashboard"
COMMENTARY_LABEL = (
    "Institutional commentary, summarised by AI and approved by a reviewer. Not an official statistic: the"
    " official Stats NZ figures are on the dashboard pages."
)
_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}

Kind = Literal["institutional_view", "forecast", "third_party_forecast", "policy_decision",
               "forward_guidance", "assumption", "reported_figure"]  # fmt: skip
BADGES: dict[str, str] = {
    "institutional_view": "Institutional view",
    "forecast": "Forecast (the institution's own)",
    "third_party_forecast": "Third-party forecast",
    "policy_decision": "Policy decision",
    "forward_guidance": "Forward guidance",
    "assumption": "Assumption",
    "reported_figure": "Figure as reported by the institution (not the official series)",
}
RegistryLoader = Callable[[], Mapping[str, Institution]]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateEvidenceOut(_Out):
    section_ordinal: int
    page: int | None
    quote: str


class PrivateBlockOut(_Out):
    kind: Kind
    badge: str
    text: str
    evidence: list[PrivateEvidenceOut]
    role: str | None = None  # outlook, driver, risk, uncertainty (institutional views)
    issuer: str | None = None  # forecasts and guidance: who made it
    indicator: str | None = None
    horizon: str | None = None
    value: float | None = None
    unit: str | None = None
    scenario: str | None = None
    qualification: str | None = None
    rate: float | None = None  # policy decisions
    action: str | None = None
    decided_on: str | None = None
    vote_for: int | None = None
    vote_against: int | None = None
    source: str | None = None  # reported figures: who produced it, as the document says
    period: str | None = None
    adjustment: str | None = None
    measure: str | None = None


class PrivateDocumentOut(_Out):
    title: str
    url: str
    published_on: str | None  # the document's own date (Pacific/Auckland civil date)
    fetched_at: str
    version_no: int
    format: str
    page_count: int | None


class PrivateReviewOut(_Out):
    human_reviewed_on: str  # date only: the reviewer's name and note stay out
    verifier_version: str
    warnings: int
    checks_scope: str = SCOPE


class PrivateProvenanceOut(_Out):
    provider: str
    model: str
    hosted: bool
    prompt_version: str
    contract_version: int


class PrivateItemOut(_Out):
    id: int
    label: str = COMMENTARY_LABEL
    official_statistic: Literal[False] = False
    institution: str
    institution_name: str
    document: PrivateDocumentOut
    licence: str
    licence_url: str | None
    review: PrivateReviewOut
    provenance: PrivateProvenanceOut
    blocks: list[PrivateBlockOut]


class PrivateFeedOut(_Out):
    items: list[PrivateItemOut]
    notice: str = COMMENTARY_LABEL


def _evidence(refs: tuple[EvidenceRef, ...]) -> list[PrivateEvidenceOut]:
    return [
        PrivateEvidenceOut(section_ordinal=e.section_ordinal, page=e.page, quote=e.quote)
        for e in refs
    ]


def _block(kind: str, text: str, refs: tuple[EvidenceRef, ...], **fields) -> PrivateBlockOut:
    return PrivateBlockOut(
        kind=kind, badge=BADGES[kind], text=text, evidence=_evidence(refs), **fields
    )


def _blocks(p: PrivateSummary) -> list[PrivateBlockOut]:
    s = p.summary
    views: list[tuple[str, Statement]] = [("outlook", s.outlook)]
    views += [("driver", d) for d in s.drivers] + [("risk", r) for r in s.risks]
    views += [("uncertainty", s.uncertainty)] if s.uncertainty is not None else []
    out = [_block("institutional_view", st.text, st.evidence, role=role) for role, st in views]
    for f in s.facts:
        out.append(_block("reported_figure", f.text, f.evidence, source=f.source, value=f.value, unit=f.unit,
                          period=f.period, adjustment=f.definition.adjustment.value, measure=f.definition.measure))  # fmt: skip
    for c in s.forecasts:
        kind = "third_party_forecast" if c.issuer_role is IssuerRole.THIRD_PARTY else "forecast"
        out.append(_block(kind, c.indicator_label, c.evidence, issuer=c.issuer or p.institution.name,
                          indicator=c.indicator.value, horizon=c.horizon, value=c.value, unit=c.unit,
                          scenario=c.scenario, qualification=c.qualification))  # fmt: skip
    for d in s.decisions:
        out.append(_block("policy_decision", f"Official Cash Rate: {d.action.value}", d.evidence, rate=d.rate,
                          action=d.action.value, decided_on=d.decided_on.isoformat(), vote_for=d.vote_for,
                          vote_against=d.vote_against, issuer=d.decision_maker))  # fmt: skip
    out += [_block("forward_guidance", g.text, g.evidence, issuer=g.issuer) for g in s.guidance]
    out += [_block("assumption", a.text, a.evidence, scenario=a.scenario) for a in s.assumptions]
    return out


def _item(p: PrivateSummary) -> PrivateItemOut:
    r, inst = p.row, p.institution
    return PrivateItemOut(
        id=p.id, institution=inst.key, institution_name=inst.name, licence=inst.licence,
        licence_url=inst.licence_url,
        document=PrivateDocumentOut(title=r["title"], url=r["canonical_url"], published_on=r["published_on"],
                                    fetched_at=to_akl_iso(r["fetched_at"]), version_no=r["version_no"],
                                    format=r["format"], page_count=r["page_count"]),
        review=PrivateReviewOut(human_reviewed_on=_date(r["reviewed_at"]), verifier_version=VERIFIER_VERSION,
                                warnings=p.warnings),
        provenance=PrivateProvenanceOut(provider=r["provider"], model=r["model"], hosted=bool(r["hosted"]),
                                        prompt_version=r["prompt_version"],
                                        contract_version=p.summary.contract_version),
        blocks=_blocks(p),
    )  # fmt: skip


def private_bind_refusal(host: str) -> str | None:
    """Why `nzstats serve --private-research` may not listen on `host`, or None. Loopback only, with no override."""
    if _is_loopback(host):
        return None
    return (
        f"refusing to serve the private research preview on {host!r}: it is for this machine only and has no"
        " login. Listen on 127.0.0.1 (`nzstats serve --host 127.0.0.1 --private-research`)"
    )


def _refuse_unless_local_dashboard(request: Request) -> None:
    host = request.headers.get("host", "")
    try:
        hostname = urlsplit(f"//{host}").hostname
    except ValueError:
        hostname = None
    origin = request.headers.get("origin")
    if (
        hostname not in LOOPBACK
        or (origin is not None and origin != f"{request.url.scheme}://{host}")
        or request.headers.get("sec-fetch-site", "same-origin") != "same-origin"
        or request.headers.get(CLIENT_HEADER) != CLIENT_VALUE
    ):
        raise HTTPException(403, "the private research preview is only for the local dashboard")


def _connection(request: Request) -> Iterator[sqlite3.Connection]:
    c = _read_only(request.app.state.settings.db_path)
    try:
        yield c
    finally:
        c.close()


Conn = Annotated[sqlite3.Connection, Depends(_connection)]


def private_research_router(
    *, enabled: bool = False, registry: RegistryLoader | None = None
) -> APIRouter:
    """The private preview routes; off unless `enabled` (the CLI passes `--private-research`)."""
    load = registry or load_registry
    router = APIRouter()

    def gate(request: Request) -> None:
        if not enabled:
            raise HTTPException(404, "not found")
        _refuse_unless_local_dashboard(request)

    def items(c: sqlite3.Connection) -> list[PrivateItemOut]:
        try:
            reg = load()
        except (RegistryError, OSError) as exc:
            log.warning("research registry unreadable; the private preview shows nothing: %s", exc)
            return []
        return [_item(p) for p in private_summaries(c, reg)]

    deps = [Depends(gate)]

    @router.get("/private/research/items", response_model=PrivateFeedOut, dependencies=deps)
    def feed(c: Conn, response: Response) -> PrivateFeedOut:
        response.headers.update(_HEADERS)
        return PrivateFeedOut(items=items(c))

    @router.get(
        "/private/research/items/{summary_id}", response_model=PrivateItemOut, dependencies=deps
    )
    def detail(
        c: Conn, response: Response, summary_id: Annotated[int, Path(ge=1, le=2**63 - 1)]
    ) -> PrivateItemOut:
        found = next((i for i in items(c) if i.id == summary_id), None)
        if found is None:
            raise HTTPException(404, "not found")
        response.headers.update(_HEADERS)
        return found

    return router
