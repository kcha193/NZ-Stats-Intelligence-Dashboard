"""Parse the JSON that Stats NZ release pages embed (data-value attributes)."""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import parse_akl_naive
from nzstats.domain import ErrorClass, IngestError

log = logging.getLogger(__name__)

_DATA_VALUE = re.compile(r'data-value="([^"]+)"')
_ASSET = re.compile(r"/assets/Uploads/[^\"\\\s]+?\.(?:csv|xlsx|zip)")


@dataclass(frozen=True)
class Chart:
    title: str
    csv: str


@dataclass(frozen=True)
class ReleasePage:
    title: str
    published_at: datetime
    headline: str | None
    charts: tuple[Chart, ...]
    download_urls: tuple[str, ...]

    def chart_starting_with(self, prefix: str) -> Chart | None:
        return next((c for c in self.charts if c.title.startswith(prefix)), None)


def _find_page_object(html_text: str) -> dict:
    for match in _DATA_VALUE.finditer(html_text):
        raw = html.unescape(match.group(1))
        if not raw.startswith("{") or "PageBlocks" not in raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "PageBlocks" in obj:
            return obj
    raise IngestError(ErrorClass.LAYOUT_CHANGED, "release page has no embedded data object")


def parse_release_page(html_text: str, base_url: str) -> ReleasePage:
    obj = _find_page_object(html_text)
    try:
        term = obj.get("DateTaxonomyTerm") or {}
        published = parse_akl_naive(term.get("PublicationDate") or obj["PageDate"])
        charts = []
        for block in obj["PageBlocks"]:
            if block.get("ClassName") != "GraphTableBlock":
                continue
            for series in block.get("SeriesData") or []:
                csv_text = (series.get("GraphCsvData") or "").lstrip("﻿")
                if csv_text:
                    charts.append(Chart(series.get("Title") or block.get("Title", ""), csv_text))
        urls = list(dict.fromkeys(_ASSET.findall(json.dumps(obj).replace("\\/", "/"))))
        return ReleasePage(
            title=obj["Title"],
            published_at=published,
            headline=(obj.get("MetaDescription") or "").strip() or None,
            charts=tuple(charts),
            download_urls=tuple(base_url + u for u in urls),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("release page malformed: %r", exc)
        raise IngestError(
            ErrorClass.LAYOUT_CHANGED, f"release page malformed ({type(exc).__name__})"
        ) from exc


def classify_download(url: str) -> str | None:
    name = url.rsplit("/", 1)[-1].lower()
    if name.startswith("electronic-card-transactions-") and name.endswith(".zip"):
        return "ect_zip"
    if name.endswith(".xlsx"):
        return "workbook"
    if not name.endswith(".csv"):
        return None
    if re.search(r"age.*sex", name):
        return "age_sex"
    if re.search(r"citizenship.*visa.*country", name):
        return "citizenship_visa_country"
    return None
