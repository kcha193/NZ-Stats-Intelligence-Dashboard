import json
from datetime import UTC

import httpx
import pytest

from nzstats.clock import to_utc_iso
from nzstats.domain import ErrorClass, IngestError, ReleaseStatus
from nzstats.sources.calendar import (
    events_to_refs,
    fetch_calendar,
    fetch_release_month,
    make_release_key,
    parse_ics,
    parse_release_month,
    parse_title,
)
from nzstats.sources.fetcher import Fetcher
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.mark.parametrize(
    ("title", "slug", "label", "period"),
    [
        (
            "International migration: August 2026",
            "international-migration",
            "August 2026",
            "2026-08",
        ),
        (
            "Gross domestic product: June 2026 quarter",
            "gross-domestic-product",
            "June 2026 quarter",
            "2026-06",
        ),
        (
            "Tatauranga umanga Māori – Statistics on Māori businesses",
            "tatauranga-umanga-maori-statistics-on-maori-businesses",
            None,
            None,
        ),
        (
            "Consumers price index: September 2026 quarter",
            "consumers-price-index",
            "September 2026 quarter",
            "2026-09",
        ),
        (
            "Household labour force survey estimated working-age population: 2026",
            "household-labour-force-survey-estimated-working-age-population",
            "2026",
            None,
        ),
    ],
)
def test_parse_title(title, slug, label, period) -> None:
    p = parse_title(title)
    assert (p.series_slug, p.period_label, p.reference_period) == (slug, label, period)


def test_release_key_is_stable_and_case_insensitive() -> None:
    assert (
        make_release_key("International migration: August 2026")
        == "international-migration:august 2026"
    )
    assert make_release_key("International Migration:  August 2026 ") == make_release_key(
        "International migration: August 2026"
    )


def test_parse_ics_fixture() -> None:
    events = parse_ics(fixture_text("calendar_export_excerpt.ics"))
    assert len(events) == 12
    assert any(e.summary.startswith("International migration:") for e in events)
    assert all(e.start.tzinfo is not None and e.uid for e in events)


def test_parse_ics_converts_auckland_time_across_dst() -> None:
    # Real event shape from the live calendar (14 Oct 2026 is NZDT, UTC+13).
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:8364@https://www.stats.govt.nz/\r\n"
        "DTSTAMP;TZID=Pacific/Auckland:19700101T120000\r\n"
        "DTSTART;TZID=Pacific/Auckland:20261014T104500\r\n"
        "DTEND;TZID=Pacific/Auckland:20261014T104500\r\n"
        "SUMMARY:International migration: August 2026\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    (first,) = parse_ics(text)
    assert first.summary == "International migration: August 2026"
    assert to_utc_iso(first.start) == "2026-10-13T21:45:00Z"
    assert first.uid.startswith("8364@")


def test_parse_ics_handles_folding_escapes_and_utc() -> None:
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1@x\r\n"
        "DTSTART:20261014T214500Z\r\nSUMMARY:Alcohol available for\r\n  consumption\\, "
        "quarterly: June 2026\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:2@x\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = parse_ics(text)
    assert len(events) == 1  # the event without SUMMARY/DTSTART is skipped
    assert events[0].summary == "Alcohol available for consumption, quarterly: June 2026"
    assert events[0].start.astimezone(UTC).hour == 21


def test_events_to_refs_are_scheduled() -> None:
    refs = events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
    assert {r.status for r in refs} == {ReleaseStatus.SCHEDULED}
    mig = next(r for r in refs if r.series_slug == "international-migration")
    assert mig.release_key == f"international-migration:{mig.period_label.lower()}"
    assert mig.reference_period and len(mig.reference_period) == 7


def test_parse_release_month_published() -> None:
    sept = json.loads(fixture_text("release_month_2026-09.json"))
    published = [r for r in parse_release_month(sept, BASE) if r.status is ReleaseStatus.PUBLISHED]
    assert published, "fixture should contain published releases"
    p = published[0]
    assert p.page_url.startswith(f"{BASE}/information-releases/")
    assert p.headline and len(p.headline) > 20
    assert p.published_at.tzinfo is not None


def test_parse_release_month_upcoming_shape() -> None:
    payload = {
        "items": {
            "published": [],
            "upcoming": [
                {
                    "DisplayName": "International migration: August 2026",
                    "PublicationDate": "2026-10-14 10:45:00",
                }
            ],
        }
    }
    (ref,) = parse_release_month(payload, BASE)
    assert ref.status is ReleaseStatus.SCHEDULED and ref.page_url is None
    assert to_utc_iso(ref.published_at) == "2026-10-13T21:45:00Z"


def test_real_october_fixture_parses() -> None:
    refs = parse_release_month(json.loads(fixture_text("release_month_2026-10.json")), BASE)
    assert {r.status for r in refs} <= {ReleaseStatus.PUBLISHED, ReleaseStatus.SCHEDULED}
    assert all(r.published_at.tzinfo is not None for r in refs)


def test_parse_release_month_rejects_unexpected_shape() -> None:
    with pytest.raises(IngestError) as e:
        parse_release_month({"nope": 1}, BASE)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def _fetcher(handler) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, sleep=lambda s: None, clock=lambda: 0.0)


def test_fetch_calendar_requests_ics_and_parses() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(
            200,
            text=fixture_text("calendar_export_excerpt.ics"),
            headers={"content-type": 'text/calendar; name="release-calendar.ics"'},
        )

    refs = fetch_calendar(_fetcher(handler), BASE, "/release-calendar/calendar-export/")
    assert seen == [f"{BASE}/release-calendar/calendar-export/"] and len(refs) == 12


def test_fetch_release_month_formats_path() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(
            200,
            text=fixture_text("release_month_2026-09.json"),
            headers={"content-type": "application/json"},
        )

    refs = fetch_release_month(
        _fetcher(handler), BASE, "/api/v1/releaseCalendarMonth/{month}", "2026-09"
    )
    assert seen == [f"{BASE}/api/v1/releaseCalendarMonth/2026-09"] and refs


def test_malformed_month_entry_error_does_not_echo_upstream_text(caplog) -> None:
    payload = {
        "items": {
            "published": [
                {
                    "DateTaxonomyTerm": {
                        "DisplayName": "X: July 2026",
                        "PublicationDate": "UPSTREAM-SECRET",
                    },
                    "PageLink": "/information-releases/x/",
                }
            ]
        }
    }
    with pytest.raises(IngestError) as e:
        parse_release_month(payload, "https://www.stats.govt.nz")
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED
    assert "UPSTREAM-SECRET" not in str(e.value) and "ValueError" in str(e.value)
    assert "UPSTREAM-SECRET" in caplog.text


def test_page_link_rejection_does_not_echo_the_link() -> None:
    payload = {
        "items": {
            "published": [
                {
                    "DateTaxonomyTerm": {
                        "DisplayName": "X: July 2026",
                        "PublicationDate": "2026-07-14T10:45:00",
                    },
                    "PageLink": "@evil.example/x",
                }
            ]
        }
    }
    with pytest.raises(IngestError) as e:
        parse_release_month(payload, "https://www.stats.govt.nz")
    assert "evil.example" not in str(e.value)


def test_calendar_with_one_malformed_event_is_a_layout_failure_not_a_healthy_partial() -> None:
    """Review #4267769129: dropping one VEVENT must not leave the ICS source reported healthy."""
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1@x\r\nDTSTART:20261014T214500Z\r\n"
        "SUMMARY:International migration: August 2026\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:2@x\r\nSUMMARY:Gross domestic product: June 2026 quarter\r\n"
        "DTSTART:not-a-date\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=text, headers={"content-type": "text/calendar"})

    with pytest.raises(IngestError) as exc:
        fetch_calendar(_fetcher(handler), BASE, "/release-calendar/calendar-export/")
    assert exc.value.error_class == ErrorClass.LAYOUT_CHANGED
