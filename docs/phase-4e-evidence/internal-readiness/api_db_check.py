"""Independent API-to-SQL consistency check over the isolated copy. Read-only; loopback only."""

import json
import sqlite3
import sys
import urllib.parse
import urllib.request

db, base = sys.argv[1], sys.argv[2]
c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
c.row_factory = sqlite3.Row


def get(path):
    with urllib.request.urlopen(base + path) as r:
        return json.load(r)


def latest_vintage(key):
    # Independent rule: newest publication, then newest capture, then highest id.
    return c.execute(
        "SELECT v.id, r.release_key, r.page_url FROM vintage v JOIN series s ON s.id = v.series_id"
        " JOIN release r ON r.id = v.release_id WHERE s.key = ?"
        " ORDER BY r.published_at DESC, v.captured_at DESC, v.id DESC LIMIT 1",
        (key,),
    ).fetchone()


def sql_points(vid):
    return {
        r["period"]: (r["value"], r["status"])
        for r in c.execute(
            "SELECT period, value, status FROM observation WHERE vintage_id = ?", (vid,)
        )
    }


report = {"series_checked": 0, "points_checked": 0, "problems": []}
for s in get("/api/series"):
    key = s["key"]
    api = get("/api/series/" + urllib.parse.quote(key, safe=""))
    lv = latest_vintage(key)
    if lv is None:
        report["problems"].append(f"{key}: no vintage in SQL")
        continue
    if api["vintage"]["release_key"] != lv["release_key"]:
        report["problems"].append(
            f"{key}: API vintage {api['vintage']['release_key']} != SQL {lv['release_key']}"
        )
    sp = sql_points(lv["id"])
    ap = {p["period"]: (p["value"], p["status"]) for p in api["points"]}
    if sp != ap:
        report["problems"].append(f"{key}: points differ ({len(ap)} API vs {len(sp)} SQL)")
    src = api.get("source_url") or ""
    if src and not src.startswith("https://www.stats.govt.nz/"):
        report["problems"].append(f"{key}: non-Stats NZ source {src}")
    report["series_checked"] += 1
    report["points_checked"] += len(ap)

# Category endpoints must show the same latest values as the per-series endpoint.
for ep in ("gdp", "labour-market"):
    payload = get(f"/api/{ep}")
    n = 0
    for s in payload["series"]:
        lv = latest_vintage(s["key"])
        sp = sql_points(lv["id"])
        for p in s["points"]:
            n += 1
            if sp.get(p["period"], (None,))[0] != p["value"]:
                report["problems"].append(
                    f"/api/{ep} {s['key']} {p['period']}: {p['value']} != SQL"
                )
    report[f"{ep}_points_checked"] = n
    report[f"{ep}_reference_period"] = payload["reference_period"]
cpi = get("/api/cpi")
n = 0
for s in cpi["series"]:
    lv = latest_vintage(s["key"])
    sp = sql_points(lv["id"])
    for p in s["points"]:
        if p.get("index") is None:
            continue
        n += 1
        if sp.get(p["period"], (None,))[0] != p["index"]:
            report["problems"].append(f"/api/cpi {s['key']} {p['period']}: {p['index']} != SQL")
report["cpi_index_points_checked"] = n
report["cpi_reference_period"] = cpi["reference_period"]
print(json.dumps(report, indent=2))
sys.exit(1 if report["problems"] else 0)
