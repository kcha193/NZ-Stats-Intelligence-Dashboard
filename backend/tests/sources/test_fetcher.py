import httpx
import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.fetcher import Fetcher


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _fetcher(handler, ft: FakeTime, **kw) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, sleep=ft.sleep, clock=ft.clock, **kw)


def test_enforces_min_interval_between_requests() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text="x"), ft, min_interval=10.0)
    f.get("http://h.test/a")
    f.get("http://h.test/b")
    assert ft.sleeps == [10.0]  # first request is not delayed; second waits the full interval


def test_waits_only_the_remaining_interval() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text="x"), ft, min_interval=10.0)
    f.get("http://h.test/a")
    ft.t += 4.0
    f.get("http://h.test/b")
    assert ft.sleeps == [6.0]


def test_retries_5xx_then_succeeds() -> None:
    ft = FakeTime()
    calls = iter([503, 502, 200])
    f = _fetcher(lambda r: httpx.Response(next(calls), text="ok"), ft, min_interval=10.0)
    assert f.get("http://h.test/a").status == 200
    assert len(ft.sleeps) >= 2


def test_gives_up_after_max_retries_as_network_error() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(500), ft, max_retries=2)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NETWORK


def test_transport_errors_are_network_errors() -> None:
    def boom(request):
        raise httpx.ConnectError("down")

    ft = FakeTime()
    f = _fetcher(boom, ft, max_retries=1)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NETWORK


def test_404_is_not_found_and_not_retried() -> None:
    ft = FakeTime()
    calls = []
    f = _fetcher(lambda r: (calls.append(1), httpx.Response(404))[1], ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NOT_FOUND and len(calls) == 1


def test_403_is_blocked_and_not_retried() -> None:
    ft = FakeTime()
    calls = []
    f = _fetcher(lambda r: (calls.append(1), httpx.Response(403))[1], ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.BLOCKED and len(calls) == 1


def test_incapsula_challenge_served_as_200_is_blocked() -> None:
    body = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
    ft = FakeTime()
    f = _fetcher(
        lambda r: httpx.Response(200, text=body, headers={"content-type": "text/html"}), ft
    )
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a.csv", expect=("text/csv",))
    assert e.value.error_class is ErrorClass.BLOCKED


def test_html_where_data_was_expected_is_blocked() -> None:
    ft = FakeTime()
    f = _fetcher(
        lambda r: httpx.Response(
            200, text="<html>hi</html>", headers={"content-type": "text/html; charset=utf-8"}
        ),
        ft,
    )
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/x.ics", expect=("text/calendar",))
    assert e.value.error_class is ErrorClass.BLOCKED


def test_other_unexpected_content_type() -> None:
    ft = FakeTime()
    f = _fetcher(
        lambda r: httpx.Response(200, content=b"\x00", headers={"content-type": "image/png"}), ft
    )
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/x.ics", expect=("text/calendar",))
    assert e.value.error_class is ErrorClass.UNEXPECTED


def test_expected_type_passes_and_returns_body() -> None:
    ft = FakeTime()
    f = _fetcher(
        lambda r: httpx.Response(
            200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv; charset=utf-8"}
        ),
        ft,
    )
    res = f.get("http://h.test/a.csv", expect=("text/csv",))
    assert res.body == b"a,b\n1,2\n" and res.content_type.startswith("text/csv")


# --- regression from the final review: the CLI and the server are separate processes ----------------


def test_two_fetchers_sharing_a_pacer_respect_the_interval_together(tmp_path) -> None:
    """`docker compose exec nzstats nzstats discover` runs beside the server's scheduler."""
    from nzstats.sources.fetcher import FilePacer

    wall = FakeTime()  # shared wall clock; sleeping advances it for everyone
    path = tmp_path / ".request-pace"
    pacer_a = FilePacer(path, 10.0, sleep=wall.sleep, wall=wall.clock)
    pacer_b = FilePacer(path, 10.0, sleep=wall.sleep, wall=wall.clock)
    # Each fetcher has its own private (monotonic) clock, as separate processes would.
    a = _fetcher(
        lambda r: httpx.Response(200, text="x"), FakeTime(), min_interval=10.0, pacer=pacer_a
    )
    b = _fetcher(
        lambda r: httpx.Response(200, text="x"), FakeTime(), min_interval=10.0, pacer=pacer_b
    )
    a.get("http://h.test/a")
    started_b = wall.t
    wall.t += 3.0  # process B asks 3 s after A finished
    b.get("http://h.test/b")
    assert wall.sleeps == [7.0], "B must wait out the rest of the 10 s window set by A"
    assert wall.t - started_b >= 10.0


# --- regression from the final review: stored/served error text must not carry raw exception text ---


def test_network_error_detail_names_the_failure_class_not_the_exception_text(caplog) -> None:
    def boom(request):
        raise httpx.ConnectError("[Errno -3] name resolution failed for internal-host-10.0.0.5")

    ft = FakeTime()
    f = _fetcher(boom, ft, min_interval=10.0, max_retries=1)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NETWORK
    assert "10.0.0.5" not in str(e.value) and "ConnectError" in str(e.value)
    assert "10.0.0.5" in caplog.text  # the operator still gets the full text in the server log


def _redirecting(routes: dict[str, httpx.Response], calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return routes[str(request.url)]

    return handler


def test_redirect_hops_wait_the_crawl_delay_and_record_the_final_url() -> None:
    # A redirect is a request too: following it inside the client would skip the 10 s delay.
    ft, calls = FakeTime(), []
    routes = {
        "https://h.test/a": httpx.Response(301, headers={"location": "/b"}),
        "https://h.test/b": httpx.Response(200, text="x"),
    }
    f = _fetcher(_redirecting(routes, calls), ft, min_interval=10.0)
    result = f.get("https://h.test/a")
    assert calls == ["https://h.test/a", "https://h.test/b"]
    assert ft.sleeps == [10.0]
    assert result.url == "https://h.test/b"


def test_off_site_redirect_is_not_followed() -> None:
    ft, calls = FakeTime(), []
    routes = {"https://h.test/a": httpx.Response(302, headers={"location": "https://evil.test/c"})}
    f = _fetcher(_redirecting(routes, calls), ft)
    with pytest.raises(IngestError) as e:
        f.get("https://h.test/a")
    assert e.value.error_class is ErrorClass.UNEXPECTED and calls == ["https://h.test/a"]


def test_redirect_loop_gives_up() -> None:
    ft, calls = FakeTime(), []
    routes = {
        "https://h.test/a": httpx.Response(302, headers={"location": "/b"}),
        "https://h.test/b": httpx.Response(302, headers={"location": "/a"}),
    }
    f = _fetcher(_redirecting(routes, calls), ft)
    with pytest.raises(IngestError) as e:
        f.get("https://h.test/a")
    assert e.value.error_class is ErrorClass.UNEXPECTED and len(calls) <= 6


def test_a_block_stops_every_request_until_the_cooldown_ends() -> None:
    # After a 403 or challenge page, requesting other URLs keeps provoking a site that is challenging us.
    ft, calls = FakeTime(), []
    f = _fetcher(lambda r: (calls.append(str(r.url)), httpx.Response(403))[1], ft)
    with pytest.raises(IngestError):
        f.get("http://h.test/a")
    ft.t += 29 * 60
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/b")
    assert e.value.error_class is ErrorClass.BLOCKED and calls == ["http://h.test/a"]
    ft.t += 60
    with pytest.raises(IngestError):
        f.get("http://h.test/c")
    assert calls == ["http://h.test/a", "http://h.test/c"]


# --- regression from the PR review: every block starts one cooldown, shared by every process ----------

BLOCK_BODY = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
HTML = {"content-type": "text/html; charset=utf-8"}
COOLDOWN = 30 * 60


def _shared(tmp_path, wall: FakeTime, name: str = ".request-pace"):
    from nzstats.sources.fetcher import FilePacer

    return FilePacer(tmp_path / name, 10.0, sleep=wall.sleep, wall=wall.clock)


def _pair(tmp_path, handler_a, handler_b, wall: FakeTime):
    """Two fetchers as two processes would have them: private clocks, one shared state file."""
    a = _fetcher(handler_a, FakeTime(), min_interval=10.0, pacer=_shared(tmp_path, wall))
    b = _fetcher(handler_b, FakeTime(), min_interval=10.0, pacer=_shared(tmp_path, wall))
    return a, b


BLOCK_RESPONSES = {
    "403": (lambda: httpx.Response(403), ()),
    "challenge marker on a 200": (
        lambda: httpx.Response(200, text=BLOCK_BODY, headers=HTML),
        ("text/csv",),
    ),
    "challenge marker without an expectation": (
        lambda: httpx.Response(200, text=BLOCK_BODY, headers=HTML),
        (),
    ),
    "html where csv was expected, no marker": (
        lambda: httpx.Response(200, text="<html>Just a moment...</html>", headers=HTML),
        ("text/csv",),
    ),
    "html where json was expected, no marker": (
        lambda: httpx.Response(200, text="<html>Access denied</html>", headers=HTML),
        ("application/json",),
    ),
}


@pytest.mark.parametrize("shared", [False, True], ids=["in-process", "shared-file"])
@pytest.mark.parametrize("make,expect", BLOCK_RESPONSES.values(), ids=BLOCK_RESPONSES.keys())
def test_every_blocked_response_starts_the_cooldown(make, expect, shared, tmp_path) -> None:
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return make()

    wall = FakeTime()
    ft = FakeTime()
    kw = {"pacer": _shared(tmp_path, wall)} if shared else {}
    f = _fetcher(handler, ft, **kw)
    with pytest.raises(IngestError) as first:
        f.get("http://h.test/a.csv", expect=expect)
    assert first.value.error_class is ErrorClass.BLOCKED
    assert calls == ["http://h.test/a.csv"], "a blocked response must not be retried"
    ft.t += 60
    wall.t += 60
    with pytest.raises(IngestError) as later:
        f.get("http://h.test/other.csv", expect=expect)
    assert later.value.error_class is ErrorClass.BLOCKED
    assert calls == ["http://h.test/a.csv"], "no HTTP traffic to a different URL during cooldown"


@pytest.mark.parametrize("shared", [False, True], ids=["in-process", "shared-file"])
def test_a_plain_content_type_mismatch_is_not_a_site_wide_block(shared, tmp_path) -> None:
    calls: list[str] = []
    png = httpx.Response(200, content=b"\x00", headers={"content-type": "image/png"})

    def handler(request):
        calls.append(str(request.url))
        return png

    f = _fetcher(
        handler, FakeTime(), **({"pacer": _shared(tmp_path, FakeTime())} if shared else {})
    )
    for path in ("a", "b"):
        with pytest.raises(IngestError) as e:
            f.get(f"http://h.test/{path}", expect=("text/csv",))
        assert e.value.error_class is ErrorClass.UNEXPECTED
    assert calls == ["http://h.test/a", "http://h.test/b"]


def test_a_block_in_one_fetcher_stops_requests_from_another_sharing_the_directory(tmp_path) -> None:
    wall, calls_b = FakeTime(), []
    a, b = _pair(
        tmp_path,
        lambda r: httpx.Response(403),
        lambda r: (calls_b.append(str(r.url)), httpx.Response(200, text="x"))[1],
        wall,
    )
    with pytest.raises(IngestError):
        a.get("http://h.test/a")
    wall.t += 60
    with pytest.raises(IngestError) as e:
        b.get("http://h.test/b")
    assert e.value.error_class is ErrorClass.BLOCKED and calls_b == []


def test_the_cooldown_survives_a_restart_and_ends_at_its_deadline(tmp_path) -> None:
    wall, calls = FakeTime(), []
    f = _fetcher(lambda r: httpx.Response(403), FakeTime(), pacer=_shared(tmp_path, wall))
    with pytest.raises(IngestError):
        f.get("http://h.test/a")
    wall.t += COOLDOWN - 1

    def ok(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="x")

    restarted = _fetcher(ok, FakeTime(), pacer=_shared(tmp_path, wall))  # new objects, same file
    with pytest.raises(IngestError):
        restarted.get("http://h.test/b")
    assert calls == []
    wall.t += 1
    assert restarted.get("http://h.test/c").status == 200 and calls == ["http://h.test/c"]


def test_separate_data_directories_have_independent_cooldowns(tmp_path) -> None:
    wall = FakeTime()
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(), two.mkdir()
    a = _fetcher(lambda r: httpx.Response(403), FakeTime(), pacer=_shared(one, wall))
    b = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(two, wall))
    with pytest.raises(IngestError):
        a.get("http://h.test/a")
    assert b.get("http://h.test/b").status == 200


def test_a_refused_request_neither_waits_nor_uses_up_the_crawl_slot(tmp_path) -> None:
    wall = FakeTime()
    a, b = _pair(
        tmp_path, lambda r: httpx.Response(403), lambda r: httpx.Response(200, text="x"), wall
    )
    with pytest.raises(IngestError):
        a.get("http://h.test/a")
    wall.t += 5  # inside the 10 s window; a refusal must not sleep it out
    with pytest.raises(IngestError):
        b.get("http://h.test/b")
    assert wall.sleeps == []


def test_a_shorter_block_never_replaces_a_longer_cooldown(tmp_path) -> None:
    wall = FakeTime()
    pacer = _shared(tmp_path, wall)
    with pacer.turn() as turn:
        turn.block(COOLDOWN)
    with pacer.turn() as turn:
        assert turn.blocked_until == wall.t + COOLDOWN
        turn.block(60)
    with pacer.turn() as turn:
        assert turn.blocked_until == wall.t + COOLDOWN


def test_redirect_hops_stay_paced_and_a_block_on_a_hop_starts_the_cooldown(tmp_path) -> None:
    wall, calls = FakeTime(), []
    routes = {
        "https://h.test/a": httpx.Response(301, headers={"location": "/b"}),
        "https://h.test/b": httpx.Response(403),
    }
    f = _fetcher(_redirecting(routes, calls), FakeTime(), pacer=_shared(tmp_path, wall))
    with pytest.raises(IngestError) as e:
        f.get("https://h.test/a")
    assert e.value.error_class is ErrorClass.BLOCKED
    assert calls == ["https://h.test/a", "https://h.test/b"] and wall.sleeps == [10.0]
    with pytest.raises(IngestError):
        f.get("https://h.test/c")
    assert len(calls) == 2


def test_retries_and_transport_errors_never_start_a_cooldown(tmp_path) -> None:
    wall, calls = FakeTime(), []

    def flaky(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(503) if len(calls) < 4 else httpx.Response(200, text="x")

    f = _fetcher(flaky, FakeTime(), pacer=_shared(tmp_path, wall))
    assert f.get("http://h.test/a").status == 200
    other = _fetcher(
        lambda r: httpx.Response(200, text="y"), FakeTime(), pacer=_shared(tmp_path, wall)
    )
    assert other.get("http://h.test/b").status == 200


def test_the_crawl_delay_still_holds_across_fetchers_after_the_state_format_change(
    tmp_path,
) -> None:
    wall = FakeTime()
    a, b = _pair(
        tmp_path,
        lambda r: httpx.Response(200, text="x"),
        lambda r: httpx.Response(200, text="x"),
        wall,
    )
    a.get("http://h.test/a")
    wall.t += 3
    b.get("http://h.test/b")
    assert wall.sleeps == [7.0]


# --- state-file safety: documented behaviour for legacy, damaged and unwritable state ---------------


def test_a_legacy_bare_timestamp_state_file_still_paces(tmp_path) -> None:
    wall = FakeTime()
    (tmp_path / ".request-pace").write_text(repr(wall.t - 4.0))
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    f.get("http://h.test/a")
    assert wall.sleeps == [6.0]


@pytest.mark.parametrize("junk", ["not a number", '{"last": ', "{}", "nan", "[1, 2"])
def test_unrecoverable_state_is_treated_as_fresh_and_rewritten(junk, tmp_path) -> None:
    wall = FakeTime()
    (tmp_path / ".request-pace").write_text(junk)
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    assert f.get("http://h.test/a").status == 200 and wall.sleeps == []
    g = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    g.get("http://h.test/b")
    assert wall.sleeps == [10.0], "the damaged file was replaced by valid state"


def test_binary_junk_in_the_state_file_is_treated_as_fresh_and_repaired(tmp_path) -> None:
    wall = FakeTime()
    (tmp_path / ".request-pace").write_bytes(b"\xff\xfe\x80garbage")
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    assert f.get("http://h.test/a").status == 200
    g = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    g.get("http://h.test/b")
    assert wall.sleeps == [10.0]


def test_a_deadline_cut_off_mid_number_is_ignored_not_read_as_a_different_time(tmp_path) -> None:
    wall = FakeTime()  # now = 1000.0
    # Torn write of 1000600.0: the surviving "10006" would read as a deadline 2.5 h away.
    (tmp_path / ".request-pace").write_text(f'{{"last": {wall.t!r}, "blocked_until": 10006')
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    assert f.get("http://h.test/a").status == 200 and wall.sleeps == [10.0]  # only `last` survived


def test_a_damaged_file_that_still_shows_an_active_cooldown_keeps_it(tmp_path) -> None:
    wall, calls = FakeTime(), []
    until = wall.t + 600
    # Truncated mid-write: `last` is unreadable but the cooldown deadline survived.
    (tmp_path / ".request-pace").write_text(f'{{"blocked_until": {until!r}, "last": 17x')
    f = _fetcher(
        lambda r: (calls.append(1), httpx.Response(200, text="x"))[1],
        FakeTime(),
        pacer=_shared(tmp_path, wall),
    )
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.BLOCKED and calls == []


def test_an_absurd_future_deadline_is_capped_at_one_cooldown(tmp_path) -> None:
    wall = FakeTime()
    (tmp_path / ".request-pace").write_text(f'{{"blocked_until": {wall.t + 10**9!r}}}')
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    with pytest.raises(IngestError):
        f.get("http://h.test/a")
    wall.t += COOLDOWN
    assert f.get("http://h.test/a").status == 200


def test_a_last_request_time_in_the_future_never_waits_longer_than_the_interval(tmp_path) -> None:
    wall = FakeTime()
    (tmp_path / ".request-pace").write_text(repr(wall.t + 10**6))  # clock stepped backwards
    f = _fetcher(lambda r: httpx.Response(200, text="x"), FakeTime(), pacer=_shared(tmp_path, wall))
    f.get("http://h.test/a")
    assert wall.sleeps == [10.0]


def test_if_the_state_cannot_be_saved_the_block_still_holds_in_this_process(
    tmp_path, monkeypatch
) -> None:
    import os

    writes = []

    def disk_full(fd, data, offset):
        writes.append(data)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "pwrite", disk_full)
    calls = []
    f = _fetcher(
        lambda r: (calls.append(1), httpx.Response(403))[1],
        FakeTime(),
        pacer=_shared(tmp_path, FakeTime()),
    )
    with pytest.raises(IngestError) as first:
        f.get("http://h.test/a")
    assert first.value.error_class is ErrorClass.BLOCKED, (
        "the caller still gets the block, not OSError"
    )
    with pytest.raises(IngestError):
        f.get("http://h.test/b")
    assert calls == [1] and writes, "the save was attempted and failed"


# --- processes and lock timing ----------------------------------------------------------------------


def _child_get(path: str, status: int, out) -> None:
    """Runs in a separate process: one fetch against a mocked server, real clocks, no pacing delay."""
    from nzstats.sources.fetcher import FilePacer

    sent: list[str] = []

    def handler(request):
        sent.append(str(request.url))
        return httpx.Response(status, text="x")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    f = Fetcher(client, min_interval=0.0, pacer=FilePacer(path, 0.0))
    try:
        f.get("http://h.test/child")
        out.put(("ok", len(sent)))
    except IngestError as exc:
        out.put((exc.error_class.value, len(sent)))


def test_a_block_in_another_process_stops_this_one_and_vice_versa(tmp_path) -> None:
    import multiprocessing

    from nzstats.sources.fetcher import FilePacer

    ctx = multiprocessing.get_context("spawn")
    path = tmp_path / ".request-pace"

    def run_child(status: int) -> tuple[str, int]:
        out = ctx.Queue()
        proc = ctx.Process(target=_child_get, args=(str(path), status, out))
        proc.start()
        result = out.get(timeout=60)
        proc.join(timeout=60)
        return result

    assert run_child(403) == ("blocked", 1)
    calls: list[str] = []
    mine = Fetcher(
        httpx.Client(
            transport=httpx.MockTransport(lambda r: (calls.append(1), httpx.Response(200))[1])
        ),
        min_interval=0.0,
        pacer=FilePacer(path, 0.0),
    )
    with pytest.raises(IngestError) as e:
        mine.get("http://h.test/mine")
    assert e.value.error_class is ErrorClass.BLOCKED and calls == []
    assert run_child(200) == ("blocked", 0), "a third process is refused before sending anything"


def test_a_request_waiting_on_the_lock_cannot_slip_past_a_block_being_published(
    tmp_path, monkeypatch
) -> None:
    import fcntl
    import threading

    wall = FakeTime()
    in_flight, release = threading.Event(), threading.Event()
    calls_b: list[str] = []

    def slow_block(request):
        in_flight.set()
        assert release.wait(timeout=30)
        return httpx.Response(403)

    def would_succeed(request):
        calls_b.append(str(request.url))
        return httpx.Response(200, text="x")

    a, b = _pair(tmp_path, slow_block, would_succeed, wall)
    outcome: dict[str, object] = {}

    def run(name: str, fetcher: Fetcher) -> None:
        try:
            outcome[name] = fetcher.get(f"http://h.test/{name}")
        except IngestError as exc:
            outcome[name] = exc.error_class

    b_at_lock = threading.Event()
    real_flock = fcntl.flock

    def flock(fd, op):
        if threading.current_thread().name == "fetch-b":
            b_at_lock.set()
        return real_flock(fd, op)

    monkeypatch.setattr(fcntl, "flock", flock)
    ta = threading.Thread(target=run, args=("a", a))
    ta.start()
    assert in_flight.wait(timeout=30)  # A holds the turn, its 403 is not yet classified
    tb = threading.Thread(target=run, args=("b", b), name="fetch-b")
    tb.start()
    assert b_at_lock.wait(timeout=30)  # B is queued behind A on the lock
    release.set()
    ta.join(timeout=30)
    tb.join(timeout=30)
    assert outcome == {"a": ErrorClass.BLOCKED, "b": ErrorClass.BLOCKED}
    assert calls_b == []
