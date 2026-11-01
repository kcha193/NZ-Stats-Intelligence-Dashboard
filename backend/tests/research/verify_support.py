"""Shared builders for the Phase 4I verifier tests (synthetic text only)."""

from datetime import UTC, date, datetime

from nzstats.research.contract import (
    CONTRACT_VERSION,
    EvidenceRef,
    ForecastClaim,
    ModelProvenance,
    OutlookSummary,
    SectionText,
)
from nzstats.research.verify import VerificationContext, VerificationReport, verify

V = 7
PROV = ModelProvenance(
    provider="fake", model="m", prompt_version="outlook-v3", processing_version="3b-1",
    input_text_sha256="0" * 64, created_at=datetime(2026, 10, 26, tzinfo=UTC),
)  # fmt: skip


def ref(ordinal: int, quote: str, page: int | None = None) -> EvidenceRef:
    return EvidenceRef(version_id=V, section_ordinal=ordinal, page=page, quote=quote)


def forecast(ordinal: int, quote: str, page: int | None = None, **kw) -> ForecastClaim:
    base = dict(indicator="gdp", indicator_label="GDP growth", horizon="2027", value=None,
                unit=None, direction="unclear", issuer="The Treasury", issuer_role="author",
                evidence=[ref(ordinal, quote, page)])  # fmt: skip
    base.update(kw)
    return ForecastClaim(**base)


def check(
    sections: dict[int, SectionText],
    *,
    outlook_ref: EvidenceRef,
    institution: str | None = "treasury",
    published_on: date | None = date(2026, 10, 15),
    contract_version: int = CONTRACT_VERSION,
    **items,
) -> VerificationReport:
    s = OutlookSummary(
        version_id=V, contract_version=contract_version, provenance=PROV,
        outlook={"text": "The outlook", "evidence": [outlook_ref]},
        indicators=items.pop("indicators", ("gdp", "cpi_inflation", "ocr", "migration")), **items,
    )  # fmt: skip
    ctx = VerificationContext(published_on=published_on, institution=institution)
    return verify(s, sections, ctx)


def codes(report: VerificationReport) -> set[str]:
    return {p.code for p in report.errors}


def warning_codes(report: VerificationReport) -> set[str]:
    return {p.code for p in report.warnings}
