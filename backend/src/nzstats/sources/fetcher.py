"""Polite HTTP: one request at a time, >= min_interval apart, bounded retries, block detection."""

from __future__ import annotations

import fcntl
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from nzstats.clock import utc_now
from nzstats.domain import ErrorClass, IngestError

log = logging.getLogger(__name__)

# Text Imperva/Incapsula puts in its challenge pages (often served with HTTP 200).
BLOCK_MARKERS = (b"Request unsuccessful. Incapsula incident ID",)
# After a block, no request of any kind for this long (the planner's per-release cooldown is the same).
BLOCKED_COOLDOWN_SECONDS = 30 * 60
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 5


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: datetime


def build_client(user_agent: str) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent},
        # Redirects are followed by `Fetcher.get`, one paced request per hop, never by the client.
        follow_redirects=False,
        timeout=httpx.Timeout(120.0, connect=15.0),
    )


class FilePacer:
    """Keeps requests at least `min_interval` apart across *processes* sharing one data directory.

    The server's scheduler and a `nzstats discover` run via `docker compose exec` are separate
    processes with separate in-memory throttles. This holds an exclusive `flock` for the duration of
    each request and records the wall-clock time the last one finished, so the crawl delay holds for
    the two together. POSIX only (the supported targets are Linux, Synology and macOS).
    """

    def __init__(
        self,
        path: Path,
        min_interval: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._path = Path(path)
        self._min_interval = min_interval
        self._sleep = sleep
        self._wall = wall

    @contextmanager
    def turn(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                fh.seek(0)
                try:
                    last = float(fh.read().strip() or "nan")
                except ValueError:
                    last = float("nan")
                wait = self._min_interval - (self._wall() - last)
                if wait > 0:  # nan compares False, so a missing or corrupt file never waits
                    self._sleep(wait)
                try:
                    yield
                finally:
                    fh.seek(0)
                    fh.truncate()
                    fh.write(repr(self._wall()))
                    fh.flush()
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)


class Fetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        min_interval: float = 10.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        pacer: FilePacer | None = None,
    ) -> None:
        self._client = client
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._pacer = pacer
        self._last_request: float | None = None
        self._blocked_until: float | None = None

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)

    def get(self, url: str, *, expect: tuple[str, ...] = (), _hops: int = 0) -> FetchResult:
        if self._blocked_until is not None and self._clock() < self._blocked_until:
            # A block page means the site is challenging us: stop all requests, not just this URL.
            raise IngestError(
                ErrorClass.BLOCKED, f"not requested: cooling down after a block, {url}", url=url
            )
        last_problem = "no response"
        for attempt in range(self._max_retries + 1):
            with self._pacer.turn() if self._pacer else nullcontext():
                self._throttle()
                try:
                    resp = self._client.get(url, follow_redirects=False)
                    transport_error = None
                except httpx.TransportError as exc:
                    resp, transport_error = None, exc
                self._last_request = self._clock()
            if transport_error is not None or resp is None:
                # Only the exception type goes into the stored/served detail; the text may name hosts.
                last_problem = f"transport error ({type(transport_error).__name__})"
                log.warning("fetch %s failed: %r (attempt %d)", url, transport_error, attempt + 1)
                self._backoff(attempt)
                continue
            status = resp.status_code
            if status == 404:
                raise IngestError(ErrorClass.NOT_FOUND, f"404 for {url}", url=url)
            if status == 403 or any(m in resp.content[:20000] for m in BLOCK_MARKERS):
                self._blocked_until = self._clock() + BLOCKED_COOLDOWN_SECONDS
                raise IngestError(ErrorClass.BLOCKED, f"blocked ({status}) for {url}", url=url)
            if status in REDIRECT_STATUSES and "location" in resp.headers:
                return self._follow(url, resp.headers["location"], expect, _hops)
            if status == 429 or status >= 500:
                last_problem = f"HTTP {status}"
                log.warning("fetch %s -> %s, attempt %d", url, status, attempt + 1)
                self._backoff(attempt)
                continue
            if status >= 400:
                raise IngestError(ErrorClass.UNEXPECTED, f"HTTP {status} for {url}", url=url)
            ctype = resp.headers.get("content-type", "")
            if expect and not any(ctype.lower().startswith(e) for e in expect):
                cls = ErrorClass.BLOCKED if "html" in ctype.lower() else ErrorClass.UNEXPECTED
                raise IngestError(cls, f"expected {expect} but got {ctype!r} for {url}", url=url)
            return FetchResult(url, status, ctype, resp.content, self._now())
        raise IngestError(ErrorClass.NETWORK, f"gave up on {url}: {last_problem}", url=url)

    def _follow(self, url: str, location: str, expect: tuple[str, ...], hops: int) -> FetchResult:
        target = httpx.URL(url).join(location)
        if target.host != httpx.URL(url).host:
            raise IngestError(ErrorClass.UNEXPECTED, f"redirected off-site from {url}", url=url)
        if hops >= MAX_REDIRECTS:
            raise IngestError(ErrorClass.UNEXPECTED, f"too many redirects from {url}", url=url)
        return self.get(str(target), expect=expect, _hops=hops + 1)

    def _backoff(self, attempt: int) -> None:
        if attempt < self._max_retries:
            self._sleep(self._backoff_base ** (attempt + 1))
