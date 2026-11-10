"""Internal bank-intelligence routes (Phase 4AE): read-only, mounted only by `drafts_api.internal_drafts_router`.

They inherit that router's gate (loopback, the local dashboard's headers, off unless internal drafts are on) and add
nothing to it. Every response is derived on each request from `drafts.draft_summaries`, the one draft gate, over a
read-only connection: nothing is written, no provider or network client is used, and an unreadable registry or owner
list shows nothing. Responses are not cached or indexed. The models (`bank_models`) are an allowlist.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from nzstats.clock import to_akl_iso, utc_now
from nzstats.research.api_models import ForecastEvaluationOut
from nzstats.research.bank_analytics import (
    bank_comparison,
    bank_consensus,
    bank_divergence,
    bank_evaluation,
    bank_revisions,
)
from nzstats.research.bank_forecast import NormalizedForecast
from nzstats.research.bank_models import (
    VIEW_REASONS,
    BankCardOut,
    BankComparisonOut,
    BankConsensusViewOut,
    BankExclusionOut,
    BankForecastOut,
    BankForecastsOut,
    BankFreshnessOut,
    BankHistoryOut,
    BankRefOut,
    BankRevisionsOut,
    BankStanceOut,
    BankStatusOut,
    BankSummaryOut,
    SeriesStatusOut,
)
from nzstats.research.bank_status import BankStatus, bank_status, bank_status_exit
from nzstats.research.bank_view import BankView, bank_view
from nzstats.research.banks import ADAPTERS, BankAdapter
from nzstats.research.drafts import (
    ALLOWLIST_FILE,
    DraftAllowlistError,
    DraftSummary,
    draft_summaries,
    load_allowlist,
)
from nzstats.research.private_api import _HEADERS, Conn
from nzstats.research.registry import Institution, RegistryError

log = logging.getLogger(__name__)
RegistryLoader = Callable[[], Mapping[str, Institution]]
Indicator = Annotated[str, Query(pattern=r"^[a-z_]{1,40}$")]


def _akl(stamp: str | None) -> str | None:
    return to_akl_iso(stamp) if stamp else None


def _forecast_out(n: NormalizedForecast) -> BankForecastOut:
    return BankForecastOut(
        forecast=n.forecast,
        claim_path=n.claim_path,
        report_kind=n.report_kind,
        adjustment=n.adjustment,
        geography=n.geography,
        measure=n.measure,
        forecast_author=n.forecast_author,
        verifier_version=n.verifier_version,
        document_version_id=n.document_version_id,
    )


def _status_out(s: BankStatus) -> BankStatusOut:
    return BankStatusOut(
        key=s.key,
        name=s.name,
        state=s.state,
        series=[
            SeriesStatusOut(
                series_key=x.series_key,
                series_name=x.series_name,
                state=x.state,
                newest_published_on=x.newest_published_on,
                ingested_at=_akl(x.ingested_at),
                analysed_at=_akl(x.analysed_at),
                last_checked_at=_akl(x.last_checked_at),
            )
            for x in s.series
        ],
    )


def _stance(d: DraftSummary) -> BankStanceOut:
    status = next((c.status for c in d.claims if c.path == "outlook"), "failed")
    return BankStanceOut(text=d.summary.outlook.text, claim_status=status)


def bank_router(
    *,
    gate: Callable[[Request], None],
    load: RegistryLoader,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> APIRouter:
    router = APIRouter()
    deps = [Depends(gate)]

    def read(
        request: Request, c: sqlite3.Connection
    ) -> tuple[Mapping[str, Institution], list[DraftSummary], BankView] | None:
        path = request.app.state.settings.db_path.parent / ALLOWLIST_FILE
        try:
            registry = load()
            allowlist = load_allowlist(path)
        except (RegistryError, DraftAllowlistError, OSError) as exc:
            log.warning("bank intelligence shows nothing: %s", type(exc).__name__)
            return None
        drafts = draft_summaries(c, registry, allowlist)
        return registry, drafts, bank_view(c, registry, allowlist, adapters, drafts=drafts)

    @router.get(
        "/internal/bank-intelligence/summary", response_model=BankSummaryOut, dependencies=deps
    )
    def summary(request: Request, c: Conn, response: Response) -> BankSummaryOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        if got is None:
            return BankSummaryOut(cards=[])
        registry, drafts, view = got
        statuses = {s.key: s for s in bank_status(c, registry, utc_now(), adapters)}
        cards = []
        for bank in view.banks:
            mine = [d for d in drafts if d.institution.key == bank.key]
            newest = max(mine, key=lambda d: (d.row["published_on"] or "", d.id), default=None)
            cards.append(
                BankCardOut(
                    key=bank.key,
                    name=bank.name,
                    state=statuses[bank.key].state,
                    report_name=newest.row["title"] if newest else None,
                    published_on=newest.row["published_on"] if newest else None,
                    stance=_stance(newest) if newest else None,
                )
            )
        return BankSummaryOut(cards=cards)

    @router.get(
        "/internal/bank-intelligence/forecasts", response_model=BankForecastsOut, dependencies=deps
    )
    def forecasts(request: Request, c: Conn, response: Response) -> BankForecastsOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        if got is None:
            return BankForecastsOut(banks=[], forecasts=[], comparison=[], excluded=[])
        _, _, view = got
        return BankForecastsOut(
            banks=[BankRefOut(key=b.key, name=b.name) for b in view.banks],
            forecasts=[_forecast_out(n) for n in view.forecasts],
            comparison=[
                BankComparisonOut(adjustment=a, comparison=x) for a, x in bank_comparison(view)
            ],
            excluded=[
                BankExclusionOut(
                    institution_key=e.institution_key,
                    summary_id=e.summary_id,
                    claim_path=e.claim_path,
                    code=e.code,
                    reason=VIEW_REASONS[e.code],
                )
                for e in view.excluded
            ],
        )

    @router.get(
        "/internal/bank-intelligence/revisions", response_model=BankRevisionsOut, dependencies=deps
    )
    def revisions(request: Request, c: Conn, response: Response) -> BankRevisionsOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        if got is None:
            return BankRevisionsOut(histories=[])
        return BankRevisionsOut(
            histories=[BankHistoryOut(adjustment=a, history=h) for a, h in bank_revisions(got[2])]
        )

    @router.get(
        "/internal/bank-intelligence/consensus",
        response_model=BankConsensusViewOut,
        dependencies=deps,
    )
    def consensus(request: Request, c: Conn, response: Response) -> BankConsensusViewOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        result = bank_consensus(got[2] if got else BankView([], [], [], []))
        return BankConsensusViewOut(consensus=result, divergence=bank_divergence(result))

    @router.get(
        "/internal/bank-intelligence/evaluation",
        response_model=ForecastEvaluationOut,
        dependencies=deps,
    )
    def evaluation(
        request: Request, c: Conn, response: Response, indicator: Indicator = "cpi_inflation"
    ) -> ForecastEvaluationOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        return bank_evaluation(got[2] if got else BankView([], [], [], []), c, indicator)

    @router.get(
        "/internal/bank-intelligence/freshness", response_model=BankFreshnessOut, dependencies=deps
    )
    def freshness(request: Request, c: Conn, response: Response) -> BankFreshnessOut:
        response.headers.update(_HEADERS)
        got = read(request, c)
        if got is None:
            return BankFreshnessOut(banks=[], exit_code=0)
        statuses = bank_status(c, got[0], utc_now(), adapters)
        return BankFreshnessOut(
            banks=[_status_out(s) for s in statuses], exit_code=bank_status_exit(statuses)
        )

    return router
