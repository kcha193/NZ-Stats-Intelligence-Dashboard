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
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nzstats.research.api_models import ForecastOut
from nzstats.research.banks import ReportKind

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


def canonical_label(label: str, adjustment: Adjustment) -> str:
    """The label without its adjustment wording, once the adjustment is settled (the same measure wherever it is stated).

    `compare.basis_of` reads "unadjusted" as part of the CPI basis and rejects "non-seasonally adjusted" as ambiguous, so
    a bank that says it in the label and a bank that says it in the evidence would otherwise be different measures. The
    adjustment lives in `NormalizedForecast.adjustment`, the stated label in `measure`, the wording in the evidence. A label
    that disagrees with its evidence (`not_stated`) is left as stated, and so is a label that is only that wording.
    """
    if adjustment == "not_stated":
        return label
    text = _ADJUSTED.sub(" ", _UNADJUSTED.sub(" ", label))
    text = re.sub(r"\(\s*\)", " ", text)  # a bracket left empty
    text = re.sub(r"\s+([,;])", r"\1", text)
    text = re.sub(r"([,;])(\s*[,;])+", r"\1", text)  # a comma left behind a removed phrase
    text = re.sub(r"\s+", " ", text).strip(" ,;-–—")
    return text or label


def states_adjustment(text: str) -> bool:
    """Whether the text says anything about seasonal adjustment (even if it contradicts itself)."""
    return bool(_stated(text))


def adjustment_conflicts(label: str, quote: str) -> bool:
    """Whether the label and quote state the adjustment both ways (so `not_stated` is a contradiction, not silence)."""
    return len(_stated(label) | _stated(quote)) > 1


# New Zealand regions, main centres and the two islands, as a bank names a part of the country. Nothing else is a place:
# `compare`'s basis qualifiers also carry measure words (production, unadjusted, Crown) and populations (youth, women).
_PLACES = {
    name.lower(): name
    for name in (
        "Northland", "Auckland", "Waikato", "Bay of Plenty", "Gisborne", "Hawke's Bay", "Taranaki", "Manawatu",
        "Whanganui", "Wellington", "Tasman", "Nelson", "Marlborough", "West Coast", "Canterbury", "Otago",
        "Southland", "Hamilton", "Tauranga", "Rotorua", "Napier", "Hastings", "Palmerston North", "Christchurch",
        "Dunedin", "Queenstown", "Invercargill", "North Island", "South Island",
    )
}  # fmt: skip
_PLACE = re.compile(
    r"(?<![\w'])("
    + "|".join(sorted((re.escape(p) for p in _PLACES), key=len, reverse=True))
    + r"|hawkes bay)(?![\w'])"
)


def derive_geography(indicator: str, label: str, horizon: str, unit: str | None) -> str:
    """The New Zealand places the label names (in order, title-cased), else New Zealand.

    Only a fixed list of places counts: a basis qualifier such as "unadjusted", "production" or "youth" is not geography.
    """
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", label) if not unicodedata.combining(c)
    ).lower()
    found: list[str] = []
    for m in _PLACE.finditer(folded.replace("’", "'")):
        name = _PLACES.get(m[1], "Hawke's Bay")  # "hawkes bay" is the only spelling not in the list
        if name not in found:
            found.append(name)
    return ", ".join(found) if found else "New Zealand"


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
    # The label and evidence state the adjustment both ways: `not_stated` here is a contradiction, not silence.
    adjustment_conflict: bool = False
    extraction_method: Literal["llm_verified"] = "llm_verified"
    verifier_version: str
    raw_value: float | None
    conversions: tuple[str, ...] = ()
