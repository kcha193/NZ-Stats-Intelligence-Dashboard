"""Optional response cap and per-request URL check added for the research fetchers.

Both default to off, so the Stats NZ fetch path is unchanged (see the rest of the fetcher tests).
"""

import gzip
import tracemalloc
import zlib

import httpx
import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.fetcher import Fetcher


def _fetcher(handler, **kw) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, sleep=lambda s: None, clock=lambda: 0.0, **kw)


def test_body_within_the_cap_is_returned_intact():
    f = _fetcher(lambda r: httpx.Response(200, content=b"x" * 100), max_bytes=100)
    assert f.get("https://h.test/a").body == b"x" * 100


def test_oversized_body_aborts_without_reading_it_all():
    pulled = []

    def chunks():
        for i in range(1000):
            pulled.append(i)
            yield b"y" * 1024

    f = _fetcher(lambda r: httpx.Response(200, content=chunks()), max_bytes=4096)
    with pytest.raises(IngestError) as exc:
        f.get("https://h.test/a")
    assert exc.value.error_class is ErrorClass.UNEXPECTED
    assert "larger than" in str(exc.value)
    assert len(pulled) < 10  # stopped streaming near the cap, did not buffer 1 MB


def test_declared_content_length_over_the_cap_is_rejected_before_reading():
    def handler(request):
        return httpx.Response(200, content=b"z" * 50, headers={"content-length": "999999999"})

    f = _fetcher(handler, max_bytes=1000)
    with pytest.raises(IngestError, match="larger than"):
        f.get("https://h.test/a")


def test_cap_applies_to_the_decompressed_size():
    bomb = gzip.compress(b"0" * 1_000_000)
    assert len(bomb) < 5000

    def handler(request):
        return httpx.Response(200, content=bomb, headers={"content-encoding": "gzip"})

    with pytest.raises(IngestError, match="larger than"):
        _fetcher(handler, max_bytes=10_000).get("https://h.test/a")


def test_a_decompression_bomb_is_never_inflated_past_the_cap_in_memory():
    bomb = gzip.compress(b"0" * 300_000_000)
    assert len(bomb) < 400_000

    def handler(request):  # a real stream: Response(content=...) would inflate inside the mock
        return httpx.Response(
            200, stream=httpx.ByteStream(bomb), headers={"content-encoding": "gzip"}
        )

    tracemalloc.start()
    try:
        with pytest.raises(IngestError, match="larger than"):
            _fetcher(handler, max_bytes=10_000).get("https://h.test/a")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 20_000_000


def test_deflate_within_the_cap_is_decoded_and_unknown_encodings_are_refused():
    payload = b"hello " * 10

    def deflate(request):
        return httpx.Response(
            200,
            stream=httpx.ByteStream(zlib.compress(payload)),
            headers={"content-encoding": "deflate"},
        )

    assert _fetcher(deflate, max_bytes=10_000).get("https://h.test/a").body == payload

    def brotli(request):
        return httpx.Response(
            200, stream=httpx.ByteStream(b"xx"), headers={"content-encoding": "br"}
        )

    with pytest.raises(IngestError, match="content-encoding"):
        _fetcher(brotli, max_bytes=10_000).get("https://h.test/a")


def test_capped_requests_only_advertise_encodings_that_can_be_bounded():
    seen = []

    def handler(request):
        seen.append(request.headers["accept-encoding"])
        return httpx.Response(200, content=b"ok")

    _fetcher(handler, max_bytes=100).get("https://h.test/a")
    assert seen == ["gzip, deflate"]


def test_compressed_body_within_the_cap_is_decoded_once():
    payload = b"hello " * 10

    def handler(request):
        return httpx.Response(
            200, content=gzip.compress(payload), headers={"content-encoding": "gzip"}
        )

    assert _fetcher(handler, max_bytes=10_000).get("https://h.test/a").body == payload


def test_no_cap_means_the_old_unbounded_behaviour():
    f = _fetcher(lambda r: httpx.Response(200, content=b"q" * 200_000))
    assert len(f.get("https://h.test/a").body) == 200_000


def test_status_and_content_type_survive_the_capped_path():
    f = _fetcher(
        lambda r: httpx.Response(200, content=b"<p>", headers={"content-type": "text/html"}),
        max_bytes=100,
    )
    r = f.get("https://h.test/a", expect=("text/html",))
    assert (r.status, r.content_type) == (200, "text/html")


def test_url_check_runs_on_the_first_url_and_every_redirect_hop():
    seen = []

    def check(url):
        seen.append(url)

    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, content=b"done")

    assert _fetcher(handler).get("https://h.test/a", url_check=check).body == b"done"
    assert seen == ["https://h.test/a", "https://h.test/b"]


def test_url_check_refusal_stops_a_redirect_downgrade_before_it_is_requested():
    requested = []

    def check(url):
        if not url.startswith("https://"):
            raise ValueError("not https")

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://h.test/b"})

    with pytest.raises(IngestError) as exc:
        _fetcher(handler).get("https://h.test/a", url_check=check)
    assert exc.value.error_class is ErrorClass.UNEXPECTED
    assert requested == ["https://h.test/a"]
    assert "not https" not in str(exc.value)  # refusal text is not echoed


def test_url_check_refusal_on_the_first_url_sends_nothing():
    requested = []
    f = _fetcher(lambda r: requested.append(1) or httpx.Response(200, content=b"x"))
    with pytest.raises(IngestError):
        f.get("https://h.test/a", url_check=lambda u: (_ for _ in ()).throw(ValueError("no")))
    assert requested == []


def test_a_truncated_compressed_body_is_an_error_not_a_short_page():
    whole = gzip.compress(b"a long report " * 2000)

    def handler(request):
        return httpx.Response(
            200, stream=httpx.ByteStream(whole[:-40]), headers={"content-encoding": "gzip"}
        )

    with pytest.raises(IngestError, match="incomplete"):
        _fetcher(handler, max_bytes=1_000_000).get("https://h.test/a")
