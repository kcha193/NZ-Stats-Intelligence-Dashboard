"""Polite HTTP: one request at a time, >= min_interval apart, bounded retries, block detection."""

from __future__ import annotations

import fcntl
import json
import logging
import math
import os
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn

import httpx

from nzstats.clock import utc_now
from nzstats.domain import ErrorClass, IngestError, RequestRefused

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


class PaceTurn:
    """What a caller holding the cross-process lock may see and change: the shared cooldown."""

    def __init__(self, blocked_until: float | None, wall: Callable[[], float]) -> None:
        # Wall-clock deadline (epoch seconds) of the cooldown in force when the turn began, else None.
        self.blocked_until = blocked_until
        self._wall = wall

    def block(self, seconds: float) -> None:
        """Start a cooldown that every process sharing the state file will observe.

        Published while the lock is still held, so no other process can send a request between the
        block being seen and the cooldown being visible. A longer cooldown is never shortened.
        """
        until = self._wall() + seconds
        self.blocked_until = until if self.blocked_until is None else max(self.blocked_until, until)


# A number must be followed by `,` or `}`: a value cut off mid-digits is unreadable, not a different time.
_STATE_FIELD = re.compile(r'"(last|blocked_until)"\s*:\s*([-+0-9.eE]+)\s*[,}]')
_STATE_MAX_BYTES = 4096


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


class FilePacer:
    """Keeps requests at least `min_interval` apart, and shares a block cooldown, across *processes*.

    The server's scheduler and a `nzstats discover` run via `docker compose exec` are separate
    processes with separate in-memory state. This holds an exclusive `flock` for the duration of
    each request and keeps, in the same file, the wall-clock time the last one finished and the
    deadline of any block cooldown, so the crawl delay and the stop-after-a-block rule hold for the
    processes together. One lock over one file is what makes "check the cooldown, send, publish a
    block" atomic. POSIX only (the supported targets are Linux, Synology and macOS).

    State is JSON, `{"last": <epoch>, "blocked_until": <epoch>}`; a bare timestamp (the earlier
    format) still reads as `last`. Unreadable state is treated as no history, except that a
    `blocked_until` that can still be read is honoured, and a deadline further out than one
    cooldown is capped (it can only come from damage or a clock step). If the state cannot be
    written, the error is logged and the caller carries on with its own in-process cooldown only.
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
    def turn(self) -> Iterator[PaceTurn]:
        """Wait for the lock, then for the crawl delay unless a cooldown is in force (it is not used up)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Raw descriptor, no buffering: a failed write cannot resurface as an error when it is closed.
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                last, stored = self._load(fd)
                now = self._wall()
                blocked_until = stored
                if blocked_until is not None and blocked_until <= now:
                    blocked_until = None
                elif blocked_until is not None:
                    # The cap is written back below, or it would slide forward with `now` forever.
                    blocked_until = min(blocked_until, now + BLOCKED_COOLDOWN_SECONDS)
                turn = PaceTurn(blocked_until, self._wall)
                if blocked_until is None and last is not None:
                    # Capped, so a `last` in the future (clock stepped back) cannot stall the lock.
                    wait = min(self._min_interval - (now - last), self._min_interval)
                    if wait > 0:
                        self._sleep(wait)
                try:
                    yield turn
                finally:
                    sent = blocked_until is None
                    if sent or turn.blocked_until != stored:
                        state = {"last": self._wall() if sent else last}
                        if turn.blocked_until is not None and turn.blocked_until > self._wall():
                            state["blocked_until"] = turn.blocked_until
                        try:
                            self._save(fd, state)
                        except OSError:
                            log.exception("could not save request pacing state to %s", self._path)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _load(self, fd: int) -> tuple[float | None, float | None]:
        # Bytes decoded leniently: damage that is not valid UTF-8 must read as "unreadable", not raise.
        text = os.pread(fd, _STATE_MAX_BYTES, 0).decode("utf-8", errors="replace").strip()
        if not text:
            return None, None
        legacy = _finite(text)
        if legacy is not None:
            return legacy, None
        found = {name: _finite(value) for name, value in _STATE_FIELD.findall(text)}
        if not found:
            log.warning("unreadable request pacing state in %s; starting fresh", self._path)
        return found.get("last"), found.get("blocked_until")

    @staticmethod
    def _save(fd: int, state: dict[str, float | None]) -> None:
        # Overwrite then shorten, never empty-then-write: a crash in between must not lose a cooldown.
        data = json.dumps(state).encode()
        os.pwrite(fd, data, 0)
        os.ftruncate(fd, len(data))


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
        self._refuse_if_cooling_down(url)
        last_problem = "no response"
        for attempt in range(self._max_retries + 1):
            with self._pacer.turn() if self._pacer else nullcontext() as turn:
                if turn is not None and turn.blocked_until is not None:
                    # Another process (or an earlier turn of ours) was blocked: send nothing.
                    self._refuse(url)
                self._throttle()
                try:
                    resp = self._client.get(url, follow_redirects=False)
                    transport_error = None
                except httpx.TransportError as exc:
                    resp, transport_error = None, exc
                self._last_request = self._clock()
                # Classified and published before the turn ends, so the next process to take the
                # lock already sees the cooldown.
                block = self._block_error(resp, url, expect) if resp is not None else None
                if block is not None:
                    self._blocked_until = self._clock() + BLOCKED_COOLDOWN_SECONDS
                    if turn is not None:
                        turn.block(BLOCKED_COOLDOWN_SECONDS)
            if block is not None:
                raise block
            if transport_error is not None or resp is None:
                # Only the exception type goes into the stored/served detail; the text may name hosts.
                last_problem = f"transport error ({type(transport_error).__name__})"
                log.warning("fetch %s failed: %r (attempt %d)", url, transport_error, attempt + 1)
                self._backoff(attempt)
                continue
            status = resp.status_code
            if status == 404:
                raise IngestError(ErrorClass.NOT_FOUND, f"404 for {url}", url=url)
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
                raise IngestError(
                    ErrorClass.UNEXPECTED, f"expected {expect} but got {ctype!r} for {url}", url=url
                )
            return FetchResult(url, status, ctype, resp.content, self._now())
        raise IngestError(ErrorClass.NETWORK, f"gave up on {url}: {last_problem}", url=url)

    def _refuse_if_cooling_down(self, url: str) -> None:
        if self._blocked_until is not None and self._clock() < self._blocked_until:
            self._refuse(url)

    @staticmethod
    def _refuse(url: str) -> NoReturn:
        # A block page means the site is challenging us: stop all requests, not just this URL.
        raise RequestRefused(
            ErrorClass.BLOCKED, f"not requested: cooling down after a block, {url}", url=url
        )

    @staticmethod
    def _block_error(resp: httpx.Response, url: str, expect: tuple[str, ...]) -> IngestError | None:
        """The error for a response that means the site is challenging us, else None.

        A 404 is a real answer, and redirects and 4xx/5xx statuses other than 403 are handled (retried
        or reported) by the caller. A 2xx page that is HTML where data was expected is a challenge page
        whether or not it carries a known marker.
        """
        status = resp.status_code
        if status == 404:
            return None
        if status == 403 or any(m in resp.content[:20000] for m in BLOCK_MARKERS):
            return IngestError(ErrorClass.BLOCKED, f"blocked ({status}) for {url}", url=url)
        if status >= 400 or (status in REDIRECT_STATUSES and "location" in resp.headers):
            return None
        ctype = resp.headers.get("content-type", "")
        if (
            expect
            and "html" in ctype.lower()
            and not any(ctype.lower().startswith(e) for e in expect)
        ):
            message = f"expected {expect} but got {ctype!r} for {url}"
            return IngestError(ErrorClass.BLOCKED, message, url=url)
        return None

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
