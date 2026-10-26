"""Optional response cap and per-request URL check added for the research fetchers.

Both default to off, so the Stats NZ fetch path is unchanged (see the rest of the fetcher tests).
"""

import fcntl
import gzip
import os
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


def _streaming(chunks, encoding="gzip", status=200):
    def handler(request):
        return httpx.Response(
            status,
            stream=httpx.ByteStream(b"".join(chunks)),
            headers={"content-encoding": encoding},
        )

    return handler


def test_bytes_after_the_end_of_a_compressed_body_are_refused_not_buffered():
    # A valid gzip member followed by ~300 MB of padding: zlib would park all of it in unused_data.
    class Endless(httpx.SyncByteStream):
        def __iter__(self):
            yield gzip.compress(b"a")
            for _ in range(300):
                yield b"\0" * 1_000_000

    def handler(request):
        return httpx.Response(200, stream=Endless(), headers={"content-encoding": "gzip"})

    tracemalloc.start()
    try:
        with pytest.raises(IngestError, match="after the end"):
            _fetcher(handler, max_bytes=10_000).get("https://h.test/a")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 20_000_000


def test_a_second_gzip_member_is_not_silently_ignored():
    two = gzip.compress(b"first " * 20) + gzip.compress(b"second " * 20)
    with pytest.raises(IngestError, match="after the end"):
        _fetcher(_streaming([two]), max_bytes=10_000).get("https://h.test/a")


def test_raw_deflate_is_decoded_and_an_empty_truncated_stream_is_an_error():
    payload = b"hello " * 10
    comp = zlib.compressobj(wbits=-15)
    raw = comp.compress(payload) + comp.flush()
    assert (
        _fetcher(_streaming([raw], "deflate"), max_bytes=10_000).get("https://h.test/a").body
        == payload
    )
    with pytest.raises(IngestError, match="incomplete"):
        _fetcher(_streaming([gzip.compress(b"x")[:5]]), max_bytes=10_000).get("https://h.test/a")


def test_a_bad_body_on_an_error_status_does_not_hide_the_status():
    f = _fetcher(_streaming([b"xx"], "br", status=403), max_bytes=10_000)
    with pytest.raises(IngestError) as exc:
        f.get("https://h.test/a")
    assert exc.value.error_class is ErrorClass.BLOCKED


def _chunked(chunks, encoding):
    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield from chunks

    def handler(request):
        return httpx.Response(200, stream=Chunks(), headers={"content-encoding": encoding})

    return handler


class _DecoderBudget:
    """Counts zlib decoder constructions in the fetcher and fails the test instead of hanging it."""

    def __init__(self, monkeypatch, limit: int) -> None:
        self.made = 0
        real = zlib.decompressobj

        def counted(*args, **kwargs):
            self.made += 1
            if self.made > limit:
                raise AssertionError("decoder fallback is not one-shot")
            return real(*args, **kwargs)

        monkeypatch.setattr("nzstats.sources.fetcher.zlib.decompressobj", counted)


@pytest.mark.parametrize("junk", [b"\x07\x00", b"\xff", b"\x78\x9c\xff\xff\xff", b"\x00" * 64])
def test_invalid_deflate_bytes_fail_once_with_a_controlled_error(monkeypatch, junk):
    budget = _DecoderBudget(monkeypatch, limit=2)  # zlib/gzip attempt, then one raw attempt
    # Junk that is also no valid raw-deflate prefix is "undecodable"; a lone valid prefix is "incomplete".
    with pytest.raises(IngestError, match="undecodable|incomplete") as exc:
        _fetcher(_streaming([junk], "deflate"), max_bytes=10_000).get("https://h.test/a")
    assert exc.value.error_class in (ErrorClass.UNEXPECTED, ErrorClass.NETWORK)
    assert budget.made <= 2


def test_invalid_deflate_in_a_later_chunk_does_not_retry_the_raw_format(monkeypatch):
    # The raw fallback only applies when the very first bytes were rejected.
    budget = _DecoderBudget(monkeypatch, limit=1)
    good = zlib.compress(b"hello " * 100)
    with pytest.raises(IngestError, match="undecodable"):
        _fetcher(_chunked([good[:10], b"\x07\x00" * 4], "deflate"), max_bytes=10_000).get(
            "https://h.test/a"
        )
    assert budget.made == 1


def test_undecodable_gzip_is_refused_without_a_raw_fallback(monkeypatch):
    budget = _DecoderBudget(monkeypatch, limit=1)
    with pytest.raises(IngestError, match="undecodable"):
        _fetcher(_streaming([b"\x07\x00"], "gzip"), max_bytes=10_000).get("https://h.test/a")
    assert budget.made == 1


def test_zlib_wrapped_deflate_still_decodes_without_the_fallback(monkeypatch):
    budget = _DecoderBudget(monkeypatch, limit=1)
    payload = b"zlib wrapped " * 20
    body = _fetcher(_streaming([zlib.compress(payload)], "deflate"), max_bytes=10_000).get(
        "https://h.test/a"
    )
    assert body.body == payload
    assert budget.made == 1


def test_raw_deflate_split_across_chunks_decodes():
    payload = b"split raw deflate " * 50
    comp = zlib.compressobj(wbits=-15)
    raw = comp.compress(payload) + comp.flush()
    # The first chunk is rejected as a zlib stream, so the raw decoder takes over from byte 0.
    out = _fetcher(_chunked([raw[:7], raw[7:]], "deflate"), max_bytes=10_000).get(
        "https://h.test/a"
    )
    assert out.body == payload


def test_invalid_deflate_releases_the_pacing_lock(tmp_path, monkeypatch):
    from nzstats.sources.fetcher import FilePacer

    _DecoderBudget(monkeypatch, limit=2)

    pacer = FilePacer(tmp_path / "pace", 0.0, sleep=lambda s: None)
    client = httpx.Client(transport=httpx.MockTransport(_streaming([b"\x07\x00"], "deflate")))
    fetcher = Fetcher(client, sleep=lambda s: None, clock=lambda: 0.0, pacer=pacer, max_bytes=1000)
    with pytest.raises(IngestError, match="undecodable"):
        fetcher.get("https://h.test/a")
    # Nothing still holds the cross-process lock: a non-blocking exclusive flock succeeds at once.
    fd = os.open(tmp_path / "pace", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def _oversized(status, headers=None, pulled=None):
    class Huge(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(1000):
                if pulled is not None:
                    pulled.append(i)
                yield b"y" * 1024

    def handler(request):
        return httpx.Response(
            status,
            stream=Huge(),
            headers={"content-length": "999999999", **(headers or {})},
        )

    return handler


def test_oversized_403_is_still_classified_as_a_block_without_reading_the_body():
    pulled: list[int] = []
    f = _fetcher(_oversized(403, pulled=pulled), max_bytes=1000)
    with pytest.raises(IngestError) as exc:
        f.get("https://h.test/a")
    assert exc.value.error_class is ErrorClass.BLOCKED
    assert pulled == []
    with pytest.raises(IngestError) as again:  # the block put the fetcher into its cooldown
        f.get("https://h.test/b")
    assert again.value.error_class is ErrorClass.BLOCKED
    assert "cooling down" in str(again.value)


def test_oversized_403_without_a_declared_length_stops_reading_and_still_blocks():
    pulled: list[int] = []

    class Huge(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(1000):
                pulled.append(i)
                yield b"y" * 1024

    f = _fetcher(lambda r: httpx.Response(403, stream=Huge()), max_bytes=4096)
    with pytest.raises(IngestError) as exc:
        f.get("https://h.test/a")
    assert exc.value.error_class is ErrorClass.BLOCKED
    assert len(pulled) < 10


def test_oversized_429_honours_retry_after_instead_of_reporting_a_size_error():
    calls = []
    slept = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return _oversized(429, {"retry-after": "5"})(request)
        return httpx.Response(200, content=b"ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    f = Fetcher(client, sleep=slept.append, clock=lambda: 0.0, max_bytes=1000)
    assert f.get("https://h.test/a").body == b"ok"
    assert len(calls) == 2
    assert 5 in slept or any(s >= 5 for s in slept)


def test_oversized_503_is_retried_not_reported_as_too_large():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return _oversized(503)(request)
        return httpx.Response(200, content=b"ok")

    assert _fetcher(handler, max_bytes=1000).get("https://h.test/a").body == b"ok"


def test_oversized_404_is_not_found_and_oversized_success_is_still_refused():
    with pytest.raises(IngestError) as nf:
        _fetcher(_oversized(404), max_bytes=1000).get("https://h.test/a")
    assert nf.value.error_class is ErrorClass.NOT_FOUND
    pulled: list[int] = []
    with pytest.raises(IngestError, match="larger than") as big:
        _fetcher(_oversized(200, pulled=pulled), max_bytes=1000).get("https://h.test/a")
    assert big.value.error_class is ErrorClass.UNEXPECTED
    assert pulled == []


def test_an_oversized_redirect_body_is_still_refused_not_turned_into_an_empty_success():
    handler = _oversized(302, {"location": "/elsewhere"})
    with pytest.raises(IngestError, match="larger than"):
        _fetcher(handler, max_bytes=1000).get("https://h.test/a")


_RAW_PAYLOAD = b"hello " * 10
_RAW_COMP = zlib.compressobj(wbits=-15)
_RAW_BLOB = _RAW_COMP.compress(_RAW_PAYLOAD) + _RAW_COMP.flush()


@pytest.mark.parametrize("split", range(1, len(_RAW_BLOB)))
def test_raw_deflate_decodes_whatever_the_chunk_boundaries(split):
    payload, raw = _RAW_PAYLOAD, _RAW_BLOB
    out = _fetcher(_chunked([raw[:split], raw[split:]], "deflate"), max_bytes=10_000).get(
        "https://h.test/a"
    )
    assert out.body == payload


def test_raw_deflate_delivered_one_byte_at_a_time_decodes():
    payload = b"byte at a time " * 20
    comp = zlib.compressobj(wbits=-15)
    raw = comp.compress(payload) + comp.flush()
    chunks = [raw[i : i + 1] for i in range(len(raw))]
    out = _fetcher(_chunked(chunks, "deflate"), max_bytes=10_000).get("https://h.test/a")
    assert out.body == payload


@pytest.mark.parametrize("split", range(1, 12))
def test_zlib_deflate_decodes_whatever_the_chunk_boundaries(split, monkeypatch):
    budget = _DecoderBudget(monkeypatch, limit=1)  # a valid zlib stream never needs the fallback
    payload = b"zlib split " * 20
    blob = zlib.compress(payload)
    out = _fetcher(_chunked([blob[:split], blob[split:]], "deflate"), max_bytes=10_000).get(
        "https://h.test/a"
    )
    assert out.body == payload and budget.made == 1


@pytest.mark.parametrize("split", range(1, 4))
def test_invalid_deflate_split_across_chunks_still_fails_after_one_fallback(monkeypatch, split):
    budget = _DecoderBudget(monkeypatch, limit=2)
    junk = b"\x07\x00\xff\xff\xff"
    with pytest.raises(IngestError, match="undecodable|incomplete"):
        _fetcher(_chunked([junk[:split], junk[split:]], "deflate"), max_bytes=10_000).get(
            "https://h.test/a"
        )
    assert budget.made <= 2


def test_a_valid_raw_prefix_followed_by_junk_is_refused_once(monkeypatch):
    budget = _DecoderBudget(monkeypatch, limit=2)
    comp = zlib.compressobj(wbits=-15)
    raw = comp.compress(b"x" * 50) + comp.flush()
    with pytest.raises(IngestError):
        _fetcher(_chunked([raw[:1], b"\xff" * 8], "deflate"), max_bytes=10_000).get(
            "https://h.test/a"
        )
    assert budget.made <= 2
