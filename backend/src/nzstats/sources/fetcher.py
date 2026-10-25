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
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
    """Shared deadlines visible while the cross-process request lock is held."""

    def __init__(
        self,
        blocked_until: float | None,
        wall: Callable[[], float],
        retry_until: float | None = None,
    ) -> None:
        self.blocked_until = blocked_until
        self.retry_until = retry_until
        self.persistence_failed = False
        self._wall = wall

    @property
    def retry_wait(self) -> float:
        return max(0.0, self.retry_until - self._wall()) if self.retry_until else 0.0

    def block(self, seconds: float) -> None:
        until = self._wall() + seconds
        self.blocked_until = max(self.blocked_until or until, until)

    def retry_after(self, seconds: float) -> None:
        until = self._wall() + seconds
        self.retry_until = max(self.retry_until or until, until)


_STATE_FIELD = re.compile(r'"(last|blocked_until)"\s*:\s*([-+0-9.eE]+)\s*[,}]')
_STATE_MAX_BYTES = 64 * 1024
MAX_INLINE_RETRY_SECONDS = 60.0


def _finite(text: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class _PaceState:
    last: float | None = None
    blocked_until: float | None = None
    retry_until: float | None = None
    pending: bool = False


class FilePacer:
    """Serialise HTTP across processes, with a durable reservation before every request.

    The flock stays on the same inode throughout. Compact JSON journal records are appended and
    fsynced; incomplete writes cannot overwrite an earlier durable reservation. Reads inspect only
    the last 64 KiB. A pending reservation means a process died or could not save its result: the
    next healthy writer durably replaces it with one fixed 30-minute recovery cooldown. Nonempty
    unrecoverable state gets the same treatment. Persistent storage errors refuse all requests;
    after storage recovers the fixed cooldown expires normally, without sliding on every read.

    Legacy bare timestamps and JSON objects remain readable. The journal is never replaced or
    compacted while other processes could hold its inode. Retry-After has its own shared deadline;
    waits over 60 seconds are returned to the caller instead of occupying a worker.
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

    @staticmethod
    def _storage_refusal() -> NoReturn:
        raise RequestRefused(
            ErrorClass.NETWORK, "not requested: shared pacing state is unavailable"
        )

    def _required_save(self, fd: int, state: _PaceState) -> None:
        try:
            self._save(fd, state)
        except OSError:
            log.exception("could not reserve request pacing state in %s", self._path)
            self._storage_refusal()

    @contextmanager
    def turn(self) -> Iterator[PaceTurn]:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o666)
        except OSError:
            log.exception("could not open request pacing state in %s", self._path)
            self._storage_refusal()
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                # A file fsync alone cannot make a newly created directory entry durable. Sync
                # every turn so a later healthy process also repairs a previous directory-sync failure.
                directory_fd = os.open(self._path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                state, damaged = self._load(fd)
            except OSError:
                log.exception("could not read request pacing state in %s", self._path)
                self._storage_refusal()
            now = self._wall()
            blocked_until = state.blocked_until
            if damaged or state.pending:
                blocked_until = max(blocked_until or now, now + BLOCKED_COOLDOWN_SECONDS)
            if blocked_until is not None:
                blocked_until = min(blocked_until, now + BLOCKED_COOLDOWN_SECONDS)
                if blocked_until <= now:
                    blocked_until = None
            recovered = _PaceState(state.last, blocked_until, state.retry_until)
            if damaged or state.pending or recovered != state:
                self._required_save(fd, recovered)
            turn = PaceTurn(blocked_until, self._wall, state.retry_until)
            if blocked_until is not None or turn.retry_wait > MAX_INLINE_RETRY_SECONDS:
                # Refusals consume no crawl slot and never wait out a site-wide cooldown.
                try:
                    yield turn
                finally:
                    if turn.blocked_until != blocked_until:
                        self._required_save(
                            fd, _PaceState(state.last, turn.blocked_until, turn.retry_until)
                        )
                return
            if turn.retry_wait:
                self._sleep(turn.retry_wait)
            if state.last is not None:
                wait = min(self._min_interval - (self._wall() - state.last), self._min_interval)
                if wait > 0:
                    self._sleep(wait)
            self._required_save(fd, _PaceState(state.last, pending=True))
            try:
                yield turn
            finally:
                try:
                    self._save(fd, _PaceState(self._wall(), turn.blocked_until, turn.retry_until))
                except OSError:
                    # The durable pending record survives. Another process must recover it into a
                    # cooldown before sending; this process also reports the persistence failure.
                    turn.persistence_failed = True
                    log.exception("could not save request pacing result in %s", self._path)
        finally:
            os.close(fd)  # closing the descriptor also releases flock

    def _load(self, fd: int) -> tuple[_PaceState, bool]:
        size = os.fstat(fd).st_size
        if size == 0:
            return _PaceState(), False
        start = max(0, size - _STATE_MAX_BYTES)
        raw = os.pread(fd, _STATE_MAX_BYTES, start)
        # A journal record is authoritative only when its entire JSON and terminating newline exist.
        damaged_newer = False
        for line in reversed(raw.splitlines(keepends=True)):
            if not line.strip():
                continue  # separators carry no state and cannot indicate lost request information
            if not line.endswith(b"\n"):
                damaged_newer = True
                continue
            try:
                data = json.loads(line)
                if (
                    not isinstance(data, dict)
                    or type(data.get("version")) is not int
                    or data["version"] != 1
                ):
                    raise ValueError("invalid pacing journal record")
                if not {"last", "blocked_until", "retry_until", "pending"} <= data.keys():
                    raise ValueError("invalid pacing journal record")
                fields = [data[k] for k in ("last", "blocked_until", "retry_until")]
                if any(
                    v is not None and (type(v) not in (int, float) or _finite(v) is None)
                    for v in fields
                ):
                    raise ValueError("invalid pacing journal record")
                if not isinstance(data.get("pending"), bool):
                    raise ValueError("invalid pacing journal record")
                return _PaceState(
                    *[float(v) if v is not None else None for v in fields], pending=data["pending"]
                ), damaged_newer
            except (UnicodeDecodeError, ValueError):
                # A newer result may have carried a cooldown. An older completed record alone
                # cannot prove it is safe to send; recover with a fixed cooldown in that case.
                damaged_newer = True
                continue
        text = raw.decode("utf-8", errors="replace").strip()
        legacy = _finite(text)
        if start == 0 and legacy is not None:
            return _PaceState(last=legacy), False
        if start == 0:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "last" in data and "version" not in data:
                    fields = [data.get(k) for k in ("last", "blocked_until")]
                    if all(
                        v is None or (type(v) in (int, float) and _finite(v) is not None)
                        for v in fields
                    ):
                        return _PaceState(*fields), False
            except (UnicodeDecodeError, ValueError):
                pass
        found = {name: _finite(value) for name, value in _STATE_FIELD.findall(text)}
        log.warning("damaged request pacing state in %s; recovering with a cooldown", self._path)
        return _PaceState(found.get("last"), found.get("blocked_until")), True

    @staticmethod
    def _save(fd: int, state: _PaceState) -> None:
        data = (
            b"\n"
            + json.dumps(
                {
                    "version": 1,
                    "last": state.last,
                    "blocked_until": state.blocked_until,
                    "retry_until": state.retry_until,
                    "pending": state.pending,
                },
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            + b"\n"
        )
        offset = os.lseek(fd, 0, os.SEEK_END)
        while data:
            written = os.pwrite(fd, data, offset)
            if written <= 0:
                raise OSError("request pacing journal write made no progress")
            offset += written
            data = data[written:]
        os.fsync(fd)


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
        max_bytes: int | None = None,
    ) -> None:
        self._client = client
        # None keeps the original unbounded behaviour (Stats NZ). Research fetchers set a cap so a
        # hostile or broken server cannot make us buffer an arbitrarily large response.
        self._max_bytes = max_bytes
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._pacer = pacer
        self._last_request: float | None = None
        self._blocked_until: float | None = None
        self._retry_until: float | None = None

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)

    def get(
        self,
        url: str,
        *,
        expect: tuple[str, ...] = (),
        url_check: Callable[[str], object] | None = None,
        _hops: int = 0,
    ) -> FetchResult:
        """Fetch `url`. `url_check`, when given, runs on this URL and on every redirect target before
        it is requested and must raise ValueError to refuse (the refusal text is not echoed)."""
        if url_check is not None:
            try:
                url_check(url)
            except ValueError:
                raise IngestError(ErrorClass.UNEXPECTED, f"url refused: {url}", url=url) from None
        self._refuse_if_cooling_down(url)
        last_problem = "no response"
        for attempt in range(self._max_retries + 1):
            with self._pacer.turn() if self._pacer else nullcontext() as turn:
                if turn is not None and turn.blocked_until is not None:
                    # Another process (or an earlier turn of ours) was blocked: send nothing.
                    self._refuse(url)
                if turn is not None and turn.retry_wait > MAX_INLINE_RETRY_SECONDS:
                    self._refuse_retry(url)
                self._throttle()
                try:
                    resp = self._send(url)
                    transport_error = None
                except httpx.TransportError as exc:
                    resp, transport_error = None, exc
                except IngestError:
                    self._last_request = self._clock()
                    raise
                self._last_request = self._clock()
                # Classified and published before the turn ends, so the next process to take the
                # lock already sees the cooldown.
                retry_after = self._retry_after(resp) if resp is not None else None
                if retry_after is not None:
                    self._retry_until = self._clock() + retry_after
                    if turn is not None:
                        turn.retry_after(retry_after)
                block = self._block_error(resp, url, expect) if resp is not None else None
                if block is not None:
                    self._blocked_until = self._clock() + BLOCKED_COOLDOWN_SECONDS
                    if turn is not None:
                        turn.block(BLOCKED_COOLDOWN_SECONDS)
            if block is not None:
                raise block
            if turn is not None and turn.persistence_failed:
                raise IngestError(
                    ErrorClass.NETWORK, "request pacing result could not be saved", url=url
                )
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
                return self._follow(url, resp.headers["location"], expect, _hops, url_check)
            if status == 429 or status >= 500:
                last_problem = f"HTTP {status}"
                log.warning("fetch %s -> %s, attempt %d", url, status, attempt + 1)
                if retry_after is not None and retry_after > MAX_INLINE_RETRY_SECONDS:
                    raise IngestError(
                        ErrorClass.NETWORK, "retry deferred by server Retry-After", url=url
                    )
                self._backoff(attempt, retry_after)
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

    def _send(self, url: str) -> httpx.Response:
        if self._max_bytes is None:
            return self._client.get(url, follow_redirects=False)
        with self._client.stream("GET", url, follow_redirects=False) as resp:
            declared = _finite(resp.headers.get("content-length", ""))
            if declared is not None and declared > self._max_bytes:
                raise self._too_large(url)
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():  # decoded bytes: the cap also bounds decompression
                size += len(chunk)
                if size > self._max_bytes:
                    raise self._too_large(url)
                chunks.append(chunk)
            headers = [
                (k, v)
                for k, v in resp.headers.multi_items()
                if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
            ]
            return httpx.Response(
                resp.status_code, headers=headers, content=b"".join(chunks), request=resp.request
            )

    def _too_large(self, url: str) -> IngestError:
        return IngestError(
            ErrorClass.UNEXPECTED, f"response larger than {self._max_bytes} bytes", url=url
        )

    def _refuse_if_cooling_down(self, url: str) -> None:
        if self._blocked_until is not None and self._clock() < self._blocked_until:
            self._refuse(url)
        if self._retry_until is not None:
            wait = self._retry_until - self._clock()
            if wait > MAX_INLINE_RETRY_SECONDS:
                self._refuse_retry(url)
            if wait > 0:
                self._sleep(wait)

    @staticmethod
    def _refuse_retry(url: str) -> NoReturn:
        raise RequestRefused(
            ErrorClass.NETWORK, "not requested: server Retry-After is in force", url=url
        )

    def _retry_after(self, resp: httpx.Response) -> float | None:
        if resp.status_code != 429 and resp.status_code < 500:
            return None
        header = resp.headers.get("retry-after")
        if header is None:
            return None
        seconds = _finite(header)
        if seconds is not None:
            return seconds if seconds >= 0 else None
        try:
            deadline = parsedate_to_datetime(header)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            return max(0.0, deadline.timestamp() - self._now().timestamp())
        except (TypeError, ValueError, OverflowError):
            return None

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

    def _follow(
        self,
        url: str,
        location: str,
        expect: tuple[str, ...],
        hops: int,
        url_check: Callable[[str], object] | None = None,
    ) -> FetchResult:
        target = httpx.URL(url).join(location)
        if target.host != httpx.URL(url).host:
            raise IngestError(ErrorClass.UNEXPECTED, f"redirected off-site from {url}", url=url)
        if hops >= MAX_REDIRECTS:
            raise IngestError(ErrorClass.UNEXPECTED, f"too many redirects from {url}", url=url)
        return self.get(str(target), expect=expect, url_check=url_check, _hops=hops + 1)

    def _backoff(self, attempt: int, retry_after: float | None = None) -> None:
        if attempt < self._max_retries:
            self._sleep(max(self._backoff_base ** (attempt + 1), retry_after or 0.0))
