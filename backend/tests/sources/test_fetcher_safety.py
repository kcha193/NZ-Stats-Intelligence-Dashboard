"""Durable pacing reserves a request before sending, and never retries before Retry-After."""

import os
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import pytest

from nzstats.domain import ErrorClass, IngestError, RequestRefused
from nzstats.sources.fetcher import Fetcher, FilePacer
from tests.sources.test_fetcher import COOLDOWN, FakeTime


def _fetcher(path, wall, handler, **kwargs):
    return Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=wall.sleep,
        clock=wall.clock,
        now=lambda: datetime.fromtimestamp(wall.t, UTC),
        pacer=FilePacer(path, 10.0, sleep=wall.sleep, wall=wall.clock),
        **kwargs,
    )


def test_pre_request_save_failure_refuses_without_outbound_traffic(tmp_path, monkeypatch):
    calls = []
    wall = FakeTime()

    def disk_full(*args):
        raise OSError("private disk error")

    monkeypatch.setattr(os, "pwrite", disk_full)
    fetcher = _fetcher(tmp_path / "pace", wall, lambda r: (calls.append(1), httpx.Response(200))[1])
    with pytest.raises(RequestRefused) as caught:
        fetcher.get("https://h.test/a")
    assert caught.value.error_class is ErrorClass.NETWORK
    assert "private" not in str(caught.value)
    assert calls == []


def test_failed_completion_save_keeps_reservation_across_restart_then_recovers(
    tmp_path, monkeypatch
):
    path, wall, calls = tmp_path / "pace", FakeTime(), []
    real = os.pwrite
    writes = []

    def fail_second(fd, data, offset):
        writes.append(1)
        if len(writes) == 2:
            raise OSError("private disk error")
        return real(fd, data, offset)

    monkeypatch.setattr(os, "pwrite", fail_second)
    first = _fetcher(path, wall, lambda r: (calls.append("a"), httpx.Response(403))[1])
    with pytest.raises(IngestError) as caught:
        first.get("https://h.test/a")
    assert caught.value.error_class is ErrorClass.BLOCKED
    assert len(writes) == 2
    monkeypatch.setattr(os, "pwrite", real)
    second = _fetcher(path, wall, lambda r: (calls.append("b"), httpx.Response(200))[1])
    with pytest.raises(RequestRefused):
        second.get("https://h.test/b")
    assert calls == ["a"]
    wall.t += COOLDOWN
    assert second.get("https://h.test/c").status == 200
    assert calls == ["a", "b"]


def test_short_writes_are_completed_before_http_is_sent(tmp_path, monkeypatch):
    path, wall = tmp_path / "pace", FakeTime()
    real = os.pwrite
    monkeypatch.setattr(os, "pwrite", lambda fd, data, off: real(fd, data[:7], off))
    first = _fetcher(path, wall, lambda r: httpx.Response(403))
    with pytest.raises(IngestError):
        first.get("https://h.test/a")
    second = _fetcher(path, wall, lambda r: pytest.fail("cooldown must survive partial writes"))
    with pytest.raises(RequestRefused):
        second.get("https://h.test/b")


def test_fsync_failure_before_http_is_fail_safe(tmp_path, monkeypatch):
    wall = FakeTime()

    def cannot_sync(fd):
        raise OSError("private disk error")

    monkeypatch.setattr(os, "fsync", cannot_sync)
    fetcher = _fetcher(tmp_path / "pace", wall, lambda r: pytest.fail("reservation not durable"))
    with pytest.raises(RequestRefused):
        fetcher.get("https://h.test/a")


@pytest.mark.parametrize("header", ["35", "date"])
def test_retry_after_delays_the_retry_until_the_server_deadline(tmp_path, header):
    wall, calls = FakeTime(), []
    if header == "date":
        header = format_datetime(datetime.fromtimestamp(wall.t + 35, UTC), usegmt=True)

    def handler(request):
        calls.append(wall.t)
        return (
            httpx.Response(429, headers={"Retry-After": header})
            if len(calls) == 1
            else httpx.Response(200)
        )

    fetcher = _fetcher(tmp_path / "pace", wall, handler)
    assert fetcher.get("https://h.test/a").status == 200
    assert calls == [1000.0, 1035.0]


@pytest.mark.parametrize("header", ["3600", "date"])
def test_long_retry_after_returns_promptly_and_survives_restart(tmp_path, header):
    path, wall, calls = tmp_path / "pace", FakeTime(), []
    if header == "date":
        header = format_datetime(datetime.fromtimestamp(wall.t + 3600, UTC), usegmt=True)
    first = _fetcher(
        path,
        wall,
        lambda r: (calls.append("a"), httpx.Response(503, headers={"Retry-After": header}))[1],
    )
    with pytest.raises(IngestError) as caught:
        first.get("https://h.test/a")
    assert caught.value.error_class is ErrorClass.NETWORK
    assert wall.sleeps == [] and calls == ["a"]
    second = _fetcher(path, wall, lambda r: (calls.append("b"), httpx.Response(200))[1])
    with pytest.raises(RequestRefused):
        second.get("https://h.test/b")
    assert wall.sleeps == [] and calls == ["a"]
    wall.t += 3600
    assert second.get("https://h.test/c").status == 200
    assert calls == ["a", "b"]


@pytest.mark.parametrize("header", ["invalid", "-1", "nan", "inf", "1e999"])
def test_invalid_retry_after_falls_back_to_normal_pacing(tmp_path, header):
    wall, calls = FakeTime(), []

    def handler(request):
        calls.append(wall.t)
        return (
            httpx.Response(429, headers={"Retry-After": header})
            if len(calls) == 1
            else httpx.Response(200)
        )

    assert _fetcher(tmp_path / "pace", wall, handler).get("https://h.test/a").status == 200
    assert calls == [1000.0, 1010.0]


def test_nonempty_corrupt_state_stops_requests_once_then_recovers_at_a_fixed_deadline(tmp_path):
    path, wall, calls = tmp_path / "pace", FakeTime(), []
    path.write_bytes(b"\xffcorrupt")
    first = _fetcher(path, wall, lambda r: (calls.append(1), httpx.Response(200))[1])
    with pytest.raises(RequestRefused):
        first.get("https://h.test/a")
    wall.t += COOLDOWN - 1
    second = _fetcher(path, wall, lambda r: (calls.append(1), httpx.Response(200))[1])
    with pytest.raises(RequestRefused):
        second.get("https://h.test/b")
    assert calls == []
    wall.t += 1
    assert second.get("https://h.test/c").status == 200


def _child_retry_get(path, clock_value, queue):
    wall, calls = FakeTime(), []
    wall.t = clock_value
    fetcher = _fetcher(path, wall, lambda r: (calls.append(wall.t), httpx.Response(200))[1])
    try:
        fetcher.get("https://h.test/child")
        queue.put(("ok", calls, wall.sleeps))
    except IngestError as exc:
        queue.put((exc.error_class.value, calls, wall.sleeps))


@pytest.mark.parametrize("seconds", [35, 3600])
@pytest.mark.parametrize("date_header", [False, True])
def test_retry_after_is_shared_with_another_process(tmp_path, seconds, date_header):
    import multiprocessing

    path, wall = tmp_path / "pace", FakeTime()
    header = (
        format_datetime(datetime.fromtimestamp(wall.t + seconds, UTC), usegmt=True)
        if date_header
        else str(seconds)
    )
    first = _fetcher(
        path, wall, lambda r: httpx.Response(429, headers={"Retry-After": header}), max_retries=0
    )
    with pytest.raises(IngestError):
        first.get("https://h.test/a")
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    child = context.Process(target=_child_retry_get, args=(path, wall.t, queue))
    child.start()
    result = queue.get(timeout=30)
    child.join(timeout=30)
    assert child.exitcode == 0
    if seconds == 35:
        assert result == ("ok", [1035.0], [35.0])
    else:
        assert result == ("network", [], [])


@pytest.mark.parametrize("broken", ["string-deadline", "missing-fields"])
def test_invalid_journal_records_cannot_erase_pacing_history(tmp_path, broken):
    import json

    path, wall = tmp_path / "pace", FakeTime()
    state = {
        "version": 1,
        "last": "1000",
        "blocked_until": None,
        "retry_until": None,
        "pending": False,
    }
    if broken == "missing-fields":
        state = {"version": 1, "pending": False}
    path.write_text(json.dumps(state) + "\n")
    fetcher = _fetcher(path, wall, lambda r: pytest.fail("damaged history must recover safely"))
    with pytest.raises(RequestRefused):
        fetcher.get("https://h.test/a")


def test_new_pacing_file_directory_entry_is_synced_before_sending(tmp_path, monkeypatch):
    import stat

    real = os.fsync
    synced_directory = []

    def sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced_directory.append(True)
        real(fd)

    monkeypatch.setattr(os, "fsync", sync)
    wall = FakeTime()

    def handler(request):
        assert synced_directory, "a durable reservation also needs a durable directory entry"
        return httpx.Response(200)

    assert _fetcher(tmp_path / "pace", wall, handler).get("https://h.test/a").status == 200


@pytest.mark.parametrize("failure", ["torn-write", "fsync"])
def test_completion_failure_cannot_erase_the_block_for_another_process(
    tmp_path, monkeypatch, failure
):
    import multiprocessing

    path, wall = tmp_path / "pace", FakeTime()
    real_write, real_sync = os.pwrite, os.fsync
    writes, syncs = [], []

    def write(fd, data, offset):
        writes.append(1)
        if failure == "torn-write" and len(writes) == 2:
            return real_write(fd, data[:7], offset)
        if failure == "torn-write" and len(writes) == 3:
            raise OSError("private disk error")
        return real_write(fd, data, offset)

    def sync(fd):
        syncs.append(1)
        if failure == "fsync" and len(syncs) == 3:  # directory, reservation, completion
            raise OSError("private disk error")
        real_sync(fd)

    monkeypatch.setattr(os, "pwrite", write)
    monkeypatch.setattr(os, "fsync", sync)
    first = _fetcher(path, wall, lambda r: httpx.Response(403))
    with pytest.raises(IngestError) as caught:
        first.get("https://h.test/a")
    assert caught.value.error_class is ErrorClass.BLOCKED
    monkeypatch.setattr(os, "pwrite", real_write)
    monkeypatch.setattr(os, "fsync", real_sync)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    child = context.Process(target=_child_retry_get, args=(path, wall.t, queue))
    child.start()
    assert queue.get(timeout=30) == ("blocked", [], [])
    child.join(timeout=30)
    assert child.exitcode == 0


def test_a_large_pacing_journal_reads_a_bounded_tail_and_honours_its_latest_block(
    tmp_path, monkeypatch
):
    import json

    path, wall = tmp_path / "pace", FakeTime()
    record = {"version": 1, "last": 0, "blocked_until": None, "retry_until": None, "pending": False}
    old = json.dumps(record) + "\n"
    record["blocked_until"] = wall.t + COOLDOWN
    path.write_text(old * 3000 + json.dumps(record) + "\n")
    real = os.pread
    read_sizes = []

    def read(fd, count, offset):
        read_sizes.append(count)
        return real(fd, count, offset)

    monkeypatch.setattr(os, "pread", read)
    fetcher = _fetcher(path, wall, lambda r: pytest.fail("latest cooldown must be retained"))
    with pytest.raises(RequestRefused):
        fetcher.get("https://h.test/a")
    assert read_sizes and max(read_sizes) <= 64 * 1024


@pytest.mark.parametrize(
    "newer", [b'{"version":1,"blocked_until":"2800"}\n', b'{"version":1,"blocked_until":2800']
)
def test_newer_damaged_record_after_completed_history_requires_recovery(tmp_path, newer):
    import json

    path, wall, calls = tmp_path / "pace", FakeTime(), []
    completed = {
        "version": 1,
        "last": 0,
        "blocked_until": None,
        "retry_until": None,
        "pending": False,
    }
    path.write_bytes(json.dumps(completed).encode() + b"\n\n" + newer)
    fetcher = _fetcher(path, wall, lambda r: (calls.append(1), httpx.Response(200))[1])
    with pytest.raises(RequestRefused):
        fetcher.get("https://h.test/a")
    assert calls == []
    wall.t += COOLDOWN
    assert fetcher.get("https://h.test/b").status == 200


def test_blank_separators_after_completed_history_do_not_start_recovery(tmp_path):
    import json

    path, wall = tmp_path / "pace", FakeTime()
    completed = {
        "version": 1,
        "last": 0,
        "blocked_until": None,
        "retry_until": None,
        "pending": False,
    }
    path.write_text(json.dumps(completed) + "\n\n  \n\t\n")
    assert _fetcher(path, wall, lambda r: httpx.Response(200)).get("https://h.test/a").status == 200
    assert wall.sleeps == []


def test_older_partial_record_at_tail_window_start_does_not_damage_newest_valid_record(tmp_path):
    import json

    path, wall = tmp_path / "pace", FakeTime()
    completed = {
        "version": 1,
        "last": 0,
        "blocked_until": None,
        "retry_until": None,
        "pending": False,
    }
    record = json.dumps(completed) + "\n"
    path.write_text(record * 3000)
    assert path.stat().st_size > 64 * 1024
    assert path.stat().st_size % len(record) == 0
    assert (64 * 1024) % len(record) != 0  # the read window starts inside an older record
    assert _fetcher(path, wall, lambda r: httpx.Response(200)).get("https://h.test/a").status == 200
    assert wall.sleeps == []
