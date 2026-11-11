"""The normalized bank forecast (Phase 4AE): one verified claim, wrapped with what the bank layer derives from it.

Nothing here is computed by a model or converted: the raw value is kept as reported, `conversions` stays empty
until a documented conversion exists, and a zero or negative value is a value (never "missing").

`compare.py` groups forecasts by a statistical basis in which seasonal-adjustment wording is deliberately ignored,
so the adjustment is derived here, from fixed phrases in the claim's label and evidence quote, and the bank
analytics keep differently adjusted figures apart (`bank_analytics`). The wrapped `ForecastOut` is the existing
internal type the comparison, history and consensus functions already accept; no public model is extended.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nzstats.research.api_models import ForecastOut
from nzstats.research.banks import ReportKind
from nzstats.research.compare import basis_of

Adjustment = Literal["seasonally_adjusted", "unadjusted", "not_stated"]

_UNADJUSTED = re.compile(
    r"\bnon[- ]?seasonally[- ]adjusted\b|\bun-?adjusted\b|\bnsa\b|\bactual (?:values|series)\b",
    re.IGNORECASE,
)
_ADJUSTED = re.compile(r"\bseasonally[- ]adjusted\b|\bs\.a\.?(?=\W|$)|\bsa\b", re.IGNORECASE)


def _stated(text: str) -> set[Adjustment]:
    found: set[Adjustment] = set()
    if _UNADJUSTED.search(text):
        found.add("unadjusted")
    # "non-seasonally adjusted" contains "seasonally adjusted": only count the latter outside the former.
    if _ADJUSTED.search(_UNADJUSTED.sub(" ", text)):
        found.add("seasonally_adjusted")
    return found


def derive_adjustment(label: str, quote: str) -> Adjustment:
    """The adjustment the label and quote state. Silence, or any disagreement, is `not_stated`."""
    found = _stated(label) | _stated(quote)
    if len(found) == 1:
        return next(iter(found))
    return "not_stated"


def states_adjustment(text: str) -> bool:
    """Whether the text says anything about seasonal adjustment (even if it contradicts itself)."""
    return bool(_stated(text))


def derive_geography(indicator: str, label: str, horizon: str, unit: str | None) -> str:
    """New Zealand unless the comparison basis carries a part-of-series word (a region), shown title-cased."""
    basis = basis_of(indicator, label, horizon, unit)
    if basis and ":" in basis:
        return basis.split(":", 1)[1].replace("-", " ").title()
    return "New Zealand"


class NormalizedForecast(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    forecast: ForecastOut
    institution_key: str
    document_version_id: int
    claim_path: str
    report_kind: ReportKind
    forecast_author: str | None
    geography: str
    measure: str
    adjustment: Adjustment
    extraction_method: Literal["llm_verified"] = "llm_verified"
    verifier_version: str
    raw_value: float | None
    conversions: tuple[str, ...] = ()
