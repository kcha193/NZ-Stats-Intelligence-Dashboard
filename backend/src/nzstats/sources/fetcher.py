"""Polite HTTP: one request at a time, >= min_interval apart, bounded retries, block detection."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from nzstats.clock import utc_now
from nzstats.domain import ErrorClass, IngestError

log = logging.getLogger(__name__)

# Text Imperva/Incapsula puts in its challenge pages (often served with HTTP 200).
BLOCK_MARKERS = (b"Request unsuccessful. Incapsula incident ID",)


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
        follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=15.0),
    )


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
    ) -> None:
        self._client = client
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._last_request: float | None = None

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)

    def get(self, url: str, *, expect: tuple[str, ...] = ()) -> FetchResult:
        last_problem = "no response"
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(url)
            except httpx.TransportError as exc:
                self._last_request = self._clock()
                last_problem = f"transport error: {exc}"
                log.warning("fetch %s failed (%s), attempt %d", url, last_problem, attempt + 1)
                self._backoff(attempt)
                continue
            self._last_request = self._clock()
            status = resp.status_code
            if status == 404:
                raise IngestError(ErrorClass.NOT_FOUND, f"404 for {url}", url=url)
            if status == 403 or any(m in resp.content[:20000] for m in BLOCK_MARKERS):
                raise IngestError(ErrorClass.BLOCKED, f"blocked ({status}) for {url}", url=url)
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

    def _backoff(self, attempt: int) -> None:
        if attempt < self._max_retries:
            self._sleep(self._backoff_base ** (attempt + 1))
