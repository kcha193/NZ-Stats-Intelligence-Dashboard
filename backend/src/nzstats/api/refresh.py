"""The on-open refresh API: `POST /api/refresh` asks for one bounded check, `GET /api/refresh/status` reads it.

Only the dashboard page this server serves may start a check. The POST must be addressed to a loopback host name
(which also defeats DNS rebinding), carry an `Origin` equal to that same host, and send the `X-NZStats-Client` header;
a cross-origin page cannot add that header without a CORS preflight, and this app answers no preflight. Reads never
start anything, so health checks, uptime probes and tests that only GET cannot cause a download.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from nzstats.api.deps import Conn
from nzstats.models import RefreshRequest, RefreshStatusOut
from nzstats.pipeline.refresh import refresh_status

router = APIRouter()
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
CLIENT_HEADER = "x-nzstats-client"
CLIENT_VALUE = "dashboard"


def _refuse_unless_local_dashboard(request: Request) -> None:
    host = request.headers.get("host", "")
    try:
        hostname = urlsplit(f"//{host}").hostname
    except ValueError:
        hostname = None
    same_origin = request.headers.get("origin") == f"{request.url.scheme}://{host}"
    if (
        hostname not in LOOPBACK
        or not same_origin
        or request.headers.get("sec-fetch-site", "same-origin") != "same-origin"
        or request.headers.get(CLIENT_HEADER) != CLIENT_VALUE
    ):
        raise HTTPException(403, "a refresh can only be requested by the local dashboard")


def _status(request: Request, conn) -> RefreshStatusOut:
    return refresh_status(
        conn, request.app.state.analysable_slugs, request.app.state.collection_mode
    )


@router.get("/refresh/status", response_model=RefreshStatusOut)
def get_refresh_status(request: Request, conn: Conn) -> RefreshStatusOut:
    """Read-only: the last check and what is pending. Never starts a check."""
    return _status(request, conn)


@router.post("/refresh", response_model=RefreshStatusOut)
def post_refresh(
    request: Request, conn: Conn, body: RefreshRequest | None = None
) -> RefreshStatusOut:
    """Start a check unless one is running or a recent result stands; answers at once with the status."""
    _refuse_unless_local_dashboard(request)
    coordinator = request.app.state.refresh
    started = coordinator.trigger(manual=bool(body and body.manual)) if coordinator else False
    out = _status(request, conn)
    out.started = started
    return out
