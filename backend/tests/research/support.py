"""Offline doubles for the research tests: an approved synthetic institution and a fake website.

Nothing here touches the network. Every body served by `Site` is synthetic (see `SYNTHETIC`);
third-party report text is never committed.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import httpx

from nzstats.research.fetch import ResearchFetcher
from nzstats.research.registry import Institution, build_institution

SYNTHETIC = "SYNTHETIC FIXTURE"
HOST = "research.example.org"
BASE = f"https://{HOST}"
ROBOTS = f"{BASE}/robots.txt"

Entry = bytes | str | tuple[int, dict[str, str], bytes] | Callable[[httpx.Request], httpx.Response]


def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


def institution(key: str = "example", **overrides: Any) -> Institution:
    raw: dict[str, Any] = {
        "name": "Example Research",
        "kind": "bank",
        "allowed_hosts": [HOST],
        "landing_urls": [f"{BASE}/research/"],
        "categories": ["economic_outlook"],
        "review_status": "approved",
        "content_policy": "full_text",
        "robots_evidence": "direct",
        "landing_evidence": "direct",
        "terms_evidence": "direct",
        "licence": "Synthetic test licence",
        "approved_by": "Test Reviewer",
        "approved_on": "2026-10-25",
        "approval_note": "synthetic test source",
        "min_text_chars": 200,
        "discovery": [
            {
                "mechanism": "html_links",
                "url": f"{BASE}/research/",
                "link_pattern": rf"^{re.escape(BASE)}/research/.+",
            }
        ],
    }
    raw.update(overrides)
    return build_institution(key, raw)


class Site:
    """A fake website keyed by absolute URL. Unknown URLs are 404. `requests` lists every URL asked for."""

    def __init__(self, pages: dict[str, Entry] | None = None) -> None:
        self.pages: dict[str, Entry] = dict(pages or {})
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        entry = self.pages.get(url)
        if entry is None:
            return httpx.Response(404, content=b"not found")
        if callable(entry):
            return entry(request)
        if isinstance(entry, tuple):
            status, headers, body = entry
            return httpx.Response(status, headers=headers, content=body)
        if isinstance(entry, str):
            entry = entry.encode()
        ctype = "text/plain" if url.endswith("robots.txt") else "text/html; charset=utf-8"
        return httpx.Response(200, headers={"content-type": ctype}, content=entry)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


class FakeClock:
    """Monotonic time that only moves when something sleeps."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += max(0.0, seconds)


def research_fetcher(
    inst: Institution, site: Site, *, clock: FakeClock | None = None, **kw: Any
) -> ResearchFetcher:
    clock = clock or FakeClock()
    kw.setdefault("resolver", public_resolver)
    return ResearchFetcher(inst, site.client(), sleep=clock.sleep, clock=clock, **kw)
