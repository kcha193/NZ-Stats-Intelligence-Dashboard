"""Check the deterministic research layers against the Phase 4H reference annotation of two real documents.

Usage (from backend/, with the venv active):
  python ../scripts/check_research_baseline.py ../data/phase-4h/annotations/baseline-2026-10-31.json \
      --gold ../data/annotations/phase-4i-evaluate.json [--db ../data/nzstats.db]

Read-only and offline: the database is opened `mode=ro`, nothing is written, no model is called and nothing is
fetched. The annotation and the documents are third-party material kept under the git-ignored `data/`, so this
prints only item numbers, verifier codes and counts, never document text or quotes.

It checks that every anchored item still matches the stored sections; builds contract version 2 records from the
annotation (reported facts, forecasts with their issuer, the policy decision) and verifies them with the current
verifier, then plants the Phase 4H errors and checks that each is caught; recomputes each Stats NZ comparison at
the vintage the document could see; and scores a reference output with the evaluation tooling.
"""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))
from nzstats.research.contract import (  # noqa: E402
    Adjustment,
    ForecastClaim,
    ModelProvenance,
    OutlookSummary,
    PolicyDecision,
    ReportedFact,
)
from nzstats.research.evaluate import PRICE_POINTS, EvalReport, aggregate, score  # noqa: E402
from nzstats.research.official_compare import compare_figure  # noqa: E402
from nzstats.research.pilot_eval import _gold, load_annotations  # noqa: E402
from nzstats.research.prompt import injection_findings  # noqa: E402
from nzstats.research.summarise import load_sections  # noqa: E402
from nzstats.research.verify import (  # noqa: E402
    VerificationContext,
    _Layout,
    _locate,
    _norm,
    _number_spans,
    verify,
)

PROV = ModelProvenance(provider="reference", model="annotation", prompt_version="none", processing_version="4i",
                       input_text_sha256="0" * 64, created_at=datetime(2026, 10, 31, tzinfo=UTC))  # fmt: skip
SA, NSA, UNSTATED = Adjustment.SEASONALLY_ADJUSTED, Adjustment.UNADJUSTED, Adjustment.NOT_STATED
# The reconciliation's figures as (period, measure, adjustment basis the document states).
RECONCILIATION = {
    "CPI annual 2026Q2": ("2026-06", "change_on_year", UNSTATED),
    "CPI quarterly 2026Q2 (SA)": ("2026-06", "change_on_previous", SA),
    "GDP qpc 2026Q2 (SA)": ("2026-06", "level", SA),
    "GDP qpc 2026Q1 (SA)": ("2026-03", "level", SA),
    "GDP annual average 2026Q2": ("2026-06", "annual", UNSTATED),
    "Unemployment rate 2026Q2 (SA)": ("2026-06", "level", SA),
    "Participation rate 2026Q2 (SA)": ("2026-06", "level", SA),
    "Employment qpc 2026Q2 (SA)": ("2026-06", "change_on_previous", SA),
    "LCI salary and wage rates annual 2026Q2": ("2026-06", "annual", UNSTATED),
    "Net migration year to Aug 2026": ("2026-08", "level", UNSTATED),
    "Net migration year to Jan 2026": ("2026-01", "level", UNSTATED),
    "Net migration July 2026 (monthly)": ("2026-07", "level", UNSTATED),
    "Net migration August 2026 (monthly)": ("2026-08", "level", UNSTATED),
    "CPI annual 2026Q3": ("2026-09", "change_on_year", UNSTATED),
    "Tradables annual 2026Q3": ("2026-09", "change_on_year", UNSTATED),
    "Tradables annual 2026Q2": ("2026-06", "change_on_year", UNSTATED),
    "Non-tradables annual 2026Q3": ("2026-09", "change_on_year", UNSTATED),
}
ISSUER_CODES = {"issuer_mismatch", "issuer_not_in_evidence", "issuer_unclear", "missing_issuer"}


def ref(e: dict) -> dict:
    return {k: e[k] for k in ("version_id", "section_ordinal", "page", "quote")}


class Doc:
    def __init__(self, conn: sqlite3.Connection, raw: dict) -> None:
        self.raw, self.version = raw, raw["version_id"]
        row = conn.execute(
            "SELECT p.published_on, i.key FROM research_document_version v JOIN research_publication p"
            " ON p.id = v.publication_id JOIN research_institution i ON i.id = p.institution_id WHERE v.id = ?",
            (self.version,),
        ).fetchone()
        self.published_on, self.institution = date.fromisoformat(row[0]), row[1]
        self.sections = load_sections(conn, self.version)
        self.outlook = next(ref(i["evidence"][0]) for i in raw["items"] if i["kind"] == "interpretation")

    def run(self, **records) -> tuple[set[str], set[str]]:
        indicators = {c.indicator for c in records.get("forecasts", ())}
        summary = OutlookSummary(version_id=self.version, contract_version=2, provenance=PROV, indicators=indicators,
                                 outlook={"text": "Reference outlook.", "evidence": [self.outlook]}, **records)  # fmt: skip
        ctx = VerificationContext(published_on=self.published_on, institution=self.institution,
                                  injection_ordinals=tuple(injection_findings(self.sections)))  # fmt: skip
        report = verify(summary, self.sections, ctx)
        own = [p for p in report.errors if not p.path.startswith("outlook")]
        warn = [p for p in report.warnings if not p.path.startswith("outlook")]
        return {p.code for p in own}, {p.code for p in warn}


def numbers(quote: str, section=None) -> list[float]:
    """The numbers in a quote as the verifier reads it (signs split across lines rejoined)."""
    located = _locate(quote, section)[0] if section is not None else None
    return [v for v, _, _ in _number_spans(located.quote if located else _norm(quote))]


def anchors(docs: list[Doc]) -> None:
    total, clean, pages = 0, 0, 0
    problems = []
    for d in docs:
        for n, item in enumerate(d.raw["items"]):
            for e in item["evidence"]:
                total += 1
                section = d.sections.get(e["section_ordinal"])
                if section is None:
                    problems.append((d.institution, n, "unknown section"))
                    continue
                exact = " ".join(section.text[e["char_start"] : e["char_end"]].split()) == " ".join(e["quote"].split())
                located, truncation = _locate(e["quote"], section)
                ok_page = (e["page"] is None and section.page_start is None) or (
                    section.page_start is not None
                    and section.page_start <= (e["page"] or 0) <= (section.page_end or section.page_start)
                )
                pages += ok_page
                if exact and located is not None and truncation is None:
                    clean += 1
                else:
                    problems.append((d.institution, n, "offsets" if not exact else truncation or "not found"))
    print(f"anchored evidence: {clean}/{total} quotes match their offsets and are found cleanly by verify-3;"
          f" pages correct {pages}/{total}")  # fmt: skip
    for p in problems:
        print("  problem:", *p)


def forecasts(docs: list[Doc], gold_file) -> None:
    gold = {doc.version_id: doc for doc in gold_file.documents}
    print("\nissuer attribution on every annotated forecast (annotated issuer, then the issuer swapped):")
    for d in docs:
        for n, item in enumerate(d.raw["items"]):
            if item["kind"] != "forecast":
                continue
            values = [v for v in numbers(item["evidence"][0]["quote"]) if not 1990 <= v <= 2100]
            claim = dict(indicator="other", indicator_label="figure", horizon=str(d.published_on.year + 1),
                         value=values[0] if values else None, unit="percent" if values else None,
                         direction="unclear", evidence=[ref(e) for e in item["evidence"]])  # fmt: skip
            own = item["issuer"] == d.institution
            right = {"issuer": "author" if own else item["issuer"].upper(), "issuer_role": "author" if own else "third_party"}
            if own:
                right["issuer"] = d.institution
            swapped = ({"issuer": "IMF", "issuer_role": "third_party"} if own
                       else {"issuer": d.institution, "issuer_role": "author"})  # fmt: skip
            e1, w1 = d.run(forecasts=[ForecastClaim(**claim, **right)])
            e2, w2 = d.run(forecasts=[ForecastClaim(**claim, **swapped)])
            print(f"  {d.institution} item {n} ({item['issuer']}): issuer findings when right"
                  f" {sorted((e1 | w1) & ISSUER_CODES) or 'none'}; when swapped: errors {sorted(e2 & ISSUER_CODES) or 'NONE'},"
                  f" warnings {sorted(w2 & ISSUER_CODES) or 'none'}")  # fmt: skip

    print("\nthe gold forecasts (the documents' own), as a faithful model would report them:")
    for d in docs:
        doc_gold = gold.get(d.version)
        if doc_gold is None:
            continue
        own_items = [i for i in d.raw["items"] if i["kind"] == "forecast" and i["issuer"] == d.institution]
        for g in doc_gold.forecasts:
            item = next((i for i in own_items if any(abs(v - (g.value or 0)) < 1e-9 for v in numbers(i["evidence"][0]["quote"]))), None)  # fmt: skip
            if item is None:
                print(f"  {d.institution} {g.indicator} {g.horizon}: no anchored quote holds {g.value:g}")
                continue
            claim = ForecastClaim(indicator=g.indicator, indicator_label=g.indicator.value.replace("_", " "),
                                  horizon=g.horizon, value=g.value, unit=g.unit, direction="unclear",
                                  issuer=d.institution, issuer_role="author",
                                  evidence=[ref(e) for e in item["evidence"]])  # fmt: skip
            errors, warnings = d.run(forecasts=[claim])
            print(f"  {d.institution} {g.indicator.value} {g.horizon} = {g.value:g}: errors {sorted(errors) or 'none'};"
                  f" warnings {sorted(warnings) or 'none'}")  # fmt: skip


def facts_and_layout(docs: list[Doc]) -> None:
    print("\nreported facts and interpretations (value-free records) and the Phase 4H layout hazards:")
    for d in docs:
        counts: Counter[str] = Counter()
        for item in d.raw["items"]:
            evidence = [ref(e) for e in item["evidence"]]
            if item["kind"] == "reported_fact":
                fact = ReportedFact(text="Reference fact.", source=item.get("source") or d.institution, evidence=evidence)
                errors, _ = d.run(facts=[fact])
                counts.update(f"fact:{c}" for c in errors or {"clean"})
            elif item["kind"] == "interpretation":
                errors, _ = d.run(drivers=[{"text": "Reference view.", "evidence": evidence}])
                counts.update(f"interpretation:{c}" for c in errors or {"clean"})
        print(f"  {d.institution}: {dict(sorted(counts.items()))}")
        residue = {o: len(_Layout(s.text).residue) for o, s in d.sections.items()}
        print(f"  {d.institution}: chart-axis/unlabelled-number lines per section {residue}")
        for n, item in enumerate(d.raw["items"]):
            hazard = item.get("extraction_hazard") or ""
            if "minus" not in hazard:
                continue
            signed = [v for v in numbers(item["evidence"][0]["quote"], d.sections[item["evidence"][0]["section_ordinal"]]) if v < 0]
            base = dict(text="Reference fact.", source=item.get("source") or "survey", unit="percent",
                        evidence=[ref(e) for e in item["evidence"]])  # fmt: skip
            kept, _ = d.run(facts=[ReportedFact(**base, value=signed[0])]) if signed else ({"no negative"}, set())
            dropped, _ = d.run(facts=[ReportedFact(**base, value=-signed[0])]) if signed else (set(), set())
            print(f"  {d.institution} item {n} split minus sign: signed value errors {sorted(kept & {'value_not_in_evidence'}) or 'none'};"
                  f" sign dropped flagged {'value_not_in_evidence' in dropped}")  # fmt: skip
        for n, item in enumerate(d.raw["items"]):
            quote = _norm(item["evidence"][0]["quote"])
            for figure in (3190, 1530):
                if figure in numbers(quote):
                    base = dict(text="Monthly net migration.", source=d.institution, value=figure, unit="persons",
                                evidence=[ref(e) for e in item["evidence"]])  # fmt: skip
                    e1, w1 = d.run(facts=[ReportedFact(**base, definition={"adjustment": "not_stated"})])
                    e2, _ = d.run(facts=[ReportedFact(**base, definition={"adjustment": "seasonally_adjusted"})])
                    print(f"  {d.institution} item {n} monthly migration {figure}: unstated basis warned"
                          f" {'definition_not_stated' in w1}; an invented SA basis flagged"
                          f" {'definition_not_in_evidence' in e2}")  # fmt: skip


def decisions(docs: list[Doc], gold_file) -> None:
    gold = {doc.version_id: doc for doc in gold_file.documents}
    for d in docs:
        doc_gold = gold.get(d.version)
        items = [i for i in d.raw["items"] if i["kind"] == "policy_decision"]
        if not doc_gold or not doc_gold.decisions or not items:
            continue
        g = doc_gold.decisions[0]
        evidence = [ref(e) for i in items for e in i["evidence"]]
        base = dict(action=g.action, rate=g.rate, decided_on=g.decided_on, decision_maker="Monetary Policy Committee",
                    evidence=evidence)  # fmt: skip
        print(f"\n{d.institution} policy decision ({g.action} at {g.rate:g}%, {g.decided_on}, vote {g.vote_for}–{g.vote_against}):")
        faithful = PolicyDecision(**base, vote_for=g.vote_for, vote_against=g.vote_against)
        print("  faithful:", *d.run(decisions=[faithful]))
        print("  vote omitted:", d.run(decisions=[PolicyDecision(**base)])[0])
        print("  wrong vote:", d.run(decisions=[PolicyDecision(**base, vote_for=5, vote_against=2)])[0])
        as_forecast = ForecastClaim(indicator="ocr", indicator_label="OCR", horizon=str(g.decided_on.year),
                                    value=g.rate, unit="percent", direction="flat", issuer=d.institution,
                                    issuer_role="author", evidence=evidence)  # fmt: skip
        print("  reported as a forecast:", d.run(forecasts=[as_forecast])[0])


def reconciliation(conn: sqlite3.Connection, docs: list[Doc], rows: list[dict]) -> None:
    by_key = {d.institution: d for d in docs}
    print("\nStats NZ comparisons at the vintage each document could see:")
    tally: Counter[str] = Counter()
    for row in rows:
        period, measure, basis = RECONCILIATION[row["figure"]]
        d = by_key[row["doc"]]
        r = compare_figure(conn, series=row["series"], period=period, measure=measure, document_value=row["doc_value"],
                           adjustment=basis, published_on=d.published_on)  # fmt: skip
        recorded = "match" if row["match"] else "basis mismatch"
        agrees = (r.status == "match") == row["match"] and (row["match"] or r.status == "not_comparable")
        tally[r.status] += 1
        print(f"  {row['doc']} {row['figure']}: {r.status} (official {r.official}, {r.released_on});"
              f" 4H recorded {recorded}; agrees {agrees}")  # fmt: skip
    print(f"  totals: {dict(tally)}")


def scoring(docs: list[Doc], gold_file) -> None:
    """A reference output built from the gold through the real scoring functions: the tooling scores contract v2."""
    report = EvalReport("reference")
    for doc in gold_file.documents:
        d = next(x for x in docs if x.version == doc.version_id)
        claims = []
        for g in doc.forecasts:
            item = next((i for i in d.raw["items"] if i["kind"] == "forecast" and i["issuer"] == d.institution
                         and any(abs(v - (g.value or 0)) < 1e-9 for v in numbers(i["evidence"][0]["quote"]))), None)  # fmt: skip
            if item is not None:
                claims.append(ForecastClaim(indicator=g.indicator, indicator_label=g.indicator.value, horizon=g.horizon,
                                            value=g.value, unit=g.unit, direction="unclear", issuer=d.institution,
                                            issuer_role="author", evidence=[ref(e) for e in item["evidence"]]))  # fmt: skip
        decided = [PolicyDecision(action=g.action, rate=g.rate, decided_on=g.decided_on, vote_for=g.vote_for,
                                  vote_against=g.vote_against, decision_maker="Monetary Policy Committee",
                                  evidence=[ref(e) for i in d.raw["items"] if i["kind"] == "policy_decision"
                                            for e in i["evidence"]]) for g in doc.decisions]  # fmt: skip
        summary = OutlookSummary(version_id=d.version, contract_version=2, provenance=PROV, forecasts=claims,
                                 decisions=decided, indicators=doc.indicators,
                                 outlook={"text": "Reference outlook.", "evidence": [d.outlook]})  # fmt: skip
        ctx = VerificationContext(published_on=d.published_on, institution=d.institution)
        result = verify(summary, d.sections, ctx)
        report.models.append(score(str(d.version), str(d.version), summary, result, _gold(doc), 0, 0, True, 0.0))
    aggregate(report, PRICE_POINTS)
    keep = ("raw_precision", "raw_recall", "accepted_recall", "numerical_fidelity", "issuer_accuracy",
            "decision_recall", "decision_fidelity", "verified_rate")  # fmt: skip
    print("\nreference output scored by the evaluation tooling:",
          {k: None if report.metrics[k] is None else round(report.metrics[k], 3) for k in keep})  # fmt: skip
    print("  verifier errors on the reference output:", sorted({c for m in report.models for c in m.errors}) or "none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path, help="the Phase 4H reference annotation (git-ignored)")
    parser.add_argument("--gold", type=Path, required=True, help="the evaluation gold file (git-ignored)")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "nzstats.db")
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    gold = load_annotations(args.gold)
    conn = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    docs = [Doc(conn, raw) for raw in baseline["documents"]]
    items = sum(len(d.raw["items"]) for d in docs)
    print(f"{len(docs)} documents, {items} anchored items (annotator: {baseline['annotator'].split(' (')[0]})")
    anchors(docs)
    forecasts(docs, gold)
    facts_and_layout(docs)
    decisions(docs, gold)
    reconciliation(conn, docs, baseline["statsnz_reconciliation"])
    scoring(docs, gold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
