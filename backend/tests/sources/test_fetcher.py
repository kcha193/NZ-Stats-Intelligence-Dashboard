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
