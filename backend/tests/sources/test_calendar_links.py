"""Page links come from upstream JSON and must never move our requests to another host."""

import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.calendar import parse_release_month

BASE = "https://www.stats.govt.nz"


def _payload(page_link: str) -> dict:
    return {
        "items": {
            "published": [
                {
                    "ID": "1",
                    "PageLink": page_link,
                    "MetaDescription": "x" * 30,
                    "DateTaxonomyTerm": {
                        "DisplayName": "International migration: July 2026",
                        "PublicationDate": "2026-09-14 10:45:00",
                    },
                }
            ],
            "upcoming": [],
        }
    }


@pytest.mark.parametrize(
    "page_link",
    ["@evil.example/x", "//evil.example/x", "https://evil.example/x", "\\\\evil.example", "", "x"],
)
def test_page_links_that_leave_the_site_are_rejected(page_link) -> None:
    with pytest.raises(IngestError) as e:
        parse_release_month(_payload(page_link), BASE)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_page_link_on_the_same_site_is_kept_verbatim() -> None:
    link = "/information-releases/international-migration-july-2026/"
    (ref,) = parse_release_month(_payload(link), BASE)
    assert ref.page_url == f"{BASE}{link}"
