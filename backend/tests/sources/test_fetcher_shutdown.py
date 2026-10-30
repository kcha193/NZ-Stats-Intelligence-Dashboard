"""Cancellation stops future HTTP attempts while preserving the shared pace journal."""

import json
import threading

import httpx
import pytest

from nzstats.domain import RequestRefused
from nzstats.sources.fetcher import Fetcher, FilePacer


@pytest.mark.parametrize("status", [503, 302, 200])
def test_stop_during_request_prevents_retry_redirect_or_following_get(tmp_path, status):
    stop = threading.Event()
    calls = []

    def handler(request):
        calls.append(str(request.url))
        stop.set()
        return httpx.Response(status, text="ok", headers={"location": "/next"})

    path = tmp_path / ".request-pace"
    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
        pacer=FilePacer(path, 10, sleep=lambda _: None),
    )
    with pytest.raises(RequestRefused):
        f.get("https://h.test/start", stop=stop)
        f.get("https://h.test/another", stop=stop)
    assert calls == ["https://h.test/start"]
    state = json.loads(path.read_text().strip().splitlines()[-1])
    assert not state["pending"] and state["blocked_until"] is None


@pytest.mark.parametrize("wait_kind", ["pacing", "retry", "retry_after"])
def test_stop_during_wait_sends_no_further_request(tmp_path, wait_kind):
    stop = threading.Event()
    calls = []
    path = tmp_path / ".request-pace"

    def sleep(_):
        stop.set()

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(503 if wait_kind == "retry" else 200)

    pacer = FilePacer(path, 10, sleep=sleep)
    if wait_kind != "retry":
        with pacer.turn() as turn:
            if wait_kind == "retry_after":
                turn.retry_after(30)
    before = path.read_bytes() if path.exists() else b""
    f = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleep, pacer=pacer)
    with pytest.raises(RequestRefused):
        f.get("https://h.test/start", stop=stop)
    assert len(calls) == (1 if wait_kind == "retry" else 0)
    state = json.loads(path.read_text().strip().splitlines()[-1])
    assert not state["pending"]
    if wait_kind != "retry":
        assert path.read_bytes() == before


def test_stop_interrupts_wait_for_another_process_pacing_lock(tmp_path):
    import fcntl

    stop, entered = threading.Event(), threading.Event()
    path = tmp_path / ".request-pace"
    calls, errors = [], []
    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(r))),
        pacer=FilePacer(path, 10),
    )

    def run():
        entered.set()
        try:
            f.get("https://h.test/start", stop=stop)
        except RequestRefused as exc:
            errors.append(exc)

    with path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        worker = threading.Thread(target=run)
        worker.start()
        assert entered.wait(1)
        stop.set()
        worker.join(1)
        assert not worker.is_alive()
    assert len(errors) == 1 and calls == [] and path.read_bytes() == b""


@pytest.mark.parametrize("compressed", [False, True])
def test_on_open_request_has_a_total_deadline_even_when_body_keeps_arriving(tmp_path, compressed):
    """HTTPX read timeout alone does not bound a peer sending a chunk just before every timeout."""
    now = [0.0]
    stop = threading.Event()
    chunks_read = []
    # Gzip header bytes yield no decoded content: the deadline must check raw reads.
    payload = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" if compressed else b"x" * 10

    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for n in range(10):
                now[0] += 61
                chunks_read.append(n)
                if n == 0:
                    stop.set()  # finish this operation safely, without waiting indefinitely for EOF
                yield payload[n : n + 1]

    path = tmp_path / ".request-pace"
    f = Fetcher(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200,
                    stream=Trickle(),
                    headers={"content-encoding": "gzip"} if compressed else {},
                )
            )
        ),
        clock=lambda: now[0],
        pacer=FilePacer(path, 10),
    )
    with pytest.raises(RequestRefused):
        f.get("https://h.test/trickle", stop=stop)
        f.get("https://h.test/following", stop=stop)
    assert len(chunks_read) == 2, "the active response must end at the 120-second body deadline"
    state = json.loads(path.read_text().strip().splitlines()[-1])
    assert not state["pending"] and state["blocked_until"] is None
