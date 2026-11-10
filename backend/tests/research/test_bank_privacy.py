"""Phase 4AE: bank routes exist only on the loopback draft router (SYNTHETIC FIXTURE)."""

from fastapi import FastAPI

from nzstats.research.api import research_router
from nzstats.research.drafts_api import internal_drafts_router
from nzstats.research.private_api import private_research_router

from .public_support import registry


def paths(router) -> set[str]:
    """The paths an app serves for this router (included routers are flattened by the OpenAPI schema)."""
    app = FastAPI()
    app.include_router(router)
    return set(app.openapi()["paths"])


def test_the_public_and_private_routers_have_no_bank_routes():
    reg = registry()
    public = research_router(enabled=True, registry=lambda: reg)
    private = private_research_router(enabled=True, registry=lambda: reg)
    for router in (public, private):
        assert not [p for p in paths(router) if "bank" in p]


def test_the_draft_router_is_where_the_bank_routes_live():
    found = paths(internal_drafts_router(enabled=True))
    assert {f"/internal/bank-intelligence/{r}" for r in (
        "summary", "forecasts", "revisions", "consensus", "evaluation", "freshness")} <= found  # fmt: skip
