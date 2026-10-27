"""Read-only public research endpoints (Phase 3C), mounted by `nzstats serve` only.

The FastAPI app has no authentication, so anything served here is public. The routes are therefore off unless the
process is started with `NZSTATS_PUBLIC_RESEARCH=1`; while off they answer exactly like an unknown API path. When on,
every response is built from `public.public_summaries`, the one eligibility gate, through the allowlist models in
`api_models`. The registry is read on every request, so revoking a permission takes effect immediately, and a
registry that cannot be read means nothing is shown. The database is opened read-only.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from nzstats.clock import AKL, from_utc_iso, to_akl_iso
from nzstats.research.api_models import (
    DocumentOut,
    EvidenceOut,
    FacetOut,
    ForecastComparisonOut,
    ForecastOut,
    InstitutionOut,
    ProcessingOut,
    ProvenanceOut,
    ResearchDetailOut,
    ResearchFeedOut,
    ResearchItemOut,
    StatementOut,
    VersionOut,
)
from nzstats.research.compare import INDICATOR_NAMES, compare_forecasts, indicator_rank
from nzstats.research.contract import ForecastClaim, Statement
from nzstats.research.public import PublicSummary, public_summaries, topics
from nzstats.research.registry import Institution, PublicDisplay, RegistryError, load_registry
from nzstats.research.verify import VERIFIER_VERSION

log = logging.getLogger(__name__)
ENABLE_ENV = "NZSTATS_PUBLIC_RESEARCH"
_SQLITE_MAX_ID = 2**63 - 1
_KEY_LIST = r"^[a-z][a-z0-9_]{0,31}(?:,[a-z][a-z0-9_]{0,31}){0,19}$"
_TOPIC_LABELS = {"economic_outlook": "Economic outlook", "monetary_policy": "Monetary policy",
                 "financial_stability": "Financial stability", "weekly_commentary": "Weekly commentary"}  # fmt: skip

RegistryLoader = Callable[[], Mapping[str, Institution]]


def public_research_enabled(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(ENABLE_ENV) == "1"


def _read_only(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _connection(request: Request) -> Iterator[sqlite3.Connection]:
    c = _read_only(request.app.state.settings.db_path)
    try:
        yield c
    finally:
        c.close()


Conn = Annotated[sqlite3.Connection, Depends(_connection)]


def _date(utc: str | None) -> str:
    return from_utc_iso(utc).astimezone(AKL).date().isoformat() if utc else ""


def _topic_label(key: str) -> str:
    return _TOPIC_LABELS.get(key, key.replace("_", " ").capitalize())


class _View:
    """Turns eligible summaries into public models; what is visible depends on the source's display level."""

    def __init__(self, item: PublicSummary) -> None:
        self.p = item
        self.ai = item.display.rank >= PublicDisplay.SUMMARY.rank
        self.quotes = item.display is PublicDisplay.EXCERPT

    def institution(self) -> InstitutionOut:
        i = self.p.institution
        return InstitutionOut(key=i.key, name=i.name, kind=i.kind)

    def _evidence(self, refs) -> list[EvidenceOut]:
        return [EvidenceOut(section_ordinal=e.section_ordinal, page=e.page, quote=e.quote if self.quotes else None)
                for e in refs]  # fmt: skip

    def _statement(self, s: Statement | None) -> StatementOut | None:
        return (
            StatementOut(text=s.text, evidence=self._evidence(s.evidence))
            if s and self.ai
            else None
        )

    def item(self) -> ResearchItemOut:
        r, s = self.p.row, self.p.summary
        return ResearchItemOut(
            id=self.p.id,
            institution=self.institution(),
            document=DocumentOut(
                title=r["title"], url=r["canonical_url"], published_on=r["published_on"],
                version_no=r["version_no"], fetched_at=to_akl_iso(r["fetched_at"]), format=r["format"],
                page_count=r["page_count"],
            ),
            display=self.p.display.value,
            topics=topics(r),
            indicators=[i.value for i in s.indicators] if self.ai else [],
            outlook=self._statement(s.outlook),
            drivers=[self._statement(d) for d in s.drivers] if self.ai else [],
            risks=[self._statement(d) for d in s.risks] if self.ai else [],
            uncertainty=self._statement(s.uncertainty),
            n_forecasts=len(s.forecasts) if self.ai else 0,
            processing=ProcessingOut(
                human_reviewed_on=_date(r["reviewed_at"]), published_here_on=_date(r["decided_at"]),
                verifier_version=VERIFIER_VERSION, warnings=self.p.warnings,
            ),
        )  # fmt: skip

    def forecasts(self) -> list[ForecastOut]:
        if not self.ai:
            return []
        r = self.p.row
        return [self._forecast(c, r) for c in self.p.summary.forecasts]

    def _forecast(self, c: ForecastClaim, r: Mapping) -> ForecastOut:
        return ForecastOut(
            summary_id=self.p.id, institution=self.institution(), document_title=r["title"],
            published_on=r["published_on"], indicator=c.indicator.value, indicator_label=c.indicator_label,
            horizon=c.horizon, value=c.value, unit=c.unit, direction=c.direction.value, scenario=c.scenario,
            qualification=c.qualification, evidence=self._evidence(c.evidence),
        )  # fmt: skip

    def searchable(self) -> str:
        """Only text the reader can see: hidden AI text must not be reachable through search."""
        parts = [self.p.row["title"], self.p.institution.name]
        item = self.item()
        for st in (item.outlook, item.uncertainty, *item.drivers, *item.risks):
            if st is not None:
                parts.append(st.text)
        return " ".join(parts).casefold()


def _facets(values: list[str], label: Callable[[str], str], order=sorted) -> list[FacetOut]:
    counts = Counter(values)
    return [FacetOut(value=v, label=label(v), count=counts[v]) for v in order(counts)]


def research_router(
    *, enabled: bool | None = None, registry: RegistryLoader | None = None
) -> APIRouter:
    """The research routes. `enabled=None` reads `NZSTATS_PUBLIC_RESEARCH` now; anything but "1" is off."""
    on = public_research_enabled() if enabled is None else enabled
    load = registry or load_registry
    router = APIRouter()

    def gate() -> None:
        if not on:
            raise HTTPException(404, "not found")

    def views(c: sqlite3.Connection) -> list[_View]:
        try:
            reg = load()
        except (RegistryError, OSError) as exc:
            log.warning("research registry unreadable; nothing is shown publicly: %s", exc)
            return []
        return [_View(p) for p in public_summaries(c, reg)]

    deps = [Depends(gate)]

    @router.get("/research/feed", response_model=ResearchFeedOut, dependencies=deps)
    def feed(
        c: Conn,
        q: Annotated[str | None, Query(max_length=100)] = None,
        institution: Annotated[str | None, Query(pattern=_KEY_LIST)] = None,
        topic: Annotated[str | None, Query(pattern=r"^[a-z_]{1,40}$")] = None,
        indicator: Annotated[str | None, Query(pattern=r"^[a-z_]{1,40}$")] = None,
        sort: Literal["newest", "oldest", "institution"] = "newest",
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    ) -> ResearchFeedOut:
        everything = views(c)
        items = [(v, v.item()) for v in everything]
        names = {i.institution.key: i.institution.name for _, i in items}
        chosen = set(institution.split(",")) if institution else None
        needle = " ".join((q or "").split()).casefold()
        selected = [
            (v, i) for v, i in items
            if (chosen is None or i.institution.key in chosen) and (not topic or topic in i.topics)
            and (not indicator or indicator in i.indicators) and (not needle or needle in v.searchable())
        ]  # fmt: skip
        newest = lambda pair: (pair[1].document.published_on or "", pair[1].id)  # noqa: E731
        if sort == "oldest":
            selected.sort(key=newest)
        elif sort == "institution":
            selected.sort(key=newest, reverse=True)
            selected.sort(key=lambda pair: (pair[1].institution.name, pair[1].institution.key))
        else:
            selected.sort(key=newest, reverse=True)
        return ResearchFeedOut(
            items=[i for _, i in selected[offset : offset + limit]],
            total=len(selected), limit=limit, offset=offset,
            institutions=_facets([i.institution.key for _, i in items], names.__getitem__),
            topics=_facets([t for _, i in items for t in i.topics], _topic_label),
            indicators=_facets([x for _, i in items for x in i.indicators],
                               lambda k: INDICATOR_NAMES.get(k, k),
                               order=lambda counts: sorted(counts, key=indicator_rank)),
        )  # fmt: skip

    @router.get(
        "/research/summaries/{summary_id}", response_model=ResearchDetailOut, dependencies=deps
    )
    def detail(summary_id: int, c: Conn) -> ResearchDetailOut:
        found = (
            next((v for v in views(c) if v.p.id == summary_id), None)
            if 0 < summary_id <= _SQLITE_MAX_ID
            else None
        )
        if found is None:
            raise HTTPException(404, "not found")
        r = found.p.row
        versions = [
            VersionOut(version_no=v["version_no"], fetched_at=to_akl_iso(v["fetched_at"]),
                       current=v["id"] == r["current_version_id"])
            for v in c.execute("SELECT id, version_no, fetched_at FROM research_document_version"
                               " WHERE publication_id = ? ORDER BY version_no", (r["publication_id"],))
        ]  # fmt: skip
        return ResearchDetailOut(
            item=found.item(),
            forecasts=found.forecasts(),
            provenance=ProvenanceOut(
                provider=r["provider"], model=r["model"], hosted=bool(r["hosted"]),
                prompt_version=r["prompt_version"], processing_version=r["processing_version"],
                verifier_version=VERIFIER_VERSION, created_at=to_akl_iso(r["created_at"]),
            ),
            versions=versions,
        )  # fmt: skip

    @router.get("/research/forecasts", response_model=ForecastComparisonOut, dependencies=deps)
    def forecasts(
        c: Conn,
        indicator: Annotated[str | None, Query(pattern=r"^[a-z_]{1,40}$")] = None,
        institution: Annotated[str | None, Query(pattern=_KEY_LIST)] = None,
        horizon: Annotated[str | None, Query(pattern=r"^[a-z_]{1,12}:[0-9/-]{4,9}$")] = None,
    ) -> ForecastComparisonOut:
        claims = [f for v in views(c) for f in v.forecasts()]
        everything = compare_forecasts(claims)
        chosen = set(institution.split(",")) if institution else None
        picked = compare_forecasts([
            f for f in claims
            if (chosen is None or f.institution.key in chosen) and (not indicator or f.indicator == indicator)
        ])  # fmt: skip
        return picked.model_copy(update={
            "groups": [g for g in picked.groups if not horizon or g.horizon_key == horizon],
            "indicators": everything.indicators, "institutions": everything.institutions,
            "horizons": everything.horizons,
        })  # fmt: skip

    return router
