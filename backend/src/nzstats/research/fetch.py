"""Paced, allowlisted, robots-aware fetching for one institution.

A `ResearchFetcher` wraps the shared `Fetcher` (one request at a time, >= the crawl delay apart, block
cooldowns) and adds the research gates: every URL, and every redirect hop, must pass the
institution's `HostPolicy` and its host's robots.txt before anything is sent. Build one per run; its
robots cache lasts as long as the instance. Each institution has its own pacer file, so a block or a
Retry-After from one institution never stops another, or Stats NZ.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from nzstats.clock import utc_now
from nzstats.domain import ErrorClass, IngestError, RequestRefused
from nzstats.research.registry import Institution
from nzstats.research.safety import (
    ALLOW_ALL,
    DENY_ALL,
    HostPolicy,
    PinnedTransport,
    Resolver,
    RobotsRules,
    UnsafeUrl,
    canonical_target,
    system_resolver,
)
from nzstats.sources.fetcher import Fetcher, FetchResult, FilePacer

log = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 20 * 1024 * 1024
ROBOTS_AGENT = "NZStatsDashboard"

# Fixed wording for every refusal; never upstream text.
_REASONS = {
    "unsafe": "not requested: url is outside the institution's allowlist",
    "robots": "not requested: disallowed by robots.txt",
    "robots_forbidden": "not requested: robots.txt is forbidden to us, so all access is",
    "robots_unavailable": "not requested: robots.txt could not be read this run",
    "robots_crawl_delay": "not requested: robots.txt crawl-delay exceeds the configured delay",
}


class Refused(RequestRefused):
    """Nothing was sent. `reason` is one of the keys of `_REASONS`."""

    def __init__(self, reason: str, url: str) -> None:
        super().__init__(ErrorClass.BLOCKED, _REASONS[reason], url=url)
        self.reason = reason


def build_research_client(user_agent: str, *, resolver: Resolver = system_resolver) -> httpx.Client:
    """The HTTP client for real research requests: pinned to checked addresses, never via a proxy.

    `trust_env=False` matters: a proxy resolves names itself, which would bypass the address check.
    """
    return httpx.Client(
        headers={"User-Agent": user_agent},
        transport=PinnedTransport(resolver),
        trust_env=False,
        follow_redirects=False,  # `Fetcher.get` follows redirects itself, one gated request per hop
        timeout=httpx.Timeout(120.0, connect=15.0),
    )


def research_pacer(
    data_dir: Path,
    inst: Institution,
    *,
    sleep: Callable[[float], None] = time.sleep,
    wall: Callable[[], float] = time.time,
) -> FilePacer:
    return FilePacer(
        Path(data_dir) / f".research-pace-{inst.key}", inst.crawl_delay_seconds, sleep=sleep,
        wall=wall,
    )  # fmt: skip


class ResearchFetcher:
    def __init__(
        self,
        inst: Institution,
        client: httpx.Client,
        *,
        pacer: FilePacer | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        resolver: Resolver | None = system_resolver,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_retries: int = 2,
    ) -> None:
        self.inst = inst
        self.policy = HostPolicy(
            inst.allowed_hosts,
            allowed_path_prefixes=inst.allowed_path_prefixes,
            blocked_path_prefixes=inst.blocked_path_prefixes,
            resolver=resolver,
        )
        # robots.txt lives at the root, which may be outside the institution's path prefixes.
        self._robots_policy = HostPolicy(inst.allowed_hosts, resolver=resolver)
        self._fetcher = Fetcher(
            client, min_interval=inst.crawl_delay_seconds, max_retries=max_retries, sleep=sleep,
            clock=clock, now=now, pacer=pacer, max_bytes=max_bytes,
        )  # fmt: skip
        self._robots: dict[str, RobotsRules] = {}
        self._robots_problem: dict[str, str] = {}
        self.access_restricted = False  # robots.txt answered 401/403: the site refuses us outright

    def get(self, url: str, *, expect: tuple[str, ...] = ()) -> FetchResult:
        # `url_check` runs on this URL and on every redirect hop, before each request.
        return self._fetcher.get(url, expect=expect, url_check=self._gate)

    def check(self, url: str) -> str:
        """The normalised URL if it passes the host policy (no network, no robots); else `Refused`."""
        try:
            return self.policy.check(url)
        except UnsafeUrl:
            raise Refused("unsafe", url) from None

    def robots_for(self, url: str) -> RobotsRules:
        host = (urlsplit(url).hostname or "").lower()
        if host not in self._robots:
            self._robots[host] = self._load_robots(host)
        return self._robots[host]

    def _gate(self, url: str) -> None:
        self.check(url)
        rules = self.robots_for(url)
        host = (urlsplit(url).hostname or "").lower()
        if host in self._robots_problem:
            raise Refused(self._robots_problem[host], url)
        parts = urlsplit(url)
        target = canonical_target((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
        if not rules.allowed(target):
            raise Refused("robots", url)

    def _load_robots(self, host: str) -> RobotsRules:
        robots_url = f"https://{host}/robots.txt"

        def check(u: str) -> None:
            try:
                self._robots_policy.check(u)
            except UnsafeUrl:
                raise Refused("unsafe", u) from None

        try:
            result = self._fetcher.get(robots_url, url_check=check)
        except Refused:
            raise
        except RequestRefused:
            raise  # a cooldown is in force: stop the run, do not guess the rules
        except IngestError as exc:
            if exc.error_class is ErrorClass.NOT_FOUND:
                return ALLOW_ALL
            if exc.error_class is ErrorClass.BLOCKED:
                self.access_restricted = True
                self._robots_problem[host] = "robots_forbidden"
            else:
                self._robots_problem[host] = "robots_unavailable"
            log.warning("robots.txt for %s unavailable (%s)", host, exc.error_class.value)
            return DENY_ALL
        if "html" in result.content_type.lower():
            self._robots_problem[host] = "robots_unavailable"
            return DENY_ALL
        rules = RobotsRules.parse(result.body.decode("utf-8", errors="replace"), ROBOTS_AGENT)
        if rules.crawl_delay is not None and rules.crawl_delay > self.inst.crawl_delay_seconds:
            self._robots_problem[host] = "robots_crawl_delay"
            return DENY_ALL
        return rules
