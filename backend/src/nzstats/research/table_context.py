"""Shared, deterministic semantic checks for interpreted and persisted table evidence.

A label is never rewritten to smuggle context into a measurement identity. Unsupported
scope/aggregation and contradictory statements are refused before either consumer uses
it. Fixed phrase recognition is deliberately bounded; this is not a language model.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from nzstats.research.bank_forecast import adjustment_conflicts, derive_geography
from nzstats.research.compare import _ANNUAL, _ANNUAL_AVERAGE, _QUARTERLY, _THROUGH_YEAR
from nzstats.research.table_parse import unit_of_text

POPULATION = re.compile(
    r"\b(?:youth|young|teenagers?|children|men|women|male|female|māori|maori|"
    r"pacific peoples?|aged|age group|ethnic(?:ity)?|migrants?|immigrants?)\b",
    re.IGNORECASE,
)
FOREIGN = re.compile(
    r"\b(?:australia(?:n)?|china|chinese|united states|u\.?s\.?a\.?|american|"
    r"united kingdom|britain|british|euro(?:zone| area)|japan(?:ese)?)\b",
    re.IGNORECASE,
)
SCENARIO = re.compile(
    r"\b(?:scenarios?|downside|upside|alternative|stress(?:ed)?|sensitivity|illustrative|what[- ]if|risk case)\b",
    re.IGNORECASE,
)
FOOTNOTE = re.compile(r"[*†‡¹²³⁴⁵⁶⁷⁸⁹]|\(\d+\)|\[\d+\]")
_OBSERVATION = re.compile(r"\b(?:estimates?|estimated|provisional)\b", re.IGNORECASE)
_QUALIFIED = re.compile(
    r"\b(?:excluding|excludes?|only|per capita|core|trimmed|weighted median)\b", re.IGNORECASE
)
_TIMING = re.compile(r"\baverage\b|\bend[- ]of[- ](?:period|quarter|year)\b", re.IGNORECASE)
# A publication's own name ("Quarterly Economic Overview") states how often it is
# issued, not what any figure inside it measures, so it never qualifies a row.
_PUBLICATION = re.compile(
    r"\b(?:(?:weekly|monthly|quarterly|annual)\s+)?(?:economic\s+|markets?\s+)?"
    r"(?:outlook|overview|update|review|report|bulletin|commentary)\b",
    re.IGNORECASE,
)


# Context outside the row may only add a supported dimension or neutral table
# wording. Unknown modifiers are refused rather than dropped from the identity.
_NEUTRAL = frozenset(
    """
    table figure chart exhibit forecasts forecast forecasting projections projection projected
    actual actuals historical outturn central baseline percent percentage per cent points basis
    bps bp ppt ppts pp change changes growth annual quarterly year years to ended ending end
    quarter calendar month months yr yrs pa y e ye yoy qoq yyy qqq seasonally adjusted non unadjusted
    nsa sa all figures are is in the of for and or note notes source sources context
    synthetic fixture revised economic economy outlook report research bank forecasts
    key main summary selected indicators overview update review bulletin commentary markets
    example a b c nz new zealand statistics stats treasury rbnz reserve imf oecd world
    consensus bloomberg reuters market pricing limited ltd group economics anz asb bnz
    westpac kiwibank cpi inflation consumers consumer price prices gdp gross domestic
    product unemployment rate ocr official cash
    jan january feb february mar march apr april may jun june jul july aug august
    sep sept september oct october nov november dec december f q
""".split()
)


def _unknown_context(text: str, publisher_names: Sequence[str]) -> bool:
    if re.match(r"^sources?\s*[:\-]", text, re.IGNORECASE):
        return False  # ownership is decided separately from source names
    text = re.sub(r"\.pdf$", " ", text, flags=re.IGNORECASE)
    for name in publisher_names:
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", text, flags=re.IGNORECASE)
    return any(word.lower() not in _NEUTRAL for word in re.findall(r"[^\W\d_]+", text))


def unmarked_notes(notes: Sequence[str]) -> tuple[str, ...]:
    """Marker-specific notes do not qualify unmarked cells. Marked cells are refused separately."""
    return tuple(n for n in notes if not FOOTNOTE.match(n.strip()))


def evidence_texts(evidence: Mapping[str, Any]) -> tuple[str, ...]:
    """The same authoritative context in normalization and reconciliation, in source order."""
    return (
        evidence.get("caption") or "",
        *unmarked_notes(evidence.get("notes", [])),
        *evidence.get("header_texts", []),
        *evidence.get("unit_texts", []),
    )


def context_rejection(
    label: str,
    texts: Sequence[str],
    *,
    publisher_names: Sequence[str] = (),
    document_title: str = "",
    kind: str = "forecast",
) -> str | None:
    """Return a fixed refusal code when context cannot safely use the row's identity."""
    document_title = _PUBLICATION.sub(" ", document_title)
    all_texts = (label, document_title, *texts)
    text = " ".join(all_texts)
    contextual = (document_title, *texts)
    if FOREIGN.search(text) or derive_geography("", text, "", None) != "New Zealand":
        return "unsupported_geography"
    if POPULATION.search(text) or _QUALIFIED.search(text):
        return "unsupported_scope"
    if SCENARIO.search(text):
        return "scenario_context"
    if FOOTNOTE.search(text):
        return "footnote_unresolved"
    if _OBSERVATION.search(text):
        return "estimate_or_provisional"
    if kind == "forecast" and re.search(
        r"\b(?:actuals?|historical|outturn)\b", text, re.IGNORECASE
    ):
        return "actual_or_forecast_unstated"
    rate = bool(re.search(r"\bocr\b|official cash rate|unemployment", label, re.IGNORECASE))
    if rate and re.search(r"\b(?:changes?|growth)\b", text, re.IGNORECASE):
        return "unsupported_measure"
    # The row's own label is the only place an annual-average basis can enter the
    # identity (`basis_of` reads the label). Any other "average" in the label is
    # unsupported; annual-average context the label does not state is refused.
    stated_average = bool(_ANNUAL_AVERAGE.search(label))
    if not rate and re.search(r"\baverage\b", label, re.IGNORECASE) and not stated_average:
        return "period_basis_unstated"
    # "Annual average annual inflation" (an average of annual rates) is not the annual-average change.
    if stated_average and re.search(
        r"\b(?:annual|average)\b", _ANNUAL_AVERAGE.sub(" ", label), re.IGNORECASE
    ):
        return "period_basis_unstated"
    annual = bool(_ANNUAL.search(label) or _THROUGH_YEAR.search(label))
    quarterly = bool(_QUARTERLY.search(label))
    average = stated_average or any(_ANNUAL_AVERAGE.search(t) for t in contextual)
    through_year = bool(_THROUGH_YEAR.search(text))
    if (bool(_QUARTERLY.search(text)) and (bool(_ANNUAL.search(text)) or through_year)) or (
        average and through_year
    ):
        return "contradictory_period"
    if stated_average:  # context may repeat the label's basis, never add another timing
        contextual = tuple(_ANNUAL_AVERAGE.sub(" ", t) for t in contextual)
    if (average and not stated_average) or any(_TIMING.search(t) for t in contextual):
        return "period_basis_unstated"
    if any(_ANNUAL.search(t) or _THROUGH_YEAR.search(t) for t in contextual) and not annual:
        return "contradictory_period"
    if any(_QUARTERLY.search(t) for t in contextual) and not quarterly:
        return "contradictory_period"
    if adjustment_conflicts(label, " ".join(contextual)):
        return "contradictory_adjustment"
    _, code = unit_of_text(*all_texts)
    if code:
        return code
    # `contextual` has had the label's own, already validated basis removed.
    if any(t and _unknown_context(t, publisher_names) for t in contextual):
        return "unsupported_context"
    return None


def stored_context_rejection(label: str, evidence: Mapping[str, Any]) -> str | None:
    """Re-evaluate the identical evidence contract for both stored consumers."""
    return context_rejection(
        label,
        evidence_texts(evidence),
        publisher_names=evidence.get("publisher_names", ()),
        document_title=evidence.get("document_title") or "",
    )
