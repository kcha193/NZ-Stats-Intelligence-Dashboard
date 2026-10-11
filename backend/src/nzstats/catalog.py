"""Editorial metadata: which category and importance a Stats NZ series belongs to.

Importance is an editorial choice made for this dashboard (not a Stats NZ field); it drives the
calendar's importance filter. Unknown series default to Other / low.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryInfo:
    category: str
    importance: str  # "high" | "medium" | "low"


_CATALOG: dict[str, CategoryInfo] = {
    "international-migration": CategoryInfo("Migration", "high"),
    "international-travel": CategoryInfo("Tourism and travel", "medium"),
    "national-population-estimates": CategoryInfo("Population", "high"),
    "subnational-population-estimates": CategoryInfo("Population", "medium"),
    "births-and-deaths": CategoryInfo("Population", "medium"),
    "consumers-price-index": CategoryInfo("Prices and inflation", "high"),
    "selected-price-indexes": CategoryInfo("Prices and inflation", "medium"),
    "household-living-costs-price-indexes": CategoryInfo("Prices and inflation", "medium"),
    "business-price-indexes": CategoryInfo("Prices and inflation", "medium"),
    "labour-market-statistics": CategoryInfo("Labour market", "high"),
    "employment-indicators": CategoryInfo("Labour market", "medium"),
    "household-labour-force-survey-estimated-working-age-population": CategoryInfo(
        "Labour market", "low"
    ),
    "gross-domestic-product": CategoryInfo("Economic growth", "high"),
    "building-consents-issued": CategoryInfo("Housing and building", "high"),
    "value-of-building-work-put-in-place": CategoryInfo("Housing and building", "medium"),
    "dwelling-and-household-estimates": CategoryInfo("Housing and building", "low"),
    "retail-trade-survey": CategoryInfo("Retail", "high"),
    "electronic-card-transactions": CategoryInfo("Retail", "medium"),
    "overseas-merchandise-trade": CategoryInfo("Trade", "medium"),
    "international-trade": CategoryInfo("Trade", "medium"),
    "balance-of-payments-and-international-investment-position": CategoryInfo("Trade", "medium"),
}
_DEFAULT = CategoryInfo("Other", "low")

# Categories shown as inactive on the overview until a verified source is wired in (Phase 2).
INACTIVE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Prices and inflation", "Planned for Phase 2: CPI release files are being verified."),
    ("Labour market", "Planned for Phase 2."),
    ("Economic growth", "Planned for Phase 2."),
    ("Housing and building", "Planned for Phase 2."),
    ("Retail", "Planned for Phase 2."),
    ("Trade", "Planned for Phase 2."),
    ("Population", "Planned for Phase 2."),
)


def category_for(series_slug: str) -> CategoryInfo:
    return _CATALOG.get(series_slug, _DEFAULT)
