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
