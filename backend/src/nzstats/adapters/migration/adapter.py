from __future__ import annotations

from collections.abc import Mapping

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.adapters.migration.parse import (
    find_rolling_chart,
    parse_age_sex_csv,
    parse_citizenship_country_csv,
    parse_wide_chart,
    with_rolling_status,
)
from nzstats.domain import ErrorClass, IngestError, Point
from nzstats.sources.release_page import ReleasePage
from nzstats.validate.rules import validate_migration

LAYOUT_VERSION = "migration-csv-v1"


class MigrationAdapter:
    series_slug = "international-migration"
    required_downloads = ("age_sex", "citizenship_visa_country")
    previous_keys = ("mig.m.arrivals", "mig.m.departures", "mig.m.net")

    def __init__(self, country_window_months: int = 36) -> None:
        self._window = country_window_months

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle:
        monthly = parse_age_sex_csv(files["age_sex"])
        places = parse_citizenship_country_csv(
            files["citizenship_visa_country"], country_window=self._window
        )
        net = next((p for p in monthly if p.definition.key == "mig.m.net"), None)
        if net is None:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "age/sex csv has no Net series")
        status = {o.period: o.status for o in net.observations}
        rolling: list[ParsedSeries] = []
        # (labels, required): Stats NZ omitted the citizenship chart from the September 2025 page, so
        # only the direction chart is mandatory; a missing citizenship chart becomes a warning.
        for labels, required in ((S.G1_LABELS, True), (S.G3_LABELS, False)):
            chart = find_rolling_chart(page.charts, labels)
            if chart is None:
                if required:
                    raise IngestError(
                        ErrorClass.LAYOUT_CHANGED,
                        f"release page has no year-ended chart with series {sorted(labels)}",
                    )
                continue
            rolling += [with_rolling_status(p, status) for p in parse_wide_chart(chart.csv, labels)]
        return ParsedBundle(LAYOUT_VERSION, tuple(monthly + places + rolling))

    def validate(
        self,
        bundle: ParsedBundle,
        *,
        reference_period: str | None,
        previous: Mapping[str, Mapping[str, Point]],
    ) -> list[Finding]:
        return validate_migration(bundle, reference_period=reference_period, previous=previous)
