import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from nzstats.research import contract
from nzstats.research.contract import (
    DisabledProvider,
    EvidenceRef,
    ForecastClaim,
    ModelProvenance,
    OutlookSummary,
    ProviderDisabled,
    SectionText,
    SummaryRequest,
    build_request,
    parse_summary,
    verify_summary,
)

SECTIONS = {
    0: SectionText("The example economy is expected to grow 2.5% in the year to March 2027.", 1, 1),
    1: SectionText("Unemployment is forecast to peak at 5.4 per cent, before easing.", 2, 3),
    2: SectionText("Risks are tilted to the downside if the example export price falls.", 4, 4),
}
PROV = ModelProvenance(
    provider="test", model="none", prompt_version="outlook-v0", processing_version="3b-0",
    parameters={"temperature": 0}, input_text_sha256="0" * 64,
    created_at=datetime(2026, 10, 25, tzinfo=UTC),
)  # fmt: skip


def ref(ordinal: int, quote: str, page: int | None = None) -> EvidenceRef:
    return EvidenceRef(version_id=7, section_ordinal=ordinal, page=page, quote=quote)


def summary(**kw) -> OutlookSummary:
    base = dict(
        version_id=7,
        outlook={"text": "Modest growth", "evidence": [ref(0, "expected to grow 2.5%")]},
        drivers=[],
        risks=[{"text": "Export prices", "evidence": [ref(2, "tilted to the downside")]}],
        forecasts=[
            ForecastClaim(
                indicator="unemployment", indicator_label="Unemployment rate", horizon="peak",
                value=5.4, unit="percent", direction="up", qualification="before easing",
                evidence=[ref(1, "forecast to peak at 5.4 per cent", page=2)],
            )
        ],
        provenance=PROV,
    )  # fmt: skip
    base.update(kw)
    return OutlookSummary(**base)


def test_a_fully_supported_summary_has_no_problems():
    assert verify_summary(summary(), SECTIONS) == []


def test_quotes_must_be_verbatim_after_whitespace_normalisation():
    s = summary(outlook={"text": "x", "evidence": [ref(0, "expected   to\ngrow 2.5%")]})
    assert verify_summary(s, SECTIONS) == []
    bad = summary(outlook={"text": "x", "evidence": [ref(0, "expected to grow 3.5%")]})
    assert verify_summary(bad, SECTIONS) == ["outlook.evidence[0]: quote not found in section 0"]


def test_unknown_section_wrong_version_and_page_outside_section_are_reported():
    s = summary(
        risks=[{"text": "r", "evidence": [ref(9, "anything at all")]}],
        outlook={"text": "x", "evidence": [EvidenceRef(version_id=8, section_ordinal=0, page=None,
                                                       quote="expected to grow")]},
    )  # fmt: skip
    problems = verify_summary(s, SECTIONS)
    assert "risks[0].evidence[0]: unknown section 9" in problems
    assert "outlook.evidence[0]: cites version 8, not 7" in problems
    paged = summary(outlook={"text": "x", "evidence": [ref(0, "expected to grow", page=5)]})
    assert verify_summary(paged, SECTIONS) == ["outlook.evidence[0]: page 5 is outside section 0"]


def test_a_forecast_number_must_appear_in_its_own_quote():
    claim = ForecastClaim(
        indicator="unemployment", indicator_label="Unemployment", horizon="peak", value=6.1,
        unit="percent", direction="up", evidence=[ref(1, "forecast to peak at 5.4 per cent")],
    )  # fmt: skip
    assert verify_summary(summary(forecasts=[claim]), SECTIONS) == [
        "forecasts[0]: value 6.1 does not appear in its evidence"
    ]


def test_claims_without_evidence_are_rejected_by_the_model():
    with pytest.raises(ValidationError):
        ForecastClaim(indicator="gdp", indicator_label="GDP", horizon="2027", value=1.0,
                      unit="percent", direction="up", evidence=[])  # fmt: skip
    with pytest.raises(ValidationError):
        summary(outlook={"text": "Unsupported", "evidence": []})


def test_output_is_never_an_official_statistic():
    assert summary().not_official_statistic is True
    assert summary().review_status == "unreviewed"
    with pytest.raises(ValidationError):
        summary(not_official_statistic=False)


def test_parse_summary_rejects_oversized_or_extra_fields():
    raw = summary().model_dump_json()
    assert parse_summary(raw) == summary()
    with pytest.raises(ValueError):
        parse_summary(raw[:-1] + ', "series_key": "cpi"}')
    with pytest.raises(ValueError):
        parse_summary("x" * (contract.MAX_OUTPUT_CHARS + 1))


def test_the_disabled_provider_never_calls_anything():
    request = build_request(7, SECTIONS, prompt_version="outlook-v0")
    with pytest.raises(ProviderDisabled):
        DisabledProvider().summarise(request)


def test_requests_frame_document_text_as_untrusted_data_within_limits():
    request = build_request(7, SECTIONS, prompt_version="outlook-v0")
    assert isinstance(request, SummaryRequest)
    assert "untrusted" in request.instructions.lower()
    assert [s.ordinal for s in request.sections] == [0, 1, 2]
    small = build_request(
        7, SECTIONS, prompt_version="v0", limits=contract.LlmLimits(max_input_chars=80)
    )
    assert sum(len(s.text) for s in small.sections) <= 80 and small.truncated


def test_contract_has_no_network_or_vendor_sdk_imports_and_no_stats_tables():
    source = Path(contract.__file__).read_text()
    tree = ast.parse(source)
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }
    banned = ("anthropic", "openai", "httpx", "requests", "socket", "urllib", "nzstats.store")
    assert not any(name.startswith(banned) for name in imported)
    for table in ("observation", "vintage", "series"):
        assert f"INSERT INTO {table}" not in source


def test_no_vendor_llm_sdk_is_imported_anywhere_in_the_backend():
    root = Path(contract.__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(n.split(".")[0] in ("anthropic", "openai") for n in names), path


# --- Phase 3B: the model returns a draft; the pipeline attaches version and provenance -----------
def _draft_json(**kw) -> str:
    s = summary()
    data = s.model_dump(mode="json", exclude={"version_id", "provenance", "not_official_statistic",
                                              "review_status"})  # fmt: skip
    data.update(kw)
    return json.dumps(data)


def test_a_draft_parses_and_assembles_into_an_unreviewed_interpretation():
    draft = contract.parse_draft(_draft_json())
    assembled = contract.assemble(draft, version_id=7, provenance=PROV)
    assert assembled == summary()
    assert assembled.not_official_statistic is True and assembled.review_status == "unreviewed"


def test_a_single_json_code_fence_is_tolerated():
    assert contract.parse_draft("```json\n" + _draft_json() + "\n```") == contract.parse_draft(
        _draft_json()
    )


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "",
        '{"outlook": 1, "outlook": 2}',
        "x" * (contract.MAX_OUTPUT_CHARS + 1),
        "[]",
    ],
)
def test_bad_model_output_is_a_value_error(raw):
    with pytest.raises(ValueError):
        contract.parse_draft(raw)


def test_a_duplicate_key_anywhere_is_rejected():
    raw = _draft_json().replace('"indicators"', '"indicators": [], "indicators"', 1)
    with pytest.raises(ValueError, match="duplicate"):
        contract.parse_draft(raw)


def test_draft_rejects_provenance_or_review_fields_written_by_the_model():
    for extra in (
        {"review_status": "approved"},
        {"version_id": 7},
        {"not_official_statistic": True},
    ):
        with pytest.raises(ValueError):
            contract.parse_draft(_draft_json(**extra))


def test_output_size_is_bounded_by_item_counts():
    claim = summary().forecasts[0].model_dump(mode="json")
    with pytest.raises(ValueError):
        contract.parse_draft(_draft_json(forecasts=[claim] * 51))
    many_refs = dict(claim, evidence=[claim["evidence"][0]] * 6)
    with pytest.raises(ValueError):
        contract.parse_draft(_draft_json(forecasts=[many_refs]))


def test_scenario_defaults_to_baseline():
    assert summary().forecasts[0].scenario is None
    named = summary().forecasts[0].model_copy(update={"scenario": "downside scenario"})
    assert named.scenario == "downside scenario"


def test_provider_errors_carry_only_a_class_and_retryability():
    err = contract.ProviderError("rate_limited", retryable=True)
    assert err.error_class == "rate_limited" and err.retryable and str(err) == "rate_limited"
    assert contract.LlmLimits().max_retries == 2
