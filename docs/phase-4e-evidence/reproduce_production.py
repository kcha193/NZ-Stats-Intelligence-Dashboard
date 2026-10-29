import dataclasses
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from nzstats.research.accuracy import evaluate_forecasts
from nzstats.research.cpi_reconcile import reconcile
from nzstats.research.macro_outcomes import gdp_actuals, unemployment_actuals
from nzstats.research.outcomes import Target
from nzstats.store import repo
from nzstats.store.backup_check import verify_backup
from tests.research.test_compare import claim

root = Path("data/phase-4e")
backup = json.loads((root / "approved-backup.json").read_text())
ledger = json.loads((root / "activation-results.json").read_text())
assert (
    len(ledger["requests"]) == len(ledger["logical_gets"]) == 30
    and len(ledger["release_results"]) == 7
    and ledger["stop"] is None
)
assert all(r["status"] == 200 for r in ledger["requests"])
dest = root / "post-backfill-copy"
dest.mkdir(exist_ok=True)
live = sqlite3.connect(
    Path("data/nzstats.db").resolve().as_uri() + "?mode=ro", uri=True
)
c = sqlite3.connect(dest / "nzstats.db")
live.backup(c)
c.close()
live.close()
shutil.copytree("data/raw", dest / "raw", dirs_exist_ok=True)
report = verify_backup(
    dest / "nzstats.db", live="data/nzstats.db", raw_dir=dest / "raw"
)
assert report.ok and not report.count_differences
c = sqlite3.connect((dest / "nzstats.db").resolve().as_uri() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
old = sqlite3.connect(
    (Path(backup["backup_dir"]) / "nzstats.db").resolve().as_uri() + "?mode=ro",
    uri=True,
)
protected = []
for table in ["observation", "vintage", "vintage_series_definition"]:
    prior = [tuple(r) for r in old.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
    maxid = max(r[0] for r in prior)
    column = "id" if table == "vintage" else "vintage_id"
    current = [
        tuple(r)
        for r in c.execute(
            f"SELECT * FROM {table} WHERE {column} <= ? ORDER BY 1,2", (maxid,)
        )
    ]
    assert prior == current, table
    protected.append(
        {
            "table": table,
            "rows_preserved": len(prior),
            "sha256": hashlib.sha256(
                json.dumps(current, separators=(",", ":")).encode()
            ).hexdigest(),
            "unchanged": True,
        }
    )
artifacts = []
for row in c.execute(
    "SELECT url,sha256,fetched_at,size_bytes,path FROM raw_artifact ORDER BY id"
):
    body = (dest / "raw" / row["path"]).read_bytes()
    assert (
        len(body) == row["size_bytes"]
        and hashlib.sha256(body).hexdigest() == row["sha256"]
    )
    artifacts.append(
        {key: row[key] for key in ("url", "sha256", "fetched_at", "size_bytes")}
    )
assert all(report.counts[t] == 0 for t in report.counts if t.startswith("research_"))
releases = []
for result in ledger["release_results"]:
    key = result["release_key"]
    rows = c.execute(
        "SELECT v.id,v.bundle_sha256,v.captured_at,v.source_kind,s.key FROM vintage v JOIN series s ON s.id=v.series_id JOIN release r ON r.id=v.release_id WHERE r.release_key=? ORDER BY v.id",
        (key,),
    ).fetchall()
    eligibility = [
        repo.supports_first_publication(c, info)
        for row in rows
        for info in repo.list_vintages(c, row["key"])
        if info.vintage_id == row["id"]
    ]
    assert len(eligibility) == len(rows) and not any(eligibility)
    releases.append(
        {
            "release_key": key,
            "vintage_ids": [r["id"] for r in rows],
            "bundle_identities": sorted({r["bundle_sha256"] for r in rows}),
            "captured_at": sorted({r["captured_at"] for r in rows}),
            "source_kind": sorted({r["source_kind"] for r in rows}),
            "first_publication_eligible": False,
            "series_vintages": len(rows),
            "observations": result["counts"]["observations"],
            "requests": result["requests_used"],
            "reconciliation": result["independent_reconciliation"],
        }
    )
audit = reconcile(c, dest / "raw")
assert audit.ok
(root / "cpi-reconciliation-final.json").write_text(
    json.dumps(dataclasses.asdict(audit), indent=2) + "\n"
)
forecasts = []
for indicator, actuals, measure, pub in [
    ("gdp", gdp_actuals(c), "gdp_quarterly_production", "2026-06-18"),
    ("unemployment", unemployment_actuals(c), "unemployment_rate", "2026-05-06"),
]:
    outcome = actuals.outcome(Target(measure, "2026-03"))
    assert outcome is not None and not outcome.first.first_release
    f = claim(
        indicator=indicator,
        indicator_label="Real GDP growth, production measure, quarterly"
        if indicator == "gdp"
        else "Unemployment rate",
        horizon="March 2026 quarter",
        value=0.5,
        published_on="2026-01-01",
    )
    e = evaluate_forecasts([f], actuals, indicator=indicator).evaluated[0]
    assert e.error_first is None and e.outcome_revision is None
    excluded = evaluate_forecasts(
        [f.model_copy(update={"published_on": pub})], actuals, indicator=indicator
    )
    assert excluded.excluded and not excluded.evaluated
    forecasts.append(
        {
            "indicator": indicator,
            "scope": "in_memory_synthetic_claim_against_actual_production_outcomes_no_research_rows_written",
            "first_stored": outcome.first.value,
            "latest": outcome.latest.value,
            "first_publication_eligible": False,
            "first_error": e.error_first,
            "first_revision": e.outcome_revision,
            "release_day_claim_excluded": True,
        }
    )
expected = {"gdp": (0.8, 0.9), "unemployment": (5.3, 5.4)}
assert all(
    (item["first_stored"], item["latest"]) == expected[item["indicator"]]
    for item in forecasts
)
new_vintages = report.counts["vintage"] - backup["verification"]["counts"]["vintage"]
new_observations = (
    report.counts["observation"] - backup["verification"]["counts"]["observation"]
)
assert (new_vintages, new_observations) == (268, 24093)
starts = [datetime.fromisoformat(r["requested_at"]) for r in ledger["requests"]]
gaps = [(b - a).total_seconds() for a, b in pairwise(starts)]
assert min(gaps) >= 10
result = {
    "checked_at": datetime.now(UTC).isoformat(),
    "production_backup_check": dataclasses.asdict(report),
    "protected_pre_existing_rows": protected,
    "raw_artifacts": artifacts,
    "releases": releases,
    "new_series_vintages": new_vintages,
    "new_observations": new_observations,
    "cpi": {
        "official_files": audit.official_files,
        "vintages": len(audit.vintages),
        "outcomes": len(audit.outcomes),
        "genuine_first_quarters": sorted(
            {o.quarter for o in audit.outcomes if o.genuine_first_release}
        ),
        "discrepancies": audit.discrepancies,
    },
    "forecast_provenance_checks": forecasts,
    "request_accounting": {
        "logical_gets": 30,
        "network_attempts": 30,
        "redirects": 0,
        "retries": 0,
        "min_observed_start_gap_seconds": min(gaps),
        "configured_min_interval_seconds": 10,
    },
    "unexplained_discrepancies": [],
}
(root / "production-reconciliation-final.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
old.close()
c.close()
print(
    json.dumps(
        {
            key: value
            for key, value in result.items()
            if key not in ("raw_artifacts", "releases", "production_backup_check")
        },
        indent=2,
    )
)
print("counts", report.counts)
