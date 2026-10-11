# NZ Stats Intelligence Dashboard — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an end-to-end working Phase 1: release discovery, vintage-preserving International Migration ingestion, deterministic release analysis, a premium React dashboard (Overview, Migration, Release Analysis, Calendar, Health), Docker deployment and CI.

**Architecture:** A Python package (`nzstats`) discovers releases from the official Stats NZ ICS calendar and the site's month endpoint, downloads each release's official CSV files, parses them with a versioned adapter, validates, and commits one vintage per release in a single SQLite transaction. A read-only FastAPI app serves deterministic analysis; a React/ECharts SPA (served by the same container) presents it. An in-process APScheduler polls only around scheduled publication times.

**Tech Stack:** Python 3.12 (Docker; local 3.11+), FastAPI, Pydantic v2, httpx, pandas, APScheduler 3, SQLite (WAL), pytest, ruff; React 18 + TypeScript + Vite + Tailwind + shadcn/ui + Apache ECharts + TanStack Query/Table, vitest, Playwright; Docker Compose; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md` (read it first; this plan implements Phase 1 of it).

## Global Constraints

Every task's requirements implicitly include these (copied from the spec / Kevin's standards):

- Python: type hints on public functions; `pathlib`; `logging` not `print`; ruff `line-length = 100`; pytest; no silent exception swallowing; no hard-coded local paths.
- Stats NZ access: descriptive User-Agent; **at least 10 s between requests** to stats.govt.nz (robots.txt crawl-delay); cache raw artifacts; no continuous scraping; attribute Stats NZ (CC BY 4.0) in the UI.
- All schedules and displayed times use `Pacific/Auckland`. **Store timestamps as UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`)** so text ordering is correct across NZST/NZDT; convert to Auckland at the API boundary.
- No synthetic values in production code paths. Test fixtures are real excerpts of official files; tests may build tiny inputs inline to exercise rules.
- Monthly and rolling-annual series are distinct series and never share an axis or comparison without explicit labelling.
- An ingestion succeeds only if files downloaded → parsed → validated → committed in **one transaction**; any failure leaves last-known-good data untouched and is recorded.
- Never commit secrets; `data/`, `.env`, `node_modules/`, `dist/` are gitignored. ADE API key (Phase 2) lives only in `.env`.
- Commits are local on the feature branch (conventional prefixes `feat:`/`fix:`/`test:`/`docs:`/`chore:`), each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. No pushes, no force operations.
- Frontend: shadcn/ui components; ECharts charts per the spec's visualisation standards; before frontend work state the taste skill's one-line "Design Read" and apply the sections listed in spec §9 (dials: DESIGN_VARIANCE 5, MOTION_INTENSITY 2, VISUAL_DENSITY 7).

## Review Focus

Failure modes the spec implies that no feature task would otherwise pin; each has a test in the named task:

1. **Block page served as HTTP 200** (Incapsula "Request unsuccessful" HTML, or HTML where CSV/ICS/JSON was expected) must be classified `blocked`, never parsed as data — Task 4.
2. **Release page live but a data file 404/partial** must write nothing and report `not_available`/`failed`, then retry later — Task 9.
3. **Corrected re-publication** (same release, different file bytes) must add a new vintage, set status `corrected`, and never duplicate observations; identical bytes must be a no-op — Task 9.
4. **Negative, zero or sign-flipping values** (net migration is routinely negative) must yield "n/a" percentage changes, not nonsense percentages — Task 2 and Task 11.
5. **First run with an empty database** (and a release with no earlier vintage) must render explicit empty/limitation states, not errors — Tasks 12, 14, 15.

---

## File Structure

```
.github/workflows/ci.yml
.gitignore  .dockerignore  .env.example  Dockerfile  docker-compose.yml
README.md  CLAUDE.md
config/sources.toml
docs/architecture.md  docs/data-sources.md  docs/data-dictionary.md
docs/troubleshooting.md  docs/progress.md
docs/data-sources/migration-vintage-depth.md        (spike output, Task 1)
scripts/capture_fixtures.py  scripts/probe_vintages.py
backend/pyproject.toml
backend/src/nzstats/
  __init__.py  config.py  clock.py  domain.py  models.py  cli.py
  stats/      periods.py changes.py rolling.py percentile.py compat.py revision.py
  store/      db.py repo.py migrations/001_init.sql
  sources/    fetcher.py artifacts.py calendar.py release_page.py
  adapters/   base.py  migration/{__init__,series,parse,adapter}.py
  validate/   rules.py
  pipeline/   discover.py ingest.py
  scheduler/  planner.py jobs.py
  insights/   migration.py
  api/        app.py deps.py routes.py
backend/tests/  conftest.py fixtures/ test_*.py
frontend/       (Vite app; Tasks 13-16)
```

Responsibilities: `stats/` knows only numbers; `adapters/` know file layouts; `store/` is the only SQL; `pipeline/` orchestrates; `insights/` builds deterministic text from stored data; `api/` is read-only; the frontend only calls the API.

---

### Task 0: Scaffold, config, clock, domain types

**Files:**
- Create: `.gitignore`, `.env.example`, `config/sources.toml`, `backend/pyproject.toml`
- Create: `backend/src/nzstats/__init__.py`, `config.py`, `clock.py`, `domain.py`
- Create: `backend/tests/conftest.py`, `test_config.py`, `test_clock.py`

**Interfaces:**
- Produces: `Settings`, `load_settings(env=None) -> Settings`; `clock.AKL`, `parse_akl_naive`, `to_utc_iso`, `from_utc_iso`, `to_akl_iso`, `utc_now`; domain enums/dataclasses used by every later task (defined in Step 6).

- [ ] **Step 1: Create the feature worktree**

Invoke `superpowers:using-git-worktrees`, then (if using the git fallback):

```bash
cd /Users/kevinchang/vault/projects/NZ-Stats-Intelligence-Dashboard
printf '.worktrees/\n' >> .gitignore && git add .gitignore && git commit -m "chore: ignore worktrees

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git worktree add .worktrees/phase-1 -b feat/phase-1
cd .worktrees/phase-1
```

All later commands run inside `.worktrees/phase-1`. Expected: `git branch --show-current` prints `feat/phase-1`.

- [ ] **Step 2: Write `.gitignore`, `.env.example`, `config/sources.toml`**

`.gitignore`:

```gitignore
.worktrees/
data/
.env
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
node_modules/
frontend/dist/
frontend/playwright-report/
frontend/test-results/
.DS_Store
```

`.env.example`:

```dotenv
# Copy to .env. Never commit .env.
NZSTATS_DATA_DIR=./data
# Appended to the User-Agent so Stats NZ can contact the operator.
NZSTATS_CONTACT=you@example.com
# Must be >= 10 (robots.txt crawl-delay).
NZSTATS_MIN_INTERVAL_SECONDS=10
# Phase 2 (optional): Stats NZ API Portal subscription key for the ADE connector.
# STATSNZ_API_KEY=
```

`config/sources.toml`:

```toml
[stats_nz]
base_url = "https://www.stats.govt.nz"
calendar_ics_path = "/release-calendar/calendar-export/"
release_month_path = "/api/v1/releaseCalendarMonth/{month}"
release_page_path = "/information-releases/{slug}/"

[polling]
# Minutes after the scheduled publication time at which a release is polled.
offsets_minutes = [0, 1, 2, 5, 10, 15, 30, 60, 120, 180]
# On startup, releases published within this many days without a vintage are ingested.
catch_up_days = 7

[migration]
country_window_months = 36
# Conservative default (July 2024 files verified). Task 1 may lower it from the vintage-depth spike.
backfill_since = "2024-07"
```

- [ ] **Step 3: Write `backend/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "nzstats"
version = "0.1.0"
description = "NZ Stats Intelligence Dashboard backend"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "pydantic>=2.7",
  "pandas>=2.2",
  "apscheduler>=3.10,<4",
  "tzdata",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6"]

[project.scripts]
nzstats = "nzstats.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
nzstats = ["store/migrations/*.sql"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
# Long string literals are allowed; `ruff format` enforces line-length 100 on code.
ignore = ["E501"]
```

- [ ] **Step 4: Write the failing config and clock tests**

`backend/tests/conftest.py`:

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
```

`backend/tests/test_config.py`:

```python
from pathlib import Path

import pytest

from nzstats.config import load_settings


def test_defaults(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path)})
    assert s.data_dir == tmp_path
    assert s.db_path == tmp_path / "nzstats.db"
    assert s.raw_dir == tmp_path / "raw"
    assert s.base_url == "https://www.stats.govt.nz"
    assert s.min_interval_seconds == 10.0
    assert "NZStatsDashboard" in s.user_agent
    assert s.poll_offsets_minutes[0] == 0
    assert s.country_window_months == 36


def test_contact_is_added_to_user_agent(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_CONTACT": "a@b.co"})
    assert "a@b.co" in s.user_agent


def test_interval_below_crawl_delay_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="crawl-delay"):
        load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_MIN_INTERVAL_SECONDS": "5"})


def test_base_url_override_for_tests(tmp_path: Path) -> None:
    s = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_BASE_URL": "http://x.test/"})
    assert s.base_url == "http://x.test"
```

`backend/tests/test_clock.py`:

```python
from datetime import datetime, timezone

from nzstats.clock import AKL, from_utc_iso, parse_akl_naive, to_akl_iso, to_utc_iso


def test_nzst_conversion() -> None:
    dt = parse_akl_naive("2026-09-14 10:45:00")
    assert to_utc_iso(dt) == "2026-09-13T22:45:00Z"


def test_nzdt_conversion_after_dst_starts() -> None:
    dt = parse_akl_naive("2026-10-14 10:45:00")
    assert to_utc_iso(dt) == "2026-10-13T21:45:00Z"


def test_round_trip_and_akl_iso() -> None:
    utc = "2026-10-13T21:45:00Z"
    assert from_utc_iso(utc) == datetime(2026, 10, 13, 21, 45, tzinfo=timezone.utc)
    assert to_akl_iso(utc) == "2026-10-14T10:45:00+13:00"


def test_naive_datetime_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        to_utc_iso(datetime(2026, 1, 1))


def test_text_ordering_survives_dst_boundary() -> None:
    before = to_utc_iso(parse_akl_naive("2026-09-26 10:45:00"))  # NZST
    after = to_utc_iso(parse_akl_naive("2026-09-28 10:45:00"))  # NZDT
    assert before < after
    assert AKL.key == "Pacific/Auckland"
```

- [ ] **Step 5: Create the venv and run tests to see them fail**

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
pytest tests/test_config.py tests/test_clock.py -v
```

Expected: collection errors, `ModuleNotFoundError: No module named 'nzstats.config'` (package exists once `__init__.py` is created in Step 6; create it first if pip fails).

- [ ] **Step 6: Write the implementation**

`backend/src/nzstats/__init__.py`:

```python
__version__ = "0.1.0"
```

`backend/src/nzstats/clock.py`:

```python
"""Time helpers. Storage is UTC ISO-8601; display is Pacific/Auckland."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

AKL = ZoneInfo("Pacific/Auckland")
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_akl_naive(text: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' (as published by Stats NZ) as Auckland local time."""
    return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=AKL)


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; attach a timezone first")
    return dt.astimezone(timezone.utc).strftime(_UTC_FMT)


def from_utc_iso(text: str) -> datetime:
    return datetime.strptime(text, _UTC_FMT).replace(tzinfo=timezone.utc)


def to_akl_iso(value: str | datetime) -> str:
    dt = from_utc_iso(value) if isinstance(value, str) else value
    return dt.astimezone(AKL).isoformat()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
```

`backend/src/nzstats/config.py`:

```python
"""Runtime settings: environment variables plus config/sources.toml."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MIN_CRAWL_DELAY_SECONDS = 10.0


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    base_url: str
    user_agent: str
    min_interval_seconds: float
    calendar_ics_path: str
    release_month_path: str
    release_page_path: str
    poll_offsets_minutes: tuple[int, ...]
    catch_up_days: int
    country_window_months: int
    backfill_since: str
    static_dir: Path | None = None
    timezone: str = "Pacific/Auckland"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "nzstats.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"


def _default_sources_file() -> Path:
    # <repo>/config/sources.toml, or /app/config/sources.toml in the container.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "sources.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/sources.toml not found; set NZSTATS_SOURCES_FILE")


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    e = os.environ if env is None else env
    sources_file = Path(e.get("NZSTATS_SOURCES_FILE") or _default_sources_file())
    cfg = tomllib.loads(sources_file.read_text(encoding="utf-8"))

    interval = float(e.get("NZSTATS_MIN_INTERVAL_SECONDS", str(MIN_CRAWL_DELAY_SECONDS)))
    if interval < MIN_CRAWL_DELAY_SECONDS:
        raise ValueError("NZSTATS_MIN_INTERVAL_SECONDS must be >= 10 (robots.txt crawl-delay)")

    contact = e.get("NZSTATS_CONTACT", "").strip()
    user_agent = "NZStatsDashboard/0.1 (self-hosted" + (f"; {contact})" if contact else ")")
    static = e.get("NZSTATS_STATIC_DIR")

    return Settings(
        data_dir=Path(e.get("NZSTATS_DATA_DIR", "./data")),
        base_url=e.get("NZSTATS_BASE_URL", cfg["stats_nz"]["base_url"]).rstrip("/"),
        user_agent=user_agent,
        min_interval_seconds=interval,
        calendar_ics_path=cfg["stats_nz"]["calendar_ics_path"],
        release_month_path=cfg["stats_nz"]["release_month_path"],
        release_page_path=cfg["stats_nz"]["release_page_path"],
        poll_offsets_minutes=tuple(cfg["polling"]["offsets_minutes"]),
        catch_up_days=int(cfg["polling"]["catch_up_days"]),
        country_window_months=int(cfg["migration"]["country_window_months"]),
        backfill_since=cfg["migration"]["backfill_since"],
        static_dir=Path(static) if static else None,
    )
```

`backend/src/nzstats/domain.py`:

```python
"""Shared domain types. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Frequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ROLLING_ANNUAL = "rolling_annual"


class Adjustment(StrEnum):
    NONE = "none"
    SEASONALLY_ADJUSTED = "seasonally_adjusted"
    TREND = "trend"


class ObsStatus(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"
    UNKNOWN = "unknown"


class ReleaseStatus(StrEnum):
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    DELAYED = "delayed"
    CORRECTED = "corrected"
    UNAVAILABLE = "unavailable"


class ErrorClass(StrEnum):
    NETWORK = "network"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    LAYOUT_CHANGED = "layout_changed"
    VALIDATION_FAILED = "validation_failed"
    UNEXPECTED = "unexpected"


class IngestError(Exception):
    def __init__(self, error_class: ErrorClass, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.url = url


@dataclass(frozen=True)
class SeriesDef:
    key: str
    name: str
    unit: str
    frequency: Frequency
    adjustment: Adjustment
    definition: str
    definition_id: str  # series sharing a definition_id measure the same concept
    category: str  # e.g. "migration", "migration:country", "migration:region"
    source_url: str | None = None


@dataclass(frozen=True)
class Observation:
    series_key: str
    period: str  # 'YYYY-MM'; for ROLLING_ANNUAL this is the year-ended month
    value: float
    status: ObsStatus
    std_error: float | None = None
    released_in: str | None = None  # 'YYYY-MM' of the release that last published this value


@dataclass(frozen=True)
class Point:
    period: str
    value: float
    status: ObsStatus


@dataclass(frozen=True)
class ReleaseRef:
    release_key: str
    series_slug: str
    title: str
    period_label: str | None
    reference_period: str | None  # 'YYYY-MM' when derivable
    published_at: datetime  # timezone-aware
    status: ReleaseStatus
    page_url: str | None = None
    headline: str | None = None
    statsnz_id: str | None = None
```

- [ ] **Step 7: Run tests to verify they pass, then lint**

Run: `cd backend && pytest tests/test_config.py tests/test_clock.py -v && ruff check . && ruff format --check .`
Expected: all tests PASS; ruff clean (run `ruff format .` first if it reports formatting).

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: scaffold backend, config, clock and domain types

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Real fixtures and vintage-depth spike

**Files:**
- Create: `scripts/capture_fixtures.py`, `scripts/probe_vintages.py`
- Create: `backend/tests/fixtures/*` (written by the script)
- Create: `docs/data-sources/migration-vintage-depth.md` (written by the probe)
- Modify: `config/sources.toml` (`backfill_since`)

**Interfaces:**
- Produces fixture files (names are relied on by Tasks 5–9, 11–12):
  `calendar_export_excerpt.ics`, `release_month_2026-09.json`, `release_month_2026-10.json`,
  `im_2026-07_page.html`, `im_2026-06_page.html`,
  `im_2026-07_age_sex.csv`, `im_2026-06_age_sex.csv`,
  `im_2026-07_citizenship_country.csv`, `im_2026-06_citizenship_country.csv`.

These are the only tasks that touch the live site outside the app. Both scripts self-throttle to 10 s/request and identify themselves.

- [ ] **Step 1: Write `scripts/capture_fixtures.py`**

```python
"""Capture real Stats NZ fixtures for tests. Manual; throttled to 10 s per request.

Usage: python scripts/capture_fixtures.py
Writes excerpts to backend/tests/fixtures/. Excerpts keep real rows; nothing is invented.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

BASE = "https://www.stats.govt.nz"
UA = "NZStatsDashboard-research/0.1 (fixture capture)"
OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
RELEASES = {
    "2026-07": "international-migration-july-2026",
    "2026-06": "international-migration-june-2026",
}


def get(client: httpx.Client, url: str) -> httpx.Response:
    time.sleep(10)
    resp = client.get(url)
    resp.raise_for_status()
    print(f"GET {url} -> {resp.status_code} {len(resp.content)}B", file=sys.stderr)
    return resp


def downloads(page_html: str) -> list[str]:
    text = page_html.replace("\\/", "/")
    found = re.findall(r"/assets/Uploads/[^\"\\\s&]+?\.(?:csv|xlsx)", text)
    return list(dict.fromkeys(found))


def pick(urls: list[str], pattern: str) -> str:
    matches = [u for u in urls if u.endswith(".csv") and re.search(pattern, u.lower())]
    if len(matches) != 1:
        raise SystemExit(f"expected one file matching {pattern!r}, got {matches}")
    return matches[0]


def excerpt_age_sex(raw: bytes, release_month: str) -> str:
    df = pd.read_csv(io.BytesIO(raw))
    total = (df["sex"] == "TOTAL") & (df["age"] == "TOTAL")
    detail = df[(~total) & (df["year_month"] == release_month)].head(60)
    return pd.concat([df[total], detail]).to_csv(index=False, quoting=1)


def excerpt_citizenship_country(raw: bytes) -> str:
    df = pd.read_csv(io.BytesIO(raw))
    vt = df["visa"] == "TOTAL"
    recent_countries = vt & (df["citizenship"] == "TOTAL") & (df["year_month"] >= "2025-06")
    country_total = vt & (df["country_of_residence"] == "TOTAL")
    noise = df[(~vt) & (df["year_month"] == df["year_month"].max())].head(100)
    kept = pd.concat([df[recent_countries | country_total], noise]).drop_duplicates()
    return kept.to_csv(index=False, quoting=1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=120) as client:
        ics = get(client, f"{BASE}/release-calendar/calendar-export/").text
        events = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", ics, flags=re.S)
        head = ics[: ics.index("BEGIN:VEVENT")]
        # Deterministic selection: every migration event plus the earliest others, 12 in total.
        mig = [e for e in events if "SUMMARY:International migration:" in e]
        others = [e for e in events if e not in mig]
        chosen = (mig + others)[:12]
        (OUT / "calendar_export_excerpt.ics").write_text(
            head + "\n".join(chosen) + "\nEND:VCALENDAR\n", encoding="utf-8"
        )

        for month, name in (("2026-09", "release_month_2026-09.json"),
                            ("2026-10", "release_month_2026-10.json")):
            payload = get(client, f"{BASE}/api/v1/releaseCalendarMonth/{month}").json()
            for key in ("published", "upcoming"):
                payload["items"][key] = payload["items"].get(key, [])[:4]
            (OUT / name).write_text(json.dumps(payload, indent=1), encoding="utf-8")

        for month, slug in RELEASES.items():
            page = get(client, f"{BASE}/information-releases/{slug}/").text
            (OUT / f"im_{month}_page.html").write_text(page, encoding="utf-8")
            urls = downloads(page)
            age_sex = pick(urls, r"age.*sex")
            cit = pick(urls, r"citizenship.*visa.*country")
            (OUT / f"im_{month}_age_sex.csv").write_text(
                excerpt_age_sex(get(client, BASE + age_sex).content, month), encoding="utf-8"
            )
            (OUT / f"im_{month}_citizenship_country.csv").write_text(
                excerpt_citizenship_country(get(client, BASE + cit).content), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (about 3 minutes) and inspect the output**

```bash
cd backend && . .venv/bin/activate && python ../scripts/capture_fixtures.py
ls -la tests/fixtures && head -c 400 tests/fixtures/im_2026-07_age_sex.csv && head -20 tests/fixtures/calendar_export_excerpt.ics
```

Expected: nine files; each CSV under ~1 MB; the ICS contains `BEGIN:VTIMEZONE` and 12 `VEVENT`s; `im_2026-07_age_sex.csv` header is `"year_month","month_of_release","passenger_type","direction","sex","age","estimate","standard_error","status"`. If June 2026's page does not yet list files matching the patterns, `pick` exits with the matches it found: report it and use the previous month instead (update `RELEASES` and every later reference to `2026-06`).

- [ ] **Step 3: Write `scripts/probe_vintages.py`**

```python
"""Measure how far back official migration release files exist with the expected layout.

Usage: python scripts/probe_vintages.py 2026-07 2020-09   (newest to oldest, inclusive)
Throttled to 10 s per request; ~30 s per release. Writes docs/data-sources/migration-vintage-depth.md.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx

BASE = "https://www.stats.govt.nz"
UA = "NZStatsDashboard-research/0.1 (vintage-depth probe)"
OUT = Path(__file__).resolve().parents[1] / "docs" / "data-sources" / "migration-vintage-depth.md"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
AGE_SEX_COLS = ('"year_month"', '"month_of_release"', '"passenger_type"', '"direction"',
                '"sex"', '"age"', '"estimate"', '"standard_error"', '"status"')
CIT_COLS = ("year_month", "month_of_release", "passenger_type", "direction", "citizenship",
            "visa", "country_of_residence", "estimate", "standard_error", "status")


def months_desc(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) >= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def throttled(client: httpx.Client, url: str, **kw) -> httpx.Response:
    time.sleep(10)
    return client.get(url, **kw)


def header_line(client: httpx.Client, url: str) -> str | None:
    resp = throttled(client, BASE + url, headers={"Range": "bytes=0-600"})
    if resp.status_code not in (200, 206):
        return None
    return resp.content.decode("utf-8-sig", errors="replace").splitlines()[0]


def main(start: str, end: str) -> None:
    rows = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=120) as c:
        for ym in months_desc(start, end):
            year, month = ym.split("-")
            slug = f"international-migration-{MONTHS[int(month) - 1]}-{year}"
            page = throttled(c, f"{BASE}/information-releases/{slug}/")
            if page.status_code != 200:
                rows.append((ym, f"page {page.status_code}", "-", "-"))
                continue
            text = page.text.replace("\\/", "/")
            urls = list(dict.fromkeys(re.findall(r"/assets/Uploads/[^\"\\\s&]+?\.csv", text)))
            a = next((u for u in urls if re.search(r"age.*sex", u.lower())), None)
            b = next((u for u in urls if re.search(r"citizenship.*visa.*country", u.lower())), None)
            ha = header_line(c, a) if a else None
            hb = header_line(c, b) if b else None
            ok_a = bool(ha) and all(col in ha for col in AGE_SEX_COLS)
            ok_b = bool(hb) and all(col in hb for col in CIT_COLS)
            rows.append((ym, "ok", "ok" if ok_a else f"MISSING/CHANGED ({ha})",
                         "ok" if ok_b else f"MISSING/CHANGED ({hb})"))
            print(rows[-1], file=sys.stderr)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Migration release-file vintage depth", "",
             f"Probed {start} down to {end}. 'ok' = file present and header has all expected columns.",
             "", "| Release | Page | age/sex CSV | citizenship/visa/country CSV |", "|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in rows]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

- [ ] **Step 4: Run the probe in the background and wait for it**

```bash
cd backend && . .venv/bin/activate && python ../scripts/probe_vintages.py 2026-07 2020-09
```

Run with `run_in_background: true` (about 40 minutes); you are notified on completion. Do other plan work only if it does not hit the network.

- [ ] **Step 5: Record the result and set `backfill_since`**

Read `docs/data-sources/migration-vintage-depth.md`. Set `backfill_since` in `config/sources.toml` to the oldest month `M` such that every release from `M` to `2026-07` has both files `ok`. If a gap exists inside the range, use the month after the newest gap. Add a one-paragraph "Findings" section to the report stating that month and any layout changes observed. If fewer than 12 consecutive months qualify, stop and tell Kevin before continuing (the Revision Explorer depends on it).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "test: capture real Stats NZ fixtures and measure vintage depth

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Statistics utilities (pure, TDD)

**Files:**
- Create: `backend/src/nzstats/stats/{__init__,periods,changes,rolling,percentile,compat,revision}.py`
- Test: `backend/tests/stats/test_periods.py`, `test_changes.py`, `test_rolling.py`, `test_percentile.py`, `test_compat.py`, `test_revision.py`

**Interfaces:**
- Consumes: `domain.Point`, `domain.ObsStatus`, `domain.SeriesDef`.
- Produces:
  - `periods`: `parse_month(p) -> tuple[int, int]`, `add_months(p, n) -> str`, `months_between(a, b) -> int`, `month_range(start, end) -> list[str]`, `month_label(p) -> str`
  - `changes`: `abs_change(cur, prev) -> float | None`, `pct_change(cur, prev) -> float | None`, `pp_diff(cur, prev) -> float | None`, `Change`, `lagged_change(series: Mapping[str, float], period: str, lag_months: int) -> Change | None`
  - `rolling`: `rolling_by_period(series: Mapping[str, float], window: int, *, mean: bool = False) -> dict[str, float]`
  - `percentile`: `PercentileContext`, `percentile_context(value: float, history: Sequence[float]) -> PercentileContext | None`
  - `compat`: `IncompatibleSeries`, `check_compatible(a: SeriesDef, b: SeriesDef) -> None`, `compatible(a, b) -> bool`
  - `revision`: `Revision`, `RevisionSummary`, `revisions(original: Mapping[str, Point], revised: Mapping[str, Point]) -> list[Revision]`, `summarise(revs: Sequence[Revision]) -> RevisionSummary`

- [ ] **Step 1: Write the failing tests**

`backend/tests/stats/test_periods.py`:

```python
import pytest

from nzstats.stats.periods import add_months, month_label, month_range, months_between, parse_month


def test_add_months_crosses_year_boundaries() -> None:
    assert add_months("2026-01", -1) == "2025-12"
    assert add_months("2025-12", 1) == "2026-01"
    assert add_months("2026-07", -12) == "2025-07"
    assert add_months("2026-07", 0) == "2026-07"


def test_months_between_and_range() -> None:
    assert months_between("2025-11", "2026-02") == 3
    assert month_range("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert month_range("2026-02", "2025-11") == []


def test_label_and_validation() -> None:
    assert month_label("2026-08") == "August 2026"
    with pytest.raises(ValueError):
        parse_month("2026-13")
    with pytest.raises(ValueError):
        parse_month("nonsense")
```

`backend/tests/stats/test_changes.py`:

```python
import pytest

from nzstats.stats.changes import abs_change, lagged_change, pct_change, pp_diff


@pytest.mark.parametrize(
    ("cur", "prev", "expected"),
    [
        (110.0, 100.0, 10.0),
        (90.0, 100.0, -10.0),
        (0.0, 100.0, -100.0),
        (5.0, 0.0, None),  # zero denominator
        (5.0, None, None),  # missing
        (None, 5.0, None),
        (-5.0, -10.0, None),  # negative base: undefined
        (5.0, -10.0, None),  # sign flip
        (-5.0, 10.0, None),  # sign flip
    ],
)
def test_pct_change_is_only_defined_for_positive_base(cur, prev, expected) -> None:
    result = pct_change(cur, prev)
    assert result == (pytest.approx(expected) if expected is not None else None)


def test_abs_change_handles_negatives_and_missing() -> None:
    assert abs_change(5.0, 3.0) == 2.0
    assert abs_change(-5.0, 3.0) == -8.0
    assert abs_change(None, 3.0) is None
    assert abs_change(5.0, None) is None


def test_pp_diff() -> None:
    assert pp_diff(5.1, 4.9) == pytest.approx(0.2)
    assert pp_diff(None, 4.9) is None


def test_lagged_change_year_on_year() -> None:
    series = {"2025-07": 100.0, "2026-07": 110.0}
    ch = lagged_change(series, "2026-07", 12)
    assert ch is not None
    assert ch.comparison_period == "2025-07"
    assert ch.absolute == 10.0
    assert ch.percent == pytest.approx(10.0)


def test_lagged_change_missing_or_nonpositive_base() -> None:
    assert lagged_change({"2026-07": 1.0}, "2026-07", 12) is None
    ch = lagged_change({"2025-07": -4.0, "2026-07": 6.0}, "2026-07", 12)
    assert ch is not None and ch.absolute == 10.0 and ch.percent is None
```

`backend/tests/stats/test_rolling.py`:

```python
from nzstats.stats.rolling import rolling_by_period


def test_rolling_sum_over_contiguous_months() -> None:
    s = {"2026-01": 1.0, "2026-02": 2.0, "2026-03": 3.0, "2026-04": 4.0}
    assert rolling_by_period(s, 3) == {"2026-03": 6.0, "2026-04": 9.0}


def test_rolling_skips_windows_with_gaps() -> None:
    s = {"2026-01": 1.0, "2026-03": 3.0, "2026-04": 4.0, "2026-05": 5.0}
    assert rolling_by_period(s, 3) == {"2026-05": 12.0}


def test_rolling_mean_and_year_boundary() -> None:
    s = {"2025-12": 2.0, "2026-01": 4.0}
    assert rolling_by_period(s, 2, mean=True) == {"2026-01": 3.0}


def test_window_larger_than_data() -> None:
    assert rolling_by_period({"2026-01": 1.0}, 12) == {}
```

`backend/tests/stats/test_percentile.py`:

```python
import pytest

from nzstats.stats.percentile import percentile_context


def test_highest_value() -> None:
    ctx = percentile_context(5, [1, 2, 3, 4, 5])
    assert ctx is not None
    assert (ctx.rank, ctx.n, ctx.percentile) == (1, 5, 100.0)


def test_middle_value() -> None:
    ctx = percentile_context(3, [1, 2, 3, 4, 5])
    assert ctx is not None
    assert (ctx.rank, ctx.percentile) == (3, 60.0)


def test_ties_share_best_rank() -> None:
    ctx = percentile_context(3, [3, 3, 1])
    assert ctx is not None
    assert ctx.rank == 1 and ctx.percentile == pytest.approx(100.0)


def test_too_little_history() -> None:
    assert percentile_context(3, [3]) is None
    assert percentile_context(3, []) is None
```

`backend/tests/stats/test_compat.py`:

```python
import pytest

from nzstats.domain import Adjustment, Frequency, SeriesDef
from nzstats.stats.compat import IncompatibleSeries, check_compatible, compatible


def _s(key: str, **kw) -> SeriesDef:
    base = dict(
        key=key, name=key, unit="people", frequency=Frequency.MONTHLY,
        adjustment=Adjustment.NONE, definition="d", definition_id="mig", category="migration",
    )
    base.update(kw)
    return SeriesDef(**base)


def test_same_concept_is_compatible() -> None:
    assert compatible(_s("a"), _s("b"))


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"frequency": Frequency.ROLLING_ANNUAL}, "frequency"),
        ({"unit": "percent"}, "unit"),
        ({"adjustment": Adjustment.SEASONALLY_ADJUSTED}, "adjustment"),
        ({"definition_id": "other"}, "definition"),
    ],
)
def test_incompatible_reasons(override, reason) -> None:
    with pytest.raises(IncompatibleSeries, match=reason):
        check_compatible(_s("a"), _s("b", **override))
    assert not compatible(_s("a"), _s("b", **override))
```

`backend/tests/stats/test_revision.py`:

```python
import pytest

from nzstats.domain import ObsStatus, Point
from nzstats.stats.revision import revisions, summarise


def _p(period: str, value: float, status: ObsStatus = ObsStatus.PROVISIONAL) -> Point:
    return Point(period, value, status)


def test_revisions_cover_common_periods_only() -> None:
    orig = {"2026-05": _p("2026-05", 100.0), "2026-06": _p("2026-06", 200.0)}
    rev = {"2026-05": _p("2026-05", 110.0, ObsStatus.FINAL), "2026-07": _p("2026-07", 5.0)}
    out = revisions(orig, rev)
    assert [r.period for r in out] == ["2026-05"]
    r = out[0]
    assert r.absolute == 10.0 and r.percent == pytest.approx(10.0)
    assert (r.original_status, r.revised_status) == (ObsStatus.PROVISIONAL, ObsStatus.FINAL)


def test_percent_is_none_when_not_meaningful() -> None:
    orig = {"2026-05": _p("2026-05", -50.0)}
    rev = {"2026-05": _p("2026-05", 20.0)}
    (r,) = revisions(orig, rev)
    assert r.absolute == 70.0 and r.percent is None


def test_summary() -> None:
    orig = {f"2026-0{i}": _p(f"2026-0{i}", 100.0) for i in range(1, 5)}
    rev = {
        "2026-01": _p("2026-01", 100.0),
        "2026-02": _p("2026-02", 90.0),
        "2026-03": _p("2026-03", 130.0),
        "2026-04": _p("2026-04", 100.0),
    }
    s = summarise(revisions(orig, rev))
    assert s.n_common == 4 and s.n_revised == 2
    assert s.max_abs.period == "2026-03" and s.max_abs.absolute == 30.0
    assert s.mean_abs == pytest.approx(20.0)  # mean over revised periods only


def test_summary_of_nothing() -> None:
    s = summarise([])
    assert s.n_common == 0 and s.n_revised == 0 and s.max_abs is None and s.mean_abs is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/stats -v`
Expected: collection errors, `ModuleNotFoundError: No module named 'nzstats.stats'`.

- [ ] **Step 3: Implement**

`backend/src/nzstats/stats/__init__.py` (empty file).

`stats/periods.py`:

```python
from __future__ import annotations

import calendar


def parse_month(period: str) -> tuple[int, int]:
    try:
        year_s, month_s = period.split("-")
        year, month = int(year_s), int(month_s)
    except ValueError as exc:
        raise ValueError(f"invalid month period: {period!r}") from exc
    if not 1 <= month <= 12 or len(year_s) != 4:
        raise ValueError(f"invalid month period: {period!r}")
    return year, month


def add_months(period: str, n: int) -> str:
    year, month = parse_month(period)
    idx = year * 12 + (month - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(a: str, b: str) -> int:
    ya, ma = parse_month(a)
    yb, mb = parse_month(b)
    return (yb - ya) * 12 + (mb - ma)


def month_range(start: str, end: str) -> list[str]:
    return [add_months(start, i) for i in range(months_between(start, end) + 1)]


def month_label(period: str) -> str:
    year, month = parse_month(period)
    return f"{calendar.month_name[month]} {year}"
```

`stats/changes.py`:

```python
"""Change calculations. Percentages are defined only for a positive base and a non-negative
current value; otherwise None ("n/a") so sign flips never produce misleading percentages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from nzstats.stats.periods import add_months


def abs_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    if previous <= 0 or current < 0:
        return None
    return (current - previous) / previous * 100.0


def pp_diff(current_pct: float | None, previous_pct: float | None) -> float | None:
    """Difference between two percentages, in percentage points."""
    return abs_change(current_pct, previous_pct)


@dataclass(frozen=True)
class Change:
    period: str
    comparison_period: str
    current: float
    previous: float
    absolute: float
    percent: float | None


def lagged_change(series: Mapping[str, float], period: str, lag_months: int) -> Change | None:
    comparison = add_months(period, -lag_months)
    if period not in series or comparison not in series:
        return None
    cur, prev = series[period], series[comparison]
    return Change(period, comparison, cur, prev, cur - prev, pct_change(cur, prev))
```

`stats/rolling.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from nzstats.stats.periods import add_months


def rolling_by_period(
    series: Mapping[str, float], window: int, *, mean: bool = False
) -> dict[str, float]:
    """Rolling sum (or mean) ending at each period; windows containing a missing month are skipped."""
    out: dict[str, float] = {}
    for period in sorted(series):
        months = [add_months(period, -i) for i in range(window)]
        if all(m in series for m in months):
            total = sum(series[m] for m in months)
            out[period] = total / window if mean else total
    return out
```

`stats/percentile.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PercentileContext:
    rank: int  # 1 = highest in history
    n: int
    percentile: float  # share of observations <= value, 0-100


def percentile_context(value: float, history: Sequence[float]) -> PercentileContext | None:
    """`history` must include `value` itself. Rarity is not economic significance."""
    n = len(history)
    if n < 2:
        return None
    higher = sum(1 for v in history if v > value)
    at_or_below = sum(1 for v in history if v <= value)
    return PercentileContext(rank=higher + 1, n=n, percentile=100.0 * at_or_below / n)
```

`stats/compat.py`:

```python
from __future__ import annotations

from nzstats.domain import SeriesDef


class IncompatibleSeries(ValueError):
    """Raised when two series must not be compared or charted together."""


def check_compatible(a: SeriesDef, b: SeriesDef) -> None:
    if a.frequency != b.frequency:
        raise IncompatibleSeries(f"frequency differs: {a.frequency} vs {b.frequency}")
    if a.unit != b.unit:
        raise IncompatibleSeries(f"unit differs: {a.unit} vs {b.unit}")
    if a.adjustment != b.adjustment:
        raise IncompatibleSeries(f"adjustment differs: {a.adjustment} vs {b.adjustment}")
    if a.definition_id != b.definition_id:
        raise IncompatibleSeries(f"definition differs: {a.definition_id} vs {b.definition_id}")


def compatible(a: SeriesDef, b: SeriesDef) -> bool:
    try:
        check_compatible(a, b)
    except IncompatibleSeries:
        return False
    return True
```

`stats/revision.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nzstats.domain import ObsStatus, Point
from nzstats.stats.changes import pct_change


@dataclass(frozen=True)
class Revision:
    period: str
    original: float
    revised: float
    absolute: float
    percent: float | None
    original_status: ObsStatus
    revised_status: ObsStatus


@dataclass(frozen=True)
class RevisionSummary:
    n_common: int
    n_revised: int
    max_abs: Revision | None
    mean_abs: float | None  # mean |revision| over revised periods only


def revisions(original: Mapping[str, Point], revised: Mapping[str, Point]) -> list[Revision]:
    """Revisions for periods present in both vintages, oldest period first."""
    out = []
    for period in sorted(set(original) & set(revised)):
        o, r = original[period], revised[period]
        out.append(
            Revision(
                period=period,
                original=o.value,
                revised=r.value,
                absolute=r.value - o.value,
                percent=pct_change(r.value, o.value),
                original_status=o.status,
                revised_status=r.status,
            )
        )
    return out


def summarise(revs: Sequence[Revision]) -> RevisionSummary:
    changed = [r for r in revs if r.absolute != 0]
    if not changed:
        return RevisionSummary(len(revs), 0, None, None)
    biggest = max(changed, key=lambda r: abs(r.absolute))
    mean_abs = sum(abs(r.absolute) for r in changed) / len(changed)
    return RevisionSummary(len(revs), len(changed), biggest, mean_abs)
```

- [ ] **Step 4: Run to verify pass, lint**

Run: `cd backend && pytest tests/stats -v && ruff check --fix . && ruff format .`
Expected: all PASS (≈30 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add pure statistics utilities with tests

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```


### Task 3: SQLite store (schema, migrations, repositories)

**Files:**
- Create: `backend/src/nzstats/store/{__init__,db,repo}.py`, `backend/src/nzstats/store/migrations/001_init.sql`
- Test: `backend/tests/store/test_db.py`, `backend/tests/store/test_repo.py`
- Modify: `docs/superpowers/specs/2026-10-11-nz-stats-dashboard-design.md` §5 (record the two extra observation columns and `definition_id`)

**Interfaces:**
- Consumes: `domain.*`, `clock.to_utc_iso`.
- Produces (`store/db.py`): `connect(path) -> sqlite3.Connection`, `migrate(conn) -> int`, `transaction(conn)` context manager.
- Produces (`store/repo.py`):
  - `upsert_release(conn, ref: ReleaseRef, now: datetime) -> int`
  - `get_release(conn, release_key: str) -> sqlite3.Row | None`
  - `set_release_status(conn, release_key: str, status: ReleaseStatus, now: datetime) -> None`
  - `set_release_headline(conn, release_key: str, headline: str | None, page_url: str | None) -> None`
  - `upsert_series(conn, d: SeriesDef) -> int`
  - `record_artifact(conn, rec: ArtifactRecord) -> int` (`ArtifactRecord` is defined in this module)
  - `create_vintage(conn, release_id: int, series_id: int, captured_at: datetime, source_kind: str, layout_version: str, bundle_sha256: str) -> int | None`
  - `insert_observations(conn, vintage_id: int, obs: Iterable[Observation]) -> int`
  - `has_vintage(conn, release_id: int, bundle_sha256: str) -> bool`
  - `has_any_vintage(conn, release_id: int) -> bool`
  - `list_vintages(conn, series_key: str) -> list[VintageInfo]` (oldest first by release `published_at`, then vintage id)
  - `vintage_points(conn, vintage_id: int) -> dict[str, Point]`
  - `latest_points(conn, series_key: str) -> dict[str, Point]`
  - `previous_points(conn, series_key: str, published_before: datetime) -> dict[str, Point]`
  - `record_ingest_run(conn, release_key, started_at, finished_at, outcome, error_class, detail) -> int`
  - `set_source_health(conn, source, now, ok: bool, detail: str | None) -> None`
  - `VintageInfo(vintage_id, release_key, title, published_at, captured_at, source_kind, layout_version)`

- [ ] **Step 1: Write the failing tests**

`backend/tests/store/test_db.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from nzstats.store.db import connect, migrate, transaction


def test_migrate_creates_schema_and_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    v1 = migrate(conn)
    v2 = migrate(conn)
    assert v1 == v2 >= 1
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"release", "series", "vintage", "observation", "raw_artifact", "ingest_run",
            "source_health"} <= tables
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO source_health(source, state) VALUES ('x', 'ok')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] == 0


def test_transaction_commits(tmp_path: Path) -> None:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    with transaction(conn):
        conn.execute("INSERT INTO source_health(source, state) VALUES ('x', 'ok')")
    other = sqlite3.connect(tmp_path / "t.db")
    assert other.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] == 1
```

`backend/tests/store/test_repo.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nzstats.clock import parse_akl_naive
from nzstats.domain import (Adjustment, Frequency, ObsStatus, Observation, Point, ReleaseRef,
                            ReleaseStatus, SeriesDef)
from nzstats.store import repo
from nzstats.store.db import connect, migrate, transaction

NOW = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c


def _ref(key="international-migration:august 2026", at="2026-10-14 10:45:00",
         status=ReleaseStatus.SCHEDULED, **kw) -> ReleaseRef:
    return ReleaseRef(
        release_key=key, series_slug="international-migration",
        title="International migration: August 2026", period_label="August 2026",
        reference_period="2026-08", published_at=parse_akl_naive(at), status=status, **kw,
    )


def _series(key="mig.m.net") -> SeriesDef:
    return SeriesDef(key, "Net migration", "people", Frequency.MONTHLY, Adjustment.NONE,
                     "def", "mig", "migration")


def test_upsert_release_is_idempotent(conn) -> None:
    a = repo.upsert_release(conn, _ref(), NOW)
    b = repo.upsert_release(conn, _ref(), NOW)
    assert a == b
    assert conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == 1


def test_published_is_never_downgraded_to_scheduled(conn) -> None:
    repo.upsert_release(conn, _ref(status=ReleaseStatus.PUBLISHED, page_url="http://p"), NOW)
    repo.upsert_release(conn, _ref(status=ReleaseStatus.SCHEDULED), NOW)
    row = repo.get_release(conn, "international-migration:august 2026")
    assert row["status"] == "published" and row["page_url"] == "http://p"


def test_later_scheduled_time_marks_release_delayed(conn) -> None:
    repo.upsert_release(conn, _ref(at="2026-10-14 10:45:00"), NOW)
    repo.upsert_release(conn, _ref(at="2026-10-16 10:45:00"), NOW)
    row = repo.get_release(conn, "international-migration:august 2026")
    assert row["status"] == "delayed"
    assert row["published_at"] == "2026-10-15T21:45:00Z"


def test_vintage_idempotent_and_observations(conn) -> None:
    rid = repo.upsert_release(conn, _ref(), NOW)
    sid = repo.upsert_series(conn, _series())
    with transaction(conn):
        vid = repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", "sha-a")
        n = repo.insert_observations(conn, vid, [
            Observation("mig.m.net", "2026-07", 5170.0, ObsStatus.PROVISIONAL, 545.0, "2026-07"),
            Observation("mig.m.net", "2026-06", 100.0, ObsStatus.FINAL, 0.0, "2020-09"),
        ])
    assert n == 2
    assert repo.has_vintage(conn, rid, "sha-a") and not repo.has_vintage(conn, rid, "sha-b")
    assert repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", "sha-a") is None
    pts = repo.latest_points(conn, "mig.m.net")
    assert pts["2026-07"] == Point("2026-07", 5170.0, ObsStatus.PROVISIONAL)


def test_latest_and_previous_points_follow_release_order(conn) -> None:
    sid = repo.upsert_series(conn, _series())
    june = _ref("im:june", "2026-07-14 10:45:00")
    july = _ref("im:july", "2026-08-14 10:45:00")
    rj = repo.upsert_release(conn, june, NOW)
    rl = repo.upsert_release(conn, july, NOW)
    with transaction(conn):
        # insert the newer release first: ordering must follow publication time, not insert order
        vl = repo.create_vintage(conn, rl, sid, NOW, "release_files", "v1", "s2")
        repo.insert_observations(conn, vl, [Observation("mig.m.net", "2026-05", 120.0,
                                                        ObsStatus.FINAL)])
        vj = repo.create_vintage(conn, rj, sid, NOW, "release_files", "v1", "s1")
        repo.insert_observations(conn, vj, [Observation("mig.m.net", "2026-05", 100.0,
                                                        ObsStatus.PROVISIONAL)])
    assert repo.latest_points(conn, "mig.m.net")["2026-05"].value == 120.0
    before_july = repo.previous_points(conn, "mig.m.net", july.published_at)
    assert before_july["2026-05"].value == 100.0
    assert repo.previous_points(conn, "mig.m.net", june.published_at) == {}
    infos = repo.list_vintages(conn, "mig.m.net")
    assert [i.release_key for i in infos] == ["im:june", "im:july"]


def test_orphan_observation_is_rejected(conn) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO observation(vintage_id, period, value, status) "
                     "VALUES (999, '2026-01', 1, 'final')")


def test_ingest_run_and_health(conn) -> None:
    repo.record_ingest_run(conn, "k", NOW, NOW + timedelta(seconds=3), "failed",
                           "validation_failed", "net != arrivals - departures")
    repo.set_source_health(conn, "calendar_ics", NOW, ok=True, detail=None)
    repo.set_source_health(conn, "calendar_ics", NOW + timedelta(hours=1), ok=False, detail="x")
    row = conn.execute("SELECT * FROM source_health WHERE source='calendar_ics'").fetchone()
    assert row["state"] == "degraded"
    assert row["last_success_at"] == "2026-10-11T03:00:00Z"
    assert row["last_checked_at"] == "2026-10-11T04:00:00Z"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/store -v`
Expected: collection errors, `ModuleNotFoundError: No module named 'nzstats.store'`.

- [ ] **Step 3: Write the schema**

`backend/src/nzstats/store/migrations/001_init.sql`:

```sql
CREATE TABLE raw_artifact (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  http_status INTEGER NOT NULL,
  content_type TEXT,
  size_bytes INTEGER NOT NULL,
  path TEXT NOT NULL,
  UNIQUE (url, sha256)
);

CREATE TABLE release (
  id INTEGER PRIMARY KEY,
  release_key TEXT NOT NULL UNIQUE,
  series_slug TEXT NOT NULL,
  title TEXT NOT NULL,
  period_label TEXT,
  reference_period TEXT,
  published_at TEXT NOT NULL,
  status TEXT NOT NULL,
  page_url TEXT,
  headline TEXT,
  statsnz_id TEXT,
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX release_published_at ON release (published_at);

CREATE TABLE series (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  frequency TEXT NOT NULL,
  seasonal_adjustment TEXT NOT NULL,
  definition TEXT NOT NULL,
  definition_id TEXT NOT NULL,
  category TEXT NOT NULL,
  source_url TEXT
);

CREATE TABLE vintage (
  id INTEGER PRIMARY KEY,
  release_id INTEGER NOT NULL REFERENCES release (id),
  series_id INTEGER NOT NULL REFERENCES series (id),
  captured_at TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('release_files', 'snapshot')),
  layout_version TEXT NOT NULL,
  bundle_sha256 TEXT NOT NULL,
  UNIQUE (release_id, series_id, bundle_sha256)
);
CREATE INDEX vintage_series ON vintage (series_id);

CREATE TABLE observation (
  vintage_id INTEGER NOT NULL REFERENCES vintage (id),
  period TEXT NOT NULL,
  value REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('provisional', 'final', 'unknown')),
  std_error REAL,
  released_in TEXT,
  PRIMARY KEY (vintage_id, period)
) WITHOUT ROWID;

CREATE TABLE ingest_run (
  id INTEGER PRIMARY KEY,
  release_key TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  error_class TEXT,
  detail TEXT
);
CREATE INDEX ingest_run_release ON ingest_run (release_key, started_at);

CREATE TABLE source_health (
  source TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  last_checked_at TEXT,
  last_success_at TEXT,
  detail TEXT
);
```

- [ ] **Step 4: Implement `db.py` and `repo.py`**

`backend/src/nzstats/store/__init__.py` (empty).

`backend/src/nzstats/store/db.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path | str) -> sqlite3.Connection:
    """Autocommit connection (transactions are explicit via `transaction`)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version in applied:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
```

`backend/src/nzstats/store/repo.py`:

```python
"""All SQL lives here. Timestamps in/out are UTC ISO strings (see clock.py)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import to_utc_iso
from nzstats.domain import Observation, ObsStatus, Point, ReleaseRef, ReleaseStatus, SeriesDef


@dataclass(frozen=True)
class ArtifactRecord:
    url: str
    sha256: str
    fetched_at: datetime
    http_status: int
    content_type: str | None
    size_bytes: int
    path: str


@dataclass(frozen=True)
class VintageInfo:
    vintage_id: int
    release_key: str
    title: str
    published_at: str
    captured_at: str
    source_kind: str
    layout_version: str


def upsert_release(conn: sqlite3.Connection, ref: ReleaseRef, now: datetime) -> int:
    now_s, pub = to_utc_iso(now), to_utc_iso(ref.published_at)
    row = conn.execute("SELECT * FROM release WHERE release_key = ?", (ref.release_key,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO release(release_key, series_slug, title, period_label, reference_period,"
            " published_at, status, page_url, headline, statsnz_id, first_seen_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ref.release_key, ref.series_slug, ref.title, ref.period_label, ref.reference_period,
             pub, ref.status.value, ref.page_url, ref.headline, ref.statsnz_id, now_s, now_s),
        )
        return int(cur.lastrowid)

    status = ReleaseStatus(row["status"])
    published_at = row["published_at"]
    if ref.status is ReleaseStatus.PUBLISHED:
        status = ReleaseStatus.PUBLISHED if status is not ReleaseStatus.CORRECTED else status
        published_at = pub
    elif status in (ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED):
        if pub > published_at:
            status = ReleaseStatus.DELAYED
        published_at = pub
    conn.execute(
        "UPDATE release SET title=?, period_label=?, reference_period=?, published_at=?, status=?,"
        " page_url=COALESCE(?, page_url), headline=COALESCE(?, headline),"
        " statsnz_id=COALESCE(?, statsnz_id), updated_at=? WHERE id=?",
        (ref.title, ref.period_label, ref.reference_period, published_at, status.value,
         ref.page_url, ref.headline, ref.statsnz_id, now_s, row["id"]),
    )
    return int(row["id"])


def get_release(conn: sqlite3.Connection, release_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM release WHERE release_key = ?", (release_key,)).fetchone()


def set_release_status(
    conn: sqlite3.Connection, release_key: str, status: ReleaseStatus, now: datetime
) -> None:
    conn.execute("UPDATE release SET status=?, updated_at=? WHERE release_key=?",
                 (status.value, to_utc_iso(now), release_key))


def set_release_headline(
    conn: sqlite3.Connection, release_key: str, headline: str | None, page_url: str | None
) -> None:
    conn.execute(
        "UPDATE release SET headline=COALESCE(?, headline), page_url=COALESCE(?, page_url)"
        " WHERE release_key=?", (headline, page_url, release_key))


def upsert_series(conn: sqlite3.Connection, d: SeriesDef) -> int:
    conn.execute(
        "INSERT INTO series(key, name, unit, frequency, seasonal_adjustment, definition,"
        " definition_id, category, source_url) VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(key) DO UPDATE SET name=excluded.name, unit=excluded.unit,"
        " frequency=excluded.frequency, seasonal_adjustment=excluded.seasonal_adjustment,"
        " definition=excluded.definition, definition_id=excluded.definition_id,"
        " category=excluded.category, source_url=excluded.source_url",
        (d.key, d.name, d.unit, d.frequency.value, d.adjustment.value, d.definition,
         d.definition_id, d.category, d.source_url),
    )
    return int(conn.execute("SELECT id FROM series WHERE key=?", (d.key,)).fetchone()[0])


def record_artifact(conn: sqlite3.Connection, rec: ArtifactRecord) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO raw_artifact(url, sha256, fetched_at, http_status, content_type,"
        " size_bytes, path) VALUES (?,?,?,?,?,?,?)",
        (rec.url, rec.sha256, to_utc_iso(rec.fetched_at), rec.http_status, rec.content_type,
         rec.size_bytes, rec.path),
    )
    return int(conn.execute("SELECT id FROM raw_artifact WHERE url=? AND sha256=?",
                            (rec.url, rec.sha256)).fetchone()[0])


def create_vintage(
    conn: sqlite3.Connection, release_id: int, series_id: int, captured_at: datetime,
    source_kind: str, layout_version: str, bundle_sha256: str,
) -> int | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO vintage(release_id, series_id, captured_at, source_kind,"
        " layout_version, bundle_sha256) VALUES (?,?,?,?,?,?)",
        (release_id, series_id, to_utc_iso(captured_at), source_kind, layout_version,
         bundle_sha256),
    )
    return int(cur.lastrowid) if cur.rowcount else None


def insert_observations(
    conn: sqlite3.Connection, vintage_id: int, obs: Iterable[Observation]
) -> int:
    rows = [(vintage_id, o.period, o.value, o.status.value, o.std_error, o.released_in)
            for o in obs]
    conn.executemany(
        "INSERT INTO observation(vintage_id, period, value, status, std_error, released_in)"
        " VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def has_vintage(conn: sqlite3.Connection, release_id: int, bundle_sha256: str) -> bool:
    return conn.execute("SELECT 1 FROM vintage WHERE release_id=? AND bundle_sha256=? LIMIT 1",
                        (release_id, bundle_sha256)).fetchone() is not None


def has_any_vintage(conn: sqlite3.Connection, release_id: int) -> bool:
    return conn.execute("SELECT 1 FROM vintage WHERE release_id=? LIMIT 1",
                        (release_id,)).fetchone() is not None


_VINTAGE_ORDER = "r.published_at, v.id"


def list_vintages(conn: sqlite3.Connection, series_key: str) -> list[VintageInfo]:
    rows = conn.execute(
        f"SELECT v.id, r.release_key, r.title, r.published_at, v.captured_at, v.source_kind,"
        f" v.layout_version FROM vintage v JOIN release r ON r.id=v.release_id"
        f" JOIN series s ON s.id=v.series_id WHERE s.key=? ORDER BY {_VINTAGE_ORDER}",
        (series_key,)).fetchall()
    return [VintageInfo(*tuple(r)) for r in rows]


def vintage_points(conn: sqlite3.Connection, vintage_id: int) -> dict[str, Point]:
    rows = conn.execute("SELECT period, value, status FROM observation WHERE vintage_id=?"
                        " ORDER BY period", (vintage_id,)).fetchall()
    return {r["period"]: Point(r["period"], r["value"], ObsStatus(r["status"])) for r in rows}


def latest_points(conn: sqlite3.Connection, series_key: str) -> dict[str, Point]:
    infos = list_vintages(conn, series_key)
    return vintage_points(conn, infos[-1].vintage_id) if infos else {}


def previous_points(
    conn: sqlite3.Connection, series_key: str, published_before: datetime
) -> dict[str, Point]:
    cutoff = to_utc_iso(published_before)
    prior = [i for i in list_vintages(conn, series_key) if i.published_at < cutoff]
    return vintage_points(conn, prior[-1].vintage_id) if prior else {}


def record_ingest_run(
    conn: sqlite3.Connection, release_key: str, started_at: datetime, finished_at: datetime,
    outcome: str, error_class: str | None, detail: str | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO ingest_run(release_key, started_at, finished_at, outcome, error_class,"
        " detail) VALUES (?,?,?,?,?,?)",
        (release_key, to_utc_iso(started_at), to_utc_iso(finished_at), outcome, error_class,
         detail))
    return int(cur.lastrowid)


def set_source_health(
    conn: sqlite3.Connection, source: str, now: datetime, *, ok: bool, detail: str | None
) -> None:
    now_s = to_utc_iso(now)
    conn.execute(
        "INSERT INTO source_health(source, state, last_checked_at, last_success_at, detail)"
        " VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET state=excluded.state,"
        " last_checked_at=excluded.last_checked_at,"
        " last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),"
        " detail=excluded.detail",
        (source, "ok" if ok else "degraded", now_s, now_s if ok else None, detail))
```

Note: `insert_observations` inside a failed vintage creation (`vid is None`) is the caller's responsibility; pipeline code (Task 9) checks `create_vintage(...) is None` first.

- [ ] **Step 5: Run to verify pass; lint**

Run: `cd backend && pytest tests/store -v && ruff check --fix . && ruff format .`
Expected: PASS. If `test_orphan_observation_is_rejected` fails, confirm `PRAGMA foreign_keys=ON` ran on that connection (it is set in `connect`).

- [ ] **Step 6: Update spec §5**

In the spec's `series` bullet add `definition_id` (series sharing it measure the same concept; drives comparison compatibility); in the `observation` bullet add `std_error` (as published; 0 on final estimates) and `released_in` (the 'YYYY-MM' release that last published the value, from the source's `month_of_release` column); in `vintage` add `bundle_sha256`; in the data-model intro state that timestamps are stored as UTC ISO-8601.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: add SQLite store with schema, migrations and repositories

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Throttled fetcher and raw artifact store

**Files:**
- Create: `backend/src/nzstats/sources/{__init__,fetcher,artifacts}.py`
- Test: `backend/tests/sources/test_fetcher.py`, `backend/tests/sources/test_artifacts.py`

**Interfaces:**
- Consumes: `domain.ErrorClass`, `domain.IngestError`, `store.repo.ArtifactRecord`, `clock.utc_now`.
- Produces:
  - `FetchResult(url: str, status: int, content_type: str, body: bytes, fetched_at: datetime)`
  - `Fetcher(client: httpx.Client, *, min_interval: float = 10.0, max_retries: int = 3, backoff_base: float = 2.0, sleep=time.sleep, clock=time.monotonic, now=utc_now)` with `.get(url: str, *, expect: tuple[str, ...] = ()) -> FetchResult`
  - `build_client(user_agent: str) -> httpx.Client`
  - `ArtifactStore(raw_dir: Path)` with `.save(result: FetchResult) -> ArtifactRecord`

- [ ] **Step 1: Write the failing tests**

`backend/tests/sources/test_fetcher.py`:

```python
import httpx
import pytest

from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.fetcher import Fetcher


class FakeTime:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _fetcher(handler, ft: FakeTime, **kw) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, sleep=ft.sleep, clock=ft.clock, **kw)


def test_enforces_min_interval_between_requests() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text="x"), ft, min_interval=10.0)
    f.get("http://h.test/a")
    f.get("http://h.test/b")
    assert ft.sleeps == [10.0]  # first request is not delayed; second waits the full interval


def test_waits_only_the_remaining_interval() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text="x"), ft, min_interval=10.0)
    f.get("http://h.test/a")
    ft.t += 4.0
    f.get("http://h.test/b")
    assert ft.sleeps == [6.0]


def test_retries_5xx_then_succeeds() -> None:
    ft = FakeTime()
    calls = iter([503, 502, 200])
    f = _fetcher(lambda r: httpx.Response(next(calls), text="ok"), ft, min_interval=10.0)
    assert f.get("http://h.test/a").status == 200
    assert len(ft.sleeps) >= 2


def test_gives_up_after_max_retries_as_network_error() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(500), ft, max_retries=2)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NETWORK


def test_transport_errors_are_network_errors() -> None:
    def boom(request):
        raise httpx.ConnectError("down")

    ft = FakeTime()
    f = _fetcher(boom, ft, max_retries=1)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NETWORK


def test_404_is_not_found_and_not_retried() -> None:
    ft = FakeTime()
    calls = []
    f = _fetcher(lambda r: (calls.append(1), httpx.Response(404))[1], ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.NOT_FOUND and len(calls) == 1


def test_403_is_blocked_and_not_retried() -> None:
    ft = FakeTime()
    calls = []
    f = _fetcher(lambda r: (calls.append(1), httpx.Response(403))[1], ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a")
    assert e.value.error_class is ErrorClass.BLOCKED and len(calls) == 1


def test_incapsula_challenge_served_as_200_is_blocked() -> None:
    body = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text=body,
                                          headers={"content-type": "text/html"}), ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/a.csv", expect=("text/csv",))
    assert e.value.error_class is ErrorClass.BLOCKED


def test_html_where_data_was_expected_is_blocked() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, text="<html>hi</html>",
                                          headers={"content-type": "text/html; charset=utf-8"}), ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/x.ics", expect=("text/calendar",))
    assert e.value.error_class is ErrorClass.BLOCKED


def test_other_unexpected_content_type() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, content=b"\x00",
                                          headers={"content-type": "image/png"}), ft)
    with pytest.raises(IngestError) as e:
        f.get("http://h.test/x.ics", expect=("text/calendar",))
    assert e.value.error_class is ErrorClass.UNEXPECTED


def test_expected_type_passes_and_returns_body() -> None:
    ft = FakeTime()
    f = _fetcher(lambda r: httpx.Response(200, content=b"a,b\n1,2\n",
                                          headers={"content-type": "text/csv; charset=utf-8"}), ft)
    res = f.get("http://h.test/a.csv", expect=("text/csv",))
    assert res.body == b"a,b\n1,2\n" and res.content_type.startswith("text/csv")
```

`backend/tests/sources/test_artifacts.py`:

```python
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import FetchResult


def _res(body: bytes) -> FetchResult:
    return FetchResult("http://h.test/a.csv", 200, "text/csv", body,
                       datetime(2026, 10, 11, tzinfo=timezone.utc))


def test_save_writes_content_addressed_file(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    rec = store.save(_res(b"hello"))
    sha = hashlib.sha256(b"hello").hexdigest()
    assert rec.sha256 == sha and rec.size_bytes == 5
    assert (tmp_path / rec.path).read_bytes() == b"hello"
    assert rec.path == f"{sha[:2]}/{sha}"


def test_same_bytes_are_stored_once(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    a = store.save(_res(b"same"))
    b = store.save(_res(b"same"))
    assert a.path == b.path
    assert len(list(tmp_path.rglob("*"))) == 2  # one shard dir + one file


def test_different_bytes_get_different_files(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    assert store.save(_res(b"one")).sha256 != store.save(_res(b"two")).sha256
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/sources -v`
Expected: `ModuleNotFoundError: No module named 'nzstats.sources'`.

- [ ] **Step 3: Implement**

`backend/src/nzstats/sources/__init__.py` (empty).

`backend/src/nzstats/sources/fetcher.py`:

```python
"""Polite HTTP: one request at a time, >= min_interval apart, bounded retries, block detection."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from nzstats.clock import utc_now
from nzstats.domain import ErrorClass, IngestError

log = logging.getLogger(__name__)

# Text Imperva/Incapsula puts in its challenge pages (often served with HTTP 200).
BLOCK_MARKERS = (b"Request unsuccessful. Incapsula incident ID",)


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes
    fetched_at: datetime


def build_client(user_agent: str) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent}, follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=15.0),
    )


class Fetcher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        min_interval: float = 10.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._client = client
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._last_request: float | None = None

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)

    def get(self, url: str, *, expect: tuple[str, ...] = ()) -> FetchResult:
        last_problem = "no response"
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(url)
            except httpx.TransportError as exc:
                self._last_request = self._clock()
                last_problem = f"transport error: {exc}"
                log.warning("fetch %s failed (%s), attempt %d", url, last_problem, attempt + 1)
                self._backoff(attempt)
                continue
            self._last_request = self._clock()
            status = resp.status_code
            if status == 404:
                raise IngestError(ErrorClass.NOT_FOUND, f"404 for {url}", url=url)
            if status == 403 or any(m in resp.content[:20000] for m in BLOCK_MARKERS):
                raise IngestError(ErrorClass.BLOCKED, f"blocked ({status}) for {url}", url=url)
            if status == 429 or status >= 500:
                last_problem = f"HTTP {status}"
                log.warning("fetch %s -> %s, attempt %d", url, status, attempt + 1)
                self._backoff(attempt)
                continue
            if status >= 400:
                raise IngestError(ErrorClass.UNEXPECTED, f"HTTP {status} for {url}", url=url)
            ctype = resp.headers.get("content-type", "")
            if expect and not any(ctype.lower().startswith(e) for e in expect):
                cls = ErrorClass.BLOCKED if "html" in ctype.lower() else ErrorClass.UNEXPECTED
                raise IngestError(
                    cls, f"expected {expect} but got {ctype!r} for {url}", url=url)
            return FetchResult(url, status, ctype, resp.content, self._now())
        raise IngestError(ErrorClass.NETWORK, f"gave up on {url}: {last_problem}", url=url)

    def _backoff(self, attempt: int) -> None:
        if attempt < self._max_retries:
            self._sleep(self._backoff_base ** (attempt + 1))
```

`backend/src/nzstats/sources/artifacts.py`:

```python
"""Content-addressed raw artifact storage (raw bytes are kept for audit and reprocessing)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from nzstats.sources.fetcher import FetchResult
from nzstats.store.repo import ArtifactRecord


class ArtifactStore:
    def __init__(self, raw_dir: Path) -> None:
        self._dir = raw_dir

    def save(self, result: FetchResult) -> ArtifactRecord:
        sha = hashlib.sha256(result.body).hexdigest()
        rel = f"{sha[:2]}/{sha}"
        target = self._dir / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(result.body)
            os.replace(tmp, target)
        return ArtifactRecord(
            url=result.url, sha256=sha, fetched_at=result.fetched_at,
            http_status=result.status, content_type=result.content_type,
            size_bytes=len(result.body), path=rel,
        )
```

- [ ] **Step 4: Run to verify pass; lint**

Run: `cd backend && pytest tests/sources -v && ruff check --fix . && ruff format .`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add throttled fetcher with block detection and artifact store

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Calendar sources (ICS, month endpoint, title parsing)

**Files:**
- Create: `backend/src/nzstats/sources/calendar.py`
- Test: `backend/tests/sources/test_calendar.py`

**Interfaces:**
- Consumes: `domain.ReleaseRef`, `domain.ReleaseStatus`, `domain.IngestError`, `domain.ErrorClass`, `clock.AKL`, `clock.parse_akl_naive`, `sources.fetcher.Fetcher`.
- Produces:
  - `TitleParts(series_slug: str, period_label: str | None, reference_period: str | None)`; `parse_title(title: str) -> TitleParts`; `make_release_key(title: str) -> str`
  - `CalendarEvent(uid: str, summary: str, start: datetime)`; `parse_ics(text: str) -> list[CalendarEvent]`
  - `events_to_refs(events: Iterable[CalendarEvent]) -> list[ReleaseRef]` (status `SCHEDULED`)
  - `parse_release_month(payload: Mapping, base_url: str) -> list[ReleaseRef]`
  - `fetch_calendar(fetcher: Fetcher, base_url: str, ics_path: str) -> list[ReleaseRef]`
  - `fetch_release_month(fetcher: Fetcher, base_url: str, path_template: str, month: str) -> list[ReleaseRef]`

Facts from the live probe: ICS lines are `DTSTART;TZID=Pacific/Auckland:20261014T104500`, `SUMMARY:International migration: August 2026`, `UID:8364@https://www.stats.govt.nz/`; the month JSON has `items.published[]` (with `DateTaxonomyTerm.DisplayName`, `DateTaxonomyTerm.PublicationDate` as `'2026-09-14 10:45:00'` Auckland-local, `PageLink`, `MetaDescription`) and `items.upcoming[]` (with `DisplayName`, `PublicationDate`). The join key between sources is the normalised title (`make_release_key`), not any numeric id.

- [ ] **Step 1: Write the failing tests**

`backend/tests/sources/test_calendar.py`:

```python
import json
from datetime import timezone

import httpx
import pytest

from nzstats.clock import to_utc_iso
from nzstats.domain import ErrorClass, IngestError, ReleaseStatus
from nzstats.sources.calendar import (events_to_refs, fetch_calendar, fetch_release_month,
                                      make_release_key, parse_ics, parse_release_month,
                                      parse_title)
from nzstats.sources.fetcher import Fetcher
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.mark.parametrize(
    ("title", "slug", "label", "period"),
    [
        ("International migration: August 2026", "international-migration", "August 2026",
         "2026-08"),
        ("Gross domestic product: June 2026 quarter", "gross-domestic-product",
         "June 2026 quarter", "2026-06"),
        ("Tatauranga umanga Māori – Statistics on Māori businesses",
         "tatauranga-umanga-maori-statistics-on-maori-businesses", None, None),
        ("Consumers price index: September 2026 quarter", "consumers-price-index",
         "September 2026 quarter", "2026-09"),
        ("Household labour force survey estimated working-age population: 2026",
         "household-labour-force-survey-estimated-working-age-population", "2026", None),
    ],
)
def test_parse_title(title, slug, label, period) -> None:
    p = parse_title(title)
    assert (p.series_slug, p.period_label, p.reference_period) == (slug, label, period)


def test_release_key_is_stable_and_case_insensitive() -> None:
    assert make_release_key("International migration: August 2026") == \
        "international-migration:august 2026"
    assert make_release_key("International Migration:  August 2026 ") == \
        make_release_key("International migration: August 2026")


def test_parse_ics_fixture() -> None:
    events = parse_ics(fixture_text("calendar_export_excerpt.ics"))
    assert len(events) == 12
    assert any(e.summary.startswith("International migration:") for e in events)
    assert all(e.start.tzinfo is not None and e.uid for e in events)


def test_parse_ics_converts_auckland_time_across_dst() -> None:
    # Real event shape from the live calendar (14 Oct 2026 is NZDT, UTC+13).
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:8364@https://www.stats.govt.nz/\r\n"
        "DTSTAMP;TZID=Pacific/Auckland:19700101T120000\r\n"
        "DTSTART;TZID=Pacific/Auckland:20261014T104500\r\n"
        "DTEND;TZID=Pacific/Auckland:20261014T104500\r\n"
        "SUMMARY:International migration: August 2026\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    (first,) = parse_ics(text)
    assert first.summary == "International migration: August 2026"
    assert to_utc_iso(first.start) == "2026-10-13T21:45:00Z"
    assert first.uid.startswith("8364@")


def test_parse_ics_handles_folding_escapes_and_utc() -> None:
    text = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1@x\r\n"
        "DTSTART:20261014T214500Z\r\nSUMMARY:Alcohol available for\r\n  consumption\\, "
        "quarterly: June 2026\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:2@x\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    events = parse_ics(text)
    assert len(events) == 1  # the event without SUMMARY/DTSTART is skipped
    assert events[0].summary == "Alcohol available for consumption, quarterly: June 2026"
    assert events[0].start.astimezone(timezone.utc).hour == 21


def test_events_to_refs_are_scheduled() -> None:
    refs = events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
    assert {r.status for r in refs} == {ReleaseStatus.SCHEDULED}
    mig = next(r for r in refs if r.series_slug == "international-migration")
    assert mig.release_key == f"international-migration:{mig.period_label.lower()}"
    assert mig.reference_period and len(mig.reference_period) == 7


def test_parse_release_month_published() -> None:
    sept = json.loads(fixture_text("release_month_2026-09.json"))
    published = [r for r in parse_release_month(sept, BASE) if r.status is ReleaseStatus.PUBLISHED]
    assert published, "fixture should contain published releases"
    p = published[0]
    assert p.page_url.startswith(f"{BASE}/information-releases/")
    assert p.headline and len(p.headline) > 20
    assert p.published_at.tzinfo is not None


def test_parse_release_month_upcoming_shape() -> None:
    payload = {"items": {"published": [], "upcoming": [
        {"DisplayName": "International migration: August 2026",
         "PublicationDate": "2026-10-14 10:45:00"}]}}
    (ref,) = parse_release_month(payload, BASE)
    assert ref.status is ReleaseStatus.SCHEDULED and ref.page_url is None
    assert to_utc_iso(ref.published_at) == "2026-10-13T21:45:00Z"


def test_real_october_fixture_parses() -> None:
    refs = parse_release_month(json.loads(fixture_text("release_month_2026-10.json")), BASE)
    assert {r.status for r in refs} <= {ReleaseStatus.PUBLISHED, ReleaseStatus.SCHEDULED}
    assert all(r.published_at.tzinfo is not None for r in refs)


def test_parse_release_month_rejects_unexpected_shape() -> None:
    with pytest.raises(IngestError) as e:
        parse_release_month({"nope": 1}, BASE)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def _fetcher(handler) -> Fetcher:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fetcher(client, sleep=lambda s: None, clock=lambda: 0.0)


def test_fetch_calendar_requests_ics_and_parses() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(200, text=fixture_text("calendar_export_excerpt.ics"),
                              headers={"content-type": 'text/calendar; name="release-calendar.ics"'})

    refs = fetch_calendar(_fetcher(handler), BASE, "/release-calendar/calendar-export/")
    assert seen == [f"{BASE}/release-calendar/calendar-export/"] and len(refs) == 12


def test_fetch_release_month_formats_path() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return httpx.Response(200, text=fixture_text("release_month_2026-09.json"),
                              headers={"content-type": "application/json"})

    refs = fetch_release_month(_fetcher(handler), BASE, "/api/v1/releaseCalendarMonth/{month}",
                               "2026-09")
    assert seen == [f"{BASE}/api/v1/releaseCalendarMonth/2026-09"] and refs
```

Also create `backend/tests/__init__.py` (empty) so `from tests.conftest import ...` resolves, and add `pythonpath = ["."]` to `[tool.pytest.ini_options]` in `pyproject.toml`.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/sources/test_calendar.py -v`
Expected: `ImportError: cannot import name 'events_to_refs' from 'nzstats.sources.calendar'` (module missing).

- [ ] **Step 3: Implement**

`backend/src/nzstats/sources/calendar.py`:

```python
"""Stats NZ release calendar: ICS export (upcoming) and month endpoint (published + upcoming)."""

from __future__ import annotations

import calendar as _calendar
import json
import logging
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from nzstats.clock import AKL, parse_akl_naive
from nzstats.domain import ErrorClass, IngestError, ReleaseRef, ReleaseStatus
from nzstats.sources.fetcher import Fetcher

log = logging.getLogger(__name__)

_MONTHS = {name.lower(): i for i, name in enumerate(_calendar.month_name) if name}
_MONTH_YEAR = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class TitleParts:
    series_slug: str
    period_label: str | None
    reference_period: str | None


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    start: datetime


def _slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")


def parse_title(title: str) -> TitleParts:
    name, sep, label = title.partition(": ")
    if not sep:
        return TitleParts(_slug(title), None, None)
    label = label.strip()
    match = _MONTH_YEAR.search(label)
    period = f"{int(match.group(2)):04d}-{_MONTHS[match.group(1).lower()]:02d}" if match else None
    return TitleParts(_slug(name), label, period)


def make_release_key(title: str) -> str:
    parts = parse_title(" ".join(title.split()))
    return f"{parts.series_slug}:{(parts.period_label or '').lower()}"


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
            .replace("\\\\", "\\"))


def _parse_dtstart(params: str, value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(AKL)
    if "VALUE=DATE" in params:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=AKL)
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=AKL)


def parse_ics(text: str) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    current: dict[str, object] | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if {"uid", "summary", "start"} <= current.keys():
                events.append(CalendarEvent(current["uid"], current["summary"], current["start"]))
            else:
                log.warning("skipping incomplete VEVENT: %s", sorted(current))
            current = None
        elif current is not None and ":" in line:
            head, _, value = line.partition(":")
            name, _, params = head.partition(";")
            if name == "UID":
                current["uid"] = value.strip()
            elif name == "SUMMARY":
                current["summary"] = _unescape(value).strip()
            elif name == "DTSTART":
                try:
                    current["start"] = _parse_dtstart(params, value)
                except ValueError:
                    log.warning("unparseable DTSTART %r", line)
    return events


def _ref(title: str, published_at: datetime, status: ReleaseStatus, **kw) -> ReleaseRef:
    parts = parse_title(" ".join(title.split()))
    return ReleaseRef(
        release_key=make_release_key(title), series_slug=parts.series_slug, title=title.strip(),
        period_label=parts.period_label, reference_period=parts.reference_period,
        published_at=published_at, status=status, **kw,
    )


def events_to_refs(events: Iterable[CalendarEvent]) -> list[ReleaseRef]:
    return [_ref(e.summary, e.start, ReleaseStatus.SCHEDULED, statsnz_id=e.uid.split("@")[0])
            for e in events]


def parse_release_month(payload: Mapping, base_url: str) -> list[ReleaseRef]:
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, Mapping) or not {"published", "upcoming"} & items.keys():
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "release month payload has no 'items'")
    refs: list[ReleaseRef] = []
    try:
        for p in items.get("published", []):
            term = p["DateTaxonomyTerm"]
            refs.append(_ref(
                term["DisplayName"], parse_akl_naive(term["PublicationDate"]),
                ReleaseStatus.PUBLISHED,
                page_url=base_url + p["PageLink"], headline=(p.get("MetaDescription") or "").strip()
                or None, statsnz_id=str(p.get("ID") or ""),
            ))
        for u in items.get("upcoming", []):
            refs.append(_ref(u["DisplayName"], parse_akl_naive(u["PublicationDate"]),
                             ReleaseStatus.SCHEDULED))
    except (KeyError, TypeError, ValueError) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release month entry malformed: {exc!r}") from exc
    return refs


def fetch_calendar(fetcher: Fetcher, base_url: str, ics_path: str) -> list[ReleaseRef]:
    result = fetcher.get(base_url + ics_path, expect=("text/calendar",))
    refs = events_to_refs(parse_ics(result.body.decode("utf-8")))
    if not refs:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "calendar export contained no events")
    return refs


def fetch_release_month(
    fetcher: Fetcher, base_url: str, path_template: str, month: str
) -> list[ReleaseRef]:
    result = fetcher.get(base_url + path_template.format(month=month),
                         expect=("application/json",))
    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "release month is not JSON") from exc
    return parse_release_month(payload, base_url)
```

- [ ] **Step 4: Run to verify pass; lint**

Run: `cd backend && pytest tests/sources -v && ruff check --fix . && ruff format .`
Expected: PASS. If `test_parse_release_month_published` fails because the fixture lacks a published item with `MetaDescription`, re-run `scripts/capture_fixtures.py` for that month after confirming the live payload keys (do not edit the fixture by hand).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: parse the Stats NZ ICS calendar and release month endpoint

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Release page parser and download classification

**Files:**
- Create: `backend/src/nzstats/sources/release_page.py`
- Test: `backend/tests/sources/test_release_page.py`

**Interfaces:**
- Consumes: `domain.IngestError`, `domain.ErrorClass`, `clock.parse_akl_naive`.
- Produces:
  - `Chart(title: str, csv: str)`
  - `ReleasePage(title: str, published_at: datetime, headline: str | None, charts: tuple[Chart, ...], download_urls: tuple[str, ...])` with method `.chart_starting_with(prefix: str) -> Chart | None`
  - `parse_release_page(html_text: str, base_url: str) -> ReleasePage`
  - `classify_download(url: str) -> str | None` returning `"age_sex"`, `"citizenship_visa_country"`, `"workbook"` or `None`

Facts from the live probe: the page holds JSON in `data-value="…"` attributes (HTML-escaped). The relevant object has keys `Title`, `PageBlocks`, `MetaDescription`, `DateTaxonomyTerm.PublicationDate`. `PageBlocks[].ClassName == "GraphTableBlock"` with `SeriesData[0].Title` and `SeriesData[0].GraphCsvData` (may start with a BOM). Downloads appear as `/assets/Uploads/...csv|xlsx`. File names vary by release (`…-by-age-and-sex.csv` in 2026, `…-by-age-sex.csv` in 2024).

- [ ] **Step 1: Write the failing tests**

`backend/tests/sources/test_release_page.py`:

```python
import pytest

from nzstats.clock import to_utc_iso
from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


def test_basic_fields(page) -> None:
    assert page.title == "International migration: July 2026"
    assert to_utc_iso(page.published_at) == "2026-09-13T22:45:00Z"  # 14 Sep 10:45 NZST
    assert page.headline and "net migration" in page.headline.lower()


def test_charts_are_extracted_with_csv(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    assert chart is not None
    first_line = chart.csv.splitlines()[0]
    assert first_line.startswith('"Year ended"') and "Jul-2026" in first_line
    assert not chart.csv.startswith("﻿")
    monthly = page.chart_starting_with("Estimated migrant arrivals and migrant departures, monthly")
    assert monthly is not None


def test_downloads_are_absolute_and_deduplicated(page) -> None:
    assert len(page.download_urls) == len(set(page.download_urls))
    assert all(u.startswith(f"{BASE}/assets/Uploads/") for u in page.download_urls)
    kinds = {classify_download(u) for u in page.download_urls}
    assert {"age_sex", "citizenship_visa_country", "workbook"} <= kinds


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("/a/international-migration-july-2026-estimated-migration-by-age-and-sex.csv", "age_sex"),
        ("/a/international-migration-july-2024-estimated-migration-by-age-sex.csv", "age_sex"),
        ("/a/international-migration-july-2026-citizenship-by-visa-by-country-of-last-permanent-residence.csv",
         "citizenship_visa_country"),
        ("/a/international-migration-july-2026.xlsx", "workbook"),
        ("/a/estimated-migration-by-direction-monthly.png", None),
        ("/a/something-else.csv", None),
    ],
)
def test_classify_download(url, kind) -> None:
    assert classify_download(url) == kind


def test_page_without_data_blob_is_layout_changed() -> None:
    with pytest.raises(IngestError) as e:
        parse_release_page("<html><body>hello</body></html>", BASE)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/sources/test_release_page.py -v`
Expected: `ModuleNotFoundError: No module named 'nzstats.sources.release_page'`.

- [ ] **Step 3: Implement**

`backend/src/nzstats/sources/release_page.py`:

```python
"""Parse the JSON that Stats NZ release pages embed (data-value attributes)."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import parse_akl_naive
from nzstats.domain import ErrorClass, IngestError

_DATA_VALUE = re.compile(r'data-value="([^"]+)"')
_ASSET = re.compile(r"/assets/Uploads/[^\"\\\s]+?\.(?:csv|xlsx)")


@dataclass(frozen=True)
class Chart:
    title: str
    csv: str


@dataclass(frozen=True)
class ReleasePage:
    title: str
    published_at: datetime
    headline: str | None
    charts: tuple[Chart, ...]
    download_urls: tuple[str, ...]

    def chart_starting_with(self, prefix: str) -> Chart | None:
        return next((c for c in self.charts if c.title.startswith(prefix)), None)


def _find_page_object(html_text: str) -> dict:
    for match in _DATA_VALUE.finditer(html_text):
        raw = html.unescape(match.group(1))
        if not raw.startswith("{") or "PageBlocks" not in raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "PageBlocks" in obj:
            return obj
    raise IngestError(ErrorClass.LAYOUT_CHANGED, "release page has no embedded data object")


def parse_release_page(html_text: str, base_url: str) -> ReleasePage:
    obj = _find_page_object(html_text)
    try:
        term = obj.get("DateTaxonomyTerm") or {}
        published = parse_akl_naive(term.get("PublicationDate") or obj["PageDate"])
        charts = []
        for block in obj["PageBlocks"]:
            if block.get("ClassName") != "GraphTableBlock":
                continue
            for series in block.get("SeriesData") or []:
                csv_text = (series.get("GraphCsvData") or "").lstrip("﻿")
                if csv_text:
                    charts.append(Chart(series.get("Title") or block.get("Title", ""), csv_text))
        urls = list(dict.fromkeys(_ASSET.findall(json.dumps(obj).replace("\\/", "/"))))
        return ReleasePage(
            title=obj["Title"],
            published_at=published,
            headline=(obj.get("MetaDescription") or "").strip() or None,
            charts=tuple(charts),
            download_urls=tuple(base_url + u for u in urls),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release page malformed: {exc!r}") from exc


def classify_download(url: str) -> str | None:
    name = url.rsplit("/", 1)[-1].lower()
    if name.endswith(".xlsx"):
        return "workbook"
    if not name.endswith(".csv"):
        return None
    if re.search(r"age.*sex", name):
        return "age_sex"
    if re.search(r"citizenship.*visa.*country", name):
        return "citizenship_visa_country"
    return None
```

- [ ] **Step 4: Run to verify pass; lint**

Run: `cd backend && pytest tests/sources -v && ruff check --fix . && ruff format .`
Expected: PASS. If the `headline` assertion fails, print `page.headline` and confirm the fixture's `MetaDescription`; adjust the assertion to a phrase that is actually present (e.g. "migration"), never the fixture.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: parse embedded release page data and classify downloads

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```


### Task 7: Migration adapter (CSV and chart parsers, series definitions)

**Files:**
- Create: `backend/src/nzstats/adapters/{__init__,base}.py`
- Create: `backend/src/nzstats/adapters/migration/{__init__,series,parse,adapter}.py`
- Test: `backend/tests/adapters/test_migration_parse.py`, `backend/tests/adapters/test_migration_adapter.py`

**Interfaces:**
- Consumes: `domain.*`, `sources.release_page.ReleasePage`, `slug.slugify`, `stats.periods.add_months`.
- Produces (`adapters/base.py`):
  - `Finding(rule: str, severity: str, message: str)` — severity is `"error"` or `"warning"`
  - `ParsedSeries(definition: SeriesDef, observations: tuple[Observation, ...])`
  - `ParsedBundle(layout_version: str, series: tuple[ParsedSeries, ...])`
  - `Adapter` Protocol: `series_slug: str`, `required_downloads: tuple[str, ...]`, `previous_keys: tuple[str, ...]`, `parse(page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle`, `validate(bundle: ParsedBundle, *, reference_period: str | None, previous: Mapping[str, Mapping[str, Point]]) -> list[Finding]`
- Produces (`adapters/migration/`): `MigrationAdapter(country_window_months: int = 36)`; `parse_age_sex_csv(data: bytes) -> list[ParsedSeries]`; `parse_citizenship_country_csv(data: bytes, *, country_window: int = 36) -> list[ParsedSeries]`; `parse_wide_chart(csv_text: str, mapping: Mapping[str, SeriesDef]) -> list[ParsedSeries]`; `with_rolling_status(ps: ParsedSeries, monthly_status: Mapping[str, ObsStatus]) -> ParsedSeries`; `REGIONS`, `UNALLOCATED`.
- Series keys (relied on by Tasks 8, 11, 12 and the frontend):
  - monthly estimates: `mig.m.arrivals`, `mig.m.departures`, `mig.m.net`
  - published rolling-year: `mig.ry.arrivals`, `mig.ry.departures`, `mig.ry.net`, and by citizenship `mig.ry.{arrivals|departures|net}.{nz|nonnz}`
  - monthly arrivals by citizenship: `mig.m.arrivals.nz`, `mig.m.arrivals.nonnz`
  - arrivals by country of last permanent residence (last `country_window_months` months): `mig.m.arrivals.country.<slug>` (categories `migration:country` and `migration:unallocated` for "Not Stated"); regions `mig.m.arrivals.region.<slug>` (category `migration:region`)

Verified source facts (live files, July 2026): the age/sex CSV columns are `year_month, month_of_release, passenger_type, direction, sex, age, estimate, standard_error, status` with `direction ∈ {Arrivals, Departures, Net}`, totals at `sex == age == "TOTAL"`, `status ∈ {Final, Provisional}` (provisional = the latest 16 months). The citizenship CSV has `year_month, month_of_release, passenger_type, direction, citizenship, visa, country_of_residence, estimate, standard_error, status`, arrivals only, `citizenship ∈ {TOTAL, NZ, non-NZ}`, `visa` and `country_of_residence` each include a `TOTAL` row, and `country_of_residence` mixes five regions (`Asia`, `Europe`, `The Americas`, `Africa and the Middle East`, `Oceania and Antarctica`) and `Not Stated` with countries — regions must never be summed with countries. Chart CSVs are wide: first cell is a label (e.g. `"Year ended"`), then headers like `Dec-2001`, one row per series. Known real values used as spot checks: July 2026 monthly arrivals 13893, departures 8722, net 5170 (SE 434/351/545, provisional, released_in `2026-07`); March 2020 arrivals 16243 (final, released_in `2021-07`); year ended July 2026 rolling arrivals 134434, departures 114084, net 20350; rolling by citizenship July 2026: NZ arrivals 26631, non-NZ 107803, NZ departures 64966, non-NZ 49118, NZ net −38335, non-NZ net 58685; June 2026 India arrivals 1510, Asia 5843.

- [ ] **Step 0: Add the shared slug helper (and use it in Task 5's module)**

Create `backend/src/nzstats/slug.py`:

```python
from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
```

In `sources/calendar.py` delete the local `_slug` function and its `unicodedata` import and use `from nzstats.slug import slugify as _slug`. Add `backend/tests/test_slug.py`:

```python
from nzstats.slug import slugify


def test_slugify() -> None:
    assert slugify("China, People's Republic of") == "china-peoples-republic-of"
    assert slugify("Tatauranga umanga Māori – x") == "tatauranga-umanga-maori-x"
    assert slugify("  Not Stated ") == "not-stated"
```

Run: `cd backend && pytest tests/test_slug.py tests/sources -v` — expected PASS.

- [ ] **Step 1: Write the failing tests**

`backend/tests/adapters/test_migration_parse.py`:

```python
import io

import pandas as pd
import pytest

from nzstats.adapters.migration import series as S
from nzstats.adapters.migration.parse import (REGIONS, parse_age_sex_csv,
                                              parse_citizenship_country_csv, parse_wide_chart,
                                              with_rolling_status)
from nzstats.domain import ErrorClass, IngestError, ObsStatus
from nzstats.sources.release_page import parse_release_page
from nzstats.stats.periods import month_range
from tests.conftest import FIXTURES, fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def age_sex():
    return {p.definition.key: p for p in parse_age_sex_csv(fixture_bytes("im_2026-07_age_sex.csv"))}


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


def _obs(ps, period):
    return next(o for o in ps.observations if o.period == period)


def test_monthly_totals_have_expected_keys_and_contiguous_history(age_sex) -> None:
    assert set(age_sex) == {"mig.m.arrivals", "mig.m.departures", "mig.m.net"}
    periods = [o.period for o in age_sex["mig.m.net"].observations]
    assert periods[0] == "2001-01" and periods[-1] == "2026-07"
    assert periods == month_range("2001-01", "2026-07")


def test_monthly_spot_values_are_real(age_sex) -> None:
    jul = {k: _obs(age_sex[k], "2026-07") for k in age_sex}
    assert (jul["mig.m.arrivals"].value, jul["mig.m.departures"].value, jul["mig.m.net"].value) \
        == (13893.0, 8722.0, 5170.0)
    assert (jul["mig.m.arrivals"].std_error, jul["mig.m.net"].std_error) == (434.0, 545.0)
    assert jul["mig.m.net"].status is ObsStatus.PROVISIONAL
    assert jul["mig.m.net"].released_in == "2026-07"
    mar2020 = _obs(age_sex["mig.m.arrivals"], "2020-03")
    assert (mar2020.value, mar2020.status, mar2020.released_in) == (
        16243.0, ObsStatus.FINAL, "2021-07")


def test_only_total_total_rows_are_used() -> None:
    df = pd.read_csv(FIXTURES / "im_2026-07_age_sex.csv")
    assert (df["sex"] != "TOTAL").any(), "fixture must include non-total rows to test filtering"
    expected = len(df[(df["sex"] == "TOTAL") & (df["age"] == "TOTAL")])
    parsed = parse_age_sex_csv(fixture_bytes("im_2026-07_age_sex.csv"))
    assert sum(len(p.observations) for p in parsed) == expected


def _mutate(name: str, fn) -> bytes:
    df = pd.read_csv(FIXTURES / name)
    return fn(df).to_csv(index=False, quoting=1).encode()


def test_missing_column_is_layout_changed() -> None:
    data = _mutate("im_2026-07_age_sex.csv", lambda d: d.drop(columns=["status"]))
    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(data)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_unknown_status_is_layout_changed() -> None:
    def fn(d):
        d = d.copy()
        d.loc[d.index[0], "status"] = "Estimated"
        return d

    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(_mutate("im_2026-07_age_sex.csv", fn))
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_duplicate_period_is_layout_changed() -> None:
    def fn(d):
        total = d[(d.sex == "TOTAL") & (d.age == "TOTAL") & (d.direction == "Net")].head(1)
        return pd.concat([d, total])

    with pytest.raises(IngestError) as e:
        parse_age_sex_csv(_mutate("im_2026-07_age_sex.csv", fn))
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


@pytest.fixture(scope="module")
def cit():
    data = fixture_bytes("im_2026-07_citizenship_country.csv")
    return {p.definition.key: p for p in parse_citizenship_country_csv(data, country_window=13)}


def test_citizenship_monthly_arrivals_reconcile_with_total(cit, age_sex) -> None:
    nz, nonnz = cit["mig.m.arrivals.nz"], cit["mig.m.arrivals.nonnz"]
    assert nz.observations[-1].period == "2026-07" and len(nz.observations) >= 300
    total = _obs(age_sex["mig.m.arrivals"], "2026-07").value
    assert abs(_obs(nz, "2026-07").value + _obs(nonnz, "2026-07").value - total) <= 2


def test_country_series_window_regions_and_unallocated(cit) -> None:
    india = cit["mig.m.arrivals.country.india"]
    assert india.definition.category == "migration:country"
    assert len(india.observations) <= 13
    assert india.observations[-1].period == "2026-07"
    assert _obs(india, "2026-06").value == 1510.0
    asia = cit["mig.m.arrivals.region.asia"]
    assert asia.definition.category == "migration:region" and _obs(asia, "2026-06").value == 5843.0
    ns = cit["mig.m.arrivals.country.not-stated"]
    assert ns.definition.category == "migration:unallocated"
    assert "mig.m.arrivals.country.total" not in cit
    assert {"Asia", "Europe"} <= REGIONS


def test_wide_chart_rolling_by_direction(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    parsed = {p.definition.key: p for p in parse_wide_chart(chart.csv, S.G1_LABELS)}
    assert set(parsed) == {"mig.ry.arrivals", "mig.ry.departures", "mig.ry.net"}
    last = {k: p.observations[-1] for k, p in parsed.items()}
    assert last["mig.ry.arrivals"].period == "2026-07"
    assert (last["mig.ry.arrivals"].value, last["mig.ry.departures"].value,
            last["mig.ry.net"].value) == (134434.0, 114084.0, 20350.0)
    assert parsed["mig.ry.net"].observations[0].period == "2001-12"
    assert parsed["mig.ry.net"].definition.frequency.value == "rolling_annual"


def test_wide_chart_rolling_by_citizenship(page) -> None:
    chart = page.chart_starting_with("Estimated migration by citizenship, rolling year")
    parsed = {p.definition.key: p for p in parse_wide_chart(chart.csv, S.G3_LABELS)}
    assert len(parsed) == 6
    assert parsed["mig.ry.net.nz"].observations[-1].value == -38335.0
    assert parsed["mig.ry.net.nonnz"].observations[-1].value == 58685.0
    assert parsed["mig.ry.arrivals.nz"].observations[-1].value == 26631.0


def test_wide_chart_missing_label_is_layout_changed(page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    mapping = dict(S.G1_LABELS)
    mapping["Something new"] = S.rolling_def("net", "nz")
    with pytest.raises(IngestError) as e:
        parse_wide_chart(chart.csv, mapping)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED


def test_wide_chart_bad_header_is_layout_changed() -> None:
    with pytest.raises(IngestError):
        parse_wide_chart('"Year ended","not-a-date"\n"Net migration",5\n',
                         {"Net migration": S.rolling_def("net")})


def test_rolling_status_follows_monthly_provisional_window(age_sex, page) -> None:
    chart = page.chart_starting_with("Estimated migration by direction, rolling year")
    net = next(p for p in parse_wide_chart(chart.csv, S.G1_LABELS)
               if p.definition.key == "mig.ry.net")
    monthly = {o.period: o.status for o in age_sex["mig.m.net"].observations}
    out = {o.period: o.status for o in with_rolling_status(net, monthly).observations}
    assert out["2025-03"] is ObsStatus.FINAL  # months 2024-04..2025-03 all final
    assert out["2025-04"] is ObsStatus.PROVISIONAL  # includes provisional 2025-04
    assert out["2026-07"] is ObsStatus.PROVISIONAL
    assert out["2001-12"] is ObsStatus.FINAL
```

`backend/tests/adapters/test_migration_adapter.py`:

```python
import dataclasses

import pytest

from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.domain import ErrorClass, IngestError
from nzstats.sources.release_page import parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"


@pytest.fixture(scope="module")
def page():
    return parse_release_page(fixture_text("im_2026-07_page.html"), BASE)


@pytest.fixture(scope="module")
def files():
    return {"age_sex": fixture_bytes("im_2026-07_age_sex.csv"),
            "citizenship_visa_country": fixture_bytes("im_2026-07_citizenship_country.csv")}


def test_bundle_contains_all_required_series(page, files) -> None:
    bundle = MigrationAdapter().parse(page, files)
    keys = {p.definition.key for p in bundle.series}
    assert {"mig.m.arrivals", "mig.m.departures", "mig.m.net", "mig.ry.arrivals",
            "mig.ry.departures", "mig.ry.net", "mig.ry.net.nz", "mig.ry.net.nonnz",
            "mig.m.arrivals.nz", "mig.m.arrivals.nonnz"} <= keys
    assert len(keys) == len(bundle.series), "series keys must be unique"
    assert bundle.layout_version == "migration-csv-v1"


def test_adapter_declares_its_inputs() -> None:
    a = MigrationAdapter()
    assert a.series_slug == "international-migration"
    assert set(a.required_downloads) == {"age_sex", "citizenship_visa_country"}
    assert "mig.m.net" in a.previous_keys


def test_missing_chart_is_layout_changed(page, files) -> None:
    without = dataclasses.replace(page, charts=())
    with pytest.raises(IngestError) as e:
        MigrationAdapter().parse(without, files)
    assert e.value.error_class is ErrorClass.LAYOUT_CHANGED
```

Create empty `backend/tests/adapters/__init__.py`? Not needed (pytest rootdir `tests` has `__init__.py`; add `__init__.py` to each test subpackage you create: `tests/stats`, `tests/store`, `tests/sources`, `tests/adapters`, `tests/validate`, `tests/pipeline`, `tests/scheduler`, `tests/insights`, `tests/api` so duplicate module basenames never collide).

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/adapters -v`
Expected: `ModuleNotFoundError: No module named 'nzstats.adapters'`.

- [ ] **Step 3: Implement**

`backend/src/nzstats/adapters/__init__.py` (empty). `backend/src/nzstats/adapters/migration/__init__.py` (empty).

`adapters/base.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from nzstats.domain import Observation, Point, SeriesDef
from nzstats.sources.release_page import ReleasePage


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "error" blocks ingestion; "warning" is recorded only
    message: str


@dataclass(frozen=True)
class ParsedSeries:
    definition: SeriesDef
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class ParsedBundle:
    layout_version: str
    series: tuple[ParsedSeries, ...]


class Adapter(Protocol):
    series_slug: str
    required_downloads: tuple[str, ...]
    previous_keys: tuple[str, ...]  # series whose previous vintage is loaded for validation

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle: ...

    def validate(
        self,
        bundle: ParsedBundle,
        *,
        reference_period: str | None,
        previous: Mapping[str, Mapping[str, Point]],
    ) -> list[Finding]: ...
```

`adapters/migration/series.py`:

```python
"""Series definitions for International migration (outcomes-based long-term migrants)."""

from __future__ import annotations

from nzstats.domain import Adjustment, Frequency, SeriesDef
from nzstats.slug import slugify

DEFINITION_ID = "migration.outcomes_based_long_term"
OUTCOMES_DEFINITION = (
    "Long-term migrant movements under Stats NZ's outcomes-based measure (a traveller is counted "
    "as a migrant if they spend 12 of the following 16 months in, or out of, New Zealand). Mean "
    "estimates, in people. Estimates for the most recent months are provisional and are revised "
    "as travel outcomes become known."
)
_NAME = {"arrivals": "Migrant arrivals", "departures": "Migrant departures",
         "net": "Net migration"}
_CIT = {"nz": "NZ citizens", "nonnz": "non-NZ citizens"}


def monthly_def(direction: str) -> SeriesDef:
    return SeriesDef(
        key=f"mig.m.{direction}", name=f"{_NAME[direction]} (monthly estimate)", unit="people",
        frequency=Frequency.MONTHLY, adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION, definition_id=DEFINITION_ID, category="migration",
    )


def rolling_def(direction: str, citizenship: str | None = None) -> SeriesDef:
    key = f"mig.ry.{direction}" + (f".{citizenship}" if citizenship else "")
    who = f", {_CIT[citizenship]}" if citizenship else ""
    return SeriesDef(
        key=key, name=f"{_NAME[direction]}{who} (year ended)", unit="people",
        frequency=Frequency.ROLLING_ANNUAL, adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION + " Rolling twelve-month total, as published by Stats NZ.",
        definition_id=DEFINITION_ID, category="migration",
    )


def citizenship_monthly_def(citizenship: str) -> SeriesDef:
    return SeriesDef(
        key=f"mig.m.arrivals.{citizenship}",
        name=f"Migrant arrivals, {_CIT[citizenship]} (monthly estimate)", unit="people",
        frequency=Frequency.MONTHLY, adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION, definition_id=DEFINITION_ID, category="migration",
    )


def country_def(name: str, kind: str) -> SeriesDef:
    prefix = "region" if kind == "region" else "country"
    category = {"country": "migration:country", "region": "migration:region",
                "unallocated": "migration:unallocated"}[kind]
    return SeriesDef(
        key=f"mig.m.arrivals.{prefix}.{slugify(name)}",
        name=f"Migrant arrivals from {name} (monthly estimate)", unit="people",
        frequency=Frequency.MONTHLY, adjustment=Adjustment.NONE,
        definition=OUTCOMES_DEFINITION + " Place is the country of last permanent residence.",
        definition_id=DEFINITION_ID, category=category,
    )


G1_LABELS = {
    "Migrant arrivals": rolling_def("arrivals"),
    "Migrant departures": rolling_def("departures"),
    "Net migration": rolling_def("net"),
}
G3_LABELS = {
    "Migrant arrivals (NZ citizens)": rolling_def("arrivals", "nz"),
    "Migrant arrivals (non-NZ citizens)": rolling_def("arrivals", "nonnz"),
    "Migrant departures (NZ citizens)": rolling_def("departures", "nz"),
    "Migrant departures (non-NZ citizens)": rolling_def("departures", "nonnz"),
    "Net migration (NZ citizens)": rolling_def("net", "nz"),
    "Net migration (non-NZ citizens)": rolling_def("net", "nonnz"),
}
ROLLING_DIRECTION_CHART = "Estimated migration by direction, rolling year"
ROLLING_CITIZENSHIP_CHART = "Estimated migration by citizenship, rolling year"
```

`adapters/migration/parse.py`:

```python
from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime

import pandas as pd

from nzstats.adapters.base import ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.domain import ErrorClass, IngestError, Observation, ObsStatus, SeriesDef
from nzstats.stats.periods import add_months

REGIONS = frozenset({
    "Asia", "Europe", "The Americas", "Africa and the Middle East", "Oceania and Antarctica",
})
UNALLOCATED = frozenset({"Not Stated"})

AGE_SEX_COLUMNS = ["year_month", "month_of_release", "passenger_type", "direction", "sex", "age",
                   "estimate", "standard_error", "status"]
CITIZENSHIP_COLUMNS = ["year_month", "month_of_release", "passenger_type", "direction",
                       "citizenship", "visa", "country_of_residence", "estimate",
                       "standard_error", "status"]
_DIRECTIONS = {"Arrivals": "arrivals", "Departures": "departures", "Net": "net"}
_STATUS = {"Final": ObsStatus.FINAL, "Provisional": ObsStatus.PROVISIONAL}


def _layout(message: str) -> IngestError:
    return IngestError(ErrorClass.LAYOUT_CHANGED, message)


def _status(value: str) -> ObsStatus:
    try:
        return _STATUS[value]
    except KeyError:
        raise _layout(f"unknown status value {value!r}") from None


def _read(data: bytes, columns: Sequence[str], name: str) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(data), usecols=list(columns), dtype={"year_month": str,
                                                                          "month_of_release": str})
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise _layout(f"{name}: unreadable or missing expected columns ({exc})") from exc


def _observations(key: str, frame: pd.DataFrame) -> tuple[Observation, ...]:
    frame = frame.sort_values("year_month")
    if not frame["year_month"].is_unique:
        raise _layout(f"{key}: duplicate periods in source")
    return tuple(
        Observation(key, r.year_month, float(r.estimate), _status(r.status),
                    float(r.standard_error), r.month_of_release)
        for r in frame.itertuples(index=False)
    )


def parse_age_sex_csv(data: bytes) -> list[ParsedSeries]:
    df = _read(data, AGE_SEX_COLUMNS, "age/sex csv")
    df = df[(df["sex"] == "TOTAL") & (df["age"] == "TOTAL")
            & (df["passenger_type"] == "Long-term migrant")]
    out = []
    for direction, label in _DIRECTIONS.items():
        sub = df[df["direction"] == direction]
        if sub.empty:
            continue
        definition = S.monthly_def(label)
        out.append(ParsedSeries(definition, _observations(definition.key, sub)))
    return out


def parse_citizenship_country_csv(data: bytes, *, country_window: int = 36) -> list[ParsedSeries]:
    df = _read(data, CITIZENSHIP_COLUMNS, "citizenship/country csv")
    base = df[(df["visa"] == "TOTAL") & (df["passenger_type"] == "Long-term migrant")
              & (df["direction"] == "Arrivals")]
    if base.empty:
        raise _layout("citizenship csv has no arrivals rows with visa == TOTAL")
    out: list[ParsedSeries] = []
    for citizenship, label in (("NZ", "nz"), ("non-NZ", "nonnz")):
        sub = base[(base["citizenship"] == citizenship) & (base["country_of_residence"] == "TOTAL")]
        if not sub.empty:
            definition = S.citizenship_monthly_def(label)
            out.append(ParsedSeries(definition, _observations(definition.key, sub)))
    cutoff = add_months(str(base["year_month"].max()), -(country_window - 1))
    places = base[(base["citizenship"] == "TOTAL") & (base["country_of_residence"] != "TOTAL")
                  & (base["year_month"] >= cutoff)]
    seen: dict[str, str] = {}
    for name, group in places.groupby("country_of_residence", sort=True):
        kind = "region" if name in REGIONS else "unallocated" if name in UNALLOCATED else "country"
        definition = S.country_def(str(name), kind)
        if definition.key in seen:
            raise _layout(f"series key collision {definition.key}: {name!r} vs {seen[definition.key]!r}")
        seen[definition.key] = str(name)
        out.append(ParsedSeries(definition, _observations(definition.key, group)))
    return out


def _chart_period(header: str) -> str:
    try:
        return datetime.strptime(header.strip(), "%b-%Y").strftime("%Y-%m")
    except ValueError:
        raise _layout(f"unexpected chart column header {header!r}") from None


def parse_wide_chart(csv_text: str, mapping: Mapping[str, SeriesDef]) -> list[ParsedSeries]:
    rows = list(csv.reader(io.StringIO(csv_text.lstrip("﻿"))))
    if len(rows) < 2:
        raise _layout("chart csv has no data rows")
    periods = [_chart_period(h) for h in rows[0][1:]]
    found: dict[str, ParsedSeries] = {}
    for row in rows[1:]:
        if not row:
            continue
        definition = mapping.get(row[0].strip())
        if definition is None:
            continue
        observations = []
        for period, cell in zip(periods, row[1:], strict=False):
            cell = cell.strip()
            if cell in ("", "..", "…"):
                continue
            try:
                observations.append(Observation(definition.key, period, float(cell),
                                                ObsStatus.UNKNOWN))
            except ValueError:
                raise _layout(f"non-numeric chart value {cell!r} for {definition.key}") from None
        found[row[0].strip()] = ParsedSeries(definition, tuple(observations))
    missing = [label for label in mapping if label not in found]
    if missing:
        raise _layout(f"chart is missing expected series: {missing}")
    return [found[label] for label in mapping]


def with_rolling_status(ps: ParsedSeries, monthly_status: Mapping[str, ObsStatus]) -> ParsedSeries:
    """A year-ended value is provisional if any of its twelve months is provisional."""
    out = []
    for obs in ps.observations:
        statuses = [monthly_status.get(add_months(obs.period, -i)) for i in range(12)]
        if any(s is None for s in statuses):
            status = ObsStatus.UNKNOWN
        elif any(s is ObsStatus.PROVISIONAL for s in statuses):
            status = ObsStatus.PROVISIONAL
        else:
            status = ObsStatus.FINAL
        out.append(replace(obs, status=status))
    return replace(ps, observations=tuple(out))
```

`adapters/migration/adapter.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from nzstats.adapters.base import Finding, ParsedBundle, ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.adapters.migration.parse import (parse_age_sex_csv, parse_citizenship_country_csv,
                                              parse_wide_chart, with_rolling_status)
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
        places = parse_citizenship_country_csv(files["citizenship_visa_country"],
                                               country_window=self._window)
        net = next((p for p in monthly if p.definition.key == "mig.m.net"), None)
        if net is None:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "age/sex csv has no Net series")
        status = {o.period: o.status for o in net.observations}
        rolling: list[ParsedSeries] = []
        for prefix, labels in ((S.ROLLING_DIRECTION_CHART, S.G1_LABELS),
                               (S.ROLLING_CITIZENSHIP_CHART, S.G3_LABELS)):
            chart = page.chart_starting_with(prefix)
            if chart is None:
                raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release page has no chart {prefix!r}")
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
```

(`validate.rules` is created in Task 8; Step 4 below stubs nothing — run Task 7's parse tests first with `pytest tests/adapters/test_migration_parse.py`, and run the adapter test after Task 8 exists. To keep each task green on its own, create `validate/__init__.py` and a one-line `validate/rules.py` containing `def validate_migration(*a, **k): return []` now; Task 8 replaces it with the real rules.)

- [ ] **Step 4: Run to verify pass; lint**

Run: `cd backend && pytest tests/adapters tests/test_slug.py -v && ruff check --fix . && ruff format .`
Expected: PASS. A failing spot-check value means the fixture or the parser is wrong: inspect the fixture row with pandas before changing any expected number (the numbers above come from the real July 2026 files).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add migration adapter with CSV and chart parsers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Validation rules

**Files:**
- Create/replace: `backend/src/nzstats/validate/{__init__,rules}.py`
- Test: `backend/tests/validate/test_rules.py`

**Interfaces:**
- Consumes: `adapters.base.{Finding, ParsedBundle, ParsedSeries}`, `domain.*`, `stats.periods.month_range`, `stats.rolling.rolling_by_period`.
- Produces: `validate_migration(bundle: ParsedBundle, *, reference_period: str | None, previous: Mapping[str, Mapping[str, Point]]) -> list[Finding]`; module constants `NET_IDENTITY_TOLERANCE = 2.0`, `ROLLING_TOLERANCE = 5.0`, `BIG_REVISION = 0.25`, `MAX_BIG_REVISION_SHARE = 0.10`, `REVISION_FLOOR = 100.0`, `PROVISIONAL_MAX_MONTHS = 16`.

Thresholds are grounded in measured real data: monthly `Net` equals `Arrivals − Departures` to within 1 (rounding); derived twelve-month sums match published rolling-year figures to within 2 (July 2026: arrivals exact, departures 1, net 2). If a rule ever rejects a real release, investigate with `superpowers:systematic-debugging`; do not loosen a threshold without evidence from the failing file.

- [ ] **Step 1: Write the failing tests**

`backend/tests/validate/test_rules.py`:

```python
import dataclasses
import math

import pytest

from nzstats.adapters.base import ParsedBundle, ParsedSeries
from nzstats.adapters.migration import series as S
from nzstats.domain import ObsStatus, Observation, Point
from nzstats.stats.periods import month_range
from nzstats.validate.rules import validate_migration

PERIODS = month_range("2024-08", "2026-07")  # 24 months


def _ps(definition, values: dict[str, float], status=ObsStatus.FINAL) -> ParsedSeries:
    return ParsedSeries(definition, tuple(
        Observation(definition.key, p, v, status) for p, v in values.items()))


def good_bundle(**overrides) -> ParsedBundle:
    """Tiny internally consistent bundle (test input, never production data)."""
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    net = {p: arr[p] - dep[p] for p in PERIODS}
    ry = {}
    for name, series in (("arrivals", arr), ("departures", dep), ("net", net)):
        ry[name] = {PERIODS[i]: sum(series[p] for p in PERIODS[i - 11:i + 1])
                    for i in range(11, 24)}
    nz = {p: arr[p] * 0.3 for p in PERIODS}
    nonnz = {p: arr[p] * 0.7 for p in PERIODS}
    latest = PERIODS[-1]
    a_total = arr[latest]
    series = {
        "mig.m.arrivals": _ps(S.monthly_def("arrivals"), arr),
        "mig.m.departures": _ps(S.monthly_def("departures"), dep),
        "mig.m.net": _ps(S.monthly_def("net"), net),
        "mig.ry.arrivals": _ps(S.rolling_def("arrivals"), ry["arrivals"]),
        "mig.ry.departures": _ps(S.rolling_def("departures"), ry["departures"]),
        "mig.ry.net": _ps(S.rolling_def("net"), ry["net"]),
        "mig.ry.net.nz": _ps(S.rolling_def("net", "nz"), {latest: -100.0}),
        "mig.ry.net.nonnz": _ps(S.rolling_def("net", "nonnz"), {latest: 500.0}),
        "mig.m.arrivals.nz": _ps(S.citizenship_monthly_def("nz"), nz),
        "mig.m.arrivals.nonnz": _ps(S.citizenship_monthly_def("nonnz"), nonnz),
        "mig.m.arrivals.country.a": _ps(S.country_def("A", "country"),
                                        {latest: round(a_total * 0.6)}),
        "mig.m.arrivals.country.b": _ps(S.country_def("B", "country"),
                                        {latest: a_total - round(a_total * 0.6)}),
        "mig.m.arrivals.region.asia": _ps(S.country_def("Asia", "region"), {latest: 1.0}),
    }
    series.update(overrides)
    return ParsedBundle("test", tuple(series.values()))


def _rules(findings, severity="error"):
    return {f.rule for f in findings if f.severity == severity}


def run(bundle=None, reference="2026-07", previous=None):
    return validate_migration(bundle or good_bundle(), reference_period=reference,
                              previous=previous or {})


def test_consistent_bundle_has_no_errors() -> None:
    assert _rules(run()) == set()


def test_missing_required_series() -> None:
    b = good_bundle()
    b = dataclasses.replace(b, series=tuple(
        p for p in b.series if p.definition.key != "mig.ry.net"))
    assert "required_series" in _rules(run(b))


def test_gap_in_monthly_history() -> None:
    values = {p: 1.0 for p in PERIODS if p != "2025-03"}
    b = good_bundle(**{"mig.m.departures": _ps(S.monthly_def("departures"), values)})
    assert "continuity" in _rules(run(b))


@pytest.mark.parametrize(("reference", "expect_error"),
                         [("2026-07", False), ("2026-08", True), (None, False)])
def test_latest_period_must_match_release(reference, expect_error) -> None:
    assert ("latest_period" in _rules(run(reference=reference))) is expect_error


def test_net_identity_tolerance() -> None:
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    ok = {p: arr[p] - dep[p] + (1 if p == "2025-01" else 0) for p in PERIODS}
    bad = {p: arr[p] - dep[p] + (3 if p == "2025-01" else 0) for p in PERIODS}
    assert "net_identity" not in _rules(run(good_bundle(**{
        "mig.m.net": _ps(S.monthly_def("net"), ok)})))
    assert "net_identity" in _rules(run(good_bundle(**{
        "mig.m.net": _ps(S.monthly_def("net"), bad)})))


def test_rolling_published_must_match_derived() -> None:
    base = good_bundle()
    ry = next(p for p in base.series if p.definition.key == "mig.ry.net")
    latest = ry.observations[-1]

    def shifted(delta: float) -> ParsedBundle:
        obs = ry.observations[:-1] + (dataclasses.replace(latest, value=latest.value + delta),)
        return good_bundle(**{"mig.ry.net": dataclasses.replace(ry, observations=obs)})

    assert "rolling_check" not in _rules(run(shifted(5.0)))
    assert "rolling_check" in _rules(run(shifted(6.0)))


def test_non_finite_values_rejected() -> None:
    values = {p: 1.0 for p in PERIODS}
    values["2026-07"] = math.nan
    b = good_bundle(**{"mig.m.arrivals": _ps(S.monthly_def("arrivals"), values)})
    assert "finite" in _rules(run(b))


def test_implausible_revisions_vs_previous_vintage() -> None:
    b = good_bundle()
    arr = next(p for p in b.series if p.definition.key == "mig.m.arrivals")
    halved = {o.period: Point(o.period, o.value * 0.5, ObsStatus.FINAL) for o in arr.observations}
    assert "revision_plausibility" in _rules(run(b, previous={"mig.m.arrivals": halved}))
    modest = {o.period: Point(o.period, o.value * 0.97, ObsStatus.FINAL)
              for o in arr.observations}
    assert "revision_plausibility" not in _rules(run(b, previous={"mig.m.arrivals": modest}))


def test_first_release_without_previous_is_fine() -> None:
    assert "revision_plausibility" not in _rules(run(previous={}))


def test_country_sum_must_reconcile_with_total() -> None:
    b = good_bundle()
    latest = PERIODS[-1]
    bad = good_bundle(**{"mig.m.arrivals.country.b": _ps(S.country_def("B", "country"),
                                                         {latest: 1.0})})
    assert "country_sum" not in _rules(run(b))
    assert "country_sum" in _rules(run(bad))


def test_regions_are_excluded_from_country_sum() -> None:
    latest = PERIODS[-1]
    huge_region = good_bundle(**{"mig.m.arrivals.region.asia": _ps(
        S.country_def("Asia", "region"), {latest: 999999.0})})
    assert "country_sum" not in _rules(run(huge_region))


def test_overlong_provisional_window_is_only_a_warning() -> None:
    arr = {p: 10000.0 + i * 10 for i, p in enumerate(PERIODS)}
    dep = {p: 8000.0 + i * 5 for i, p in enumerate(PERIODS)}
    net = {p: arr[p] - dep[p] for p in PERIODS}
    prov = good_bundle(**{"mig.m.net": ParsedSeries(S.monthly_def("net"), tuple(
        Observation("mig.m.net", p, v, ObsStatus.PROVISIONAL) for p, v in net.items()))})
    findings = run(prov)
    assert "provisional_window" in _rules(findings, "warning")
    assert "provisional_window" not in _rules(findings, "error")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/validate -v`
Expected: FAIL (the stub returns `[]`, so `test_missing_required_series` etc. fail).

- [ ] **Step 3: Implement**

`backend/src/nzstats/validate/rules.py` (replace the stub):

```python
"""Structural and sanity checks. Errors block ingestion; warnings are recorded only."""

from __future__ import annotations

import math
from collections.abc import Mapping

from nzstats.adapters.base import Finding, ParsedBundle
from nzstats.domain import ObsStatus, Point
from nzstats.stats.periods import month_range
from nzstats.stats.rolling import rolling_by_period

NET_IDENTITY_TOLERANCE = 2.0
ROLLING_TOLERANCE = 5.0
BIG_REVISION = 0.25
MAX_BIG_REVISION_SHARE = 0.10
REVISION_FLOOR = 100.0
PROVISIONAL_MAX_MONTHS = 16
COUNTRY_TOLERANCE_ABS = 20.0
COUNTRY_TOLERANCE_REL = 0.01
MIN_HISTORY_MONTHS = 12

MONTHLY = ("mig.m.arrivals", "mig.m.departures", "mig.m.net")
ROLLING = ("mig.ry.arrivals", "mig.ry.departures", "mig.ry.net")
REQUIRED = MONTHLY + ROLLING + (
    "mig.ry.net.nz", "mig.ry.net.nonnz", "mig.m.arrivals.nz", "mig.m.arrivals.nonnz")


def validate_migration(
    bundle: ParsedBundle,
    *,
    reference_period: str | None,
    previous: Mapping[str, Mapping[str, Point]],
) -> list[Finding]:
    findings: list[Finding] = []

    def error(rule: str, message: str) -> None:
        findings.append(Finding(rule, "error", message))

    by_key = {ps.definition.key: ps for ps in bundle.series}
    for key in REQUIRED:
        if key not in by_key:
            error("required_series", f"required series missing: {key}")
    if findings:
        return findings

    for ps in bundle.series:
        bad = [o.period for o in ps.observations if not math.isfinite(o.value)]
        if bad:
            error("finite", f"{ps.definition.key}: non-finite values at {bad[:3]}")

    values = {k: {o.period: o.value for o in ps.observations} for k, ps in by_key.items()}

    for key in MONTHLY:
        periods = sorted(values[key])
        if len(periods) < MIN_HISTORY_MONTHS:
            error("history", f"{key}: only {len(periods)} months of history")
            continue
        expected = month_range(periods[0], periods[-1])
        if len(expected) != len(periods):
            missing = sorted(set(expected) - set(periods))
            error("continuity", f"{key}: missing months, e.g. {missing[:3]}")
        if reference_period and periods[-1] != reference_period:
            error("latest_period", f"{key}: latest month {periods[-1]} != release {reference_period}")
    for key in ROLLING:
        if values[key] and reference_period and max(values[key]) != reference_period:
            error("latest_period", f"{key}: latest year-ended {max(values[key])} != release "
                                   f"{reference_period}")

    arr, dep, net = (values[k] for k in MONTHLY)
    off = [p for p in sorted(set(arr) & set(dep) & set(net))
           if abs(net[p] - (arr[p] - dep[p])) > NET_IDENTITY_TOLERANCE]
    if off:
        error("net_identity", f"net != arrivals - departures (tolerance "
                              f"{NET_IDENTITY_TOLERANCE:g}) in {len(off)} months, e.g. {off[:3]}")

    for direction in ("arrivals", "departures", "net"):
        published = values[f"mig.ry.{direction}"]
        derived = rolling_by_period(values[f"mig.m.{direction}"], 12)
        if not published:
            continue
        latest = max(published)
        if latest not in derived:
            error("rolling_check", f"cannot derive year ended {latest} for {direction}")
        elif abs(published[latest] - derived[latest]) > ROLLING_TOLERANCE:
            error("rolling_check",
                  f"{direction}: published year ended {latest} = {published[latest]:g} but the sum "
                  f"of twelve monthly estimates = {derived[latest]:g}")

    status = {o.period: o.status for o in by_key["mig.m.net"].observations}
    provisional = sorted(p for p, s in status.items() if s is ObsStatus.PROVISIONAL)
    if provisional and (
        len(provisional) > PROVISIONAL_MAX_MONTHS
        or provisional != month_range(provisional[0], provisional[-1])
        or provisional[-1] != max(status)
    ):
        findings.append(Finding(
            "provisional_window", "warning",
            f"provisional months are not the latest <= {PROVISIONAL_MAX_MONTHS} contiguous months "
            f"({len(provisional)} provisional, {provisional[0]}..{provisional[-1]})"))

    for key in MONTHLY:
        prev = previous.get(key) or {}
        common = [p for p in values[key] if p in prev]
        if len(common) < MIN_HISTORY_MONTHS:
            continue
        big = [p for p in common
               if abs(values[key][p] - prev[p].value) / max(abs(prev[p].value), REVISION_FLOOR)
               > BIG_REVISION]
        if len(big) / len(common) > MAX_BIG_REVISION_SHARE:
            error("revision_plausibility",
                  f"{key}: {len(big)} of {len(common)} overlapping months moved by more than "
                  f"{BIG_REVISION:.0%} versus the previous vintage")

    latest_total = max(values["mig.m.arrivals"])
    total = values["mig.m.arrivals"][latest_total]
    place_keys = [k for k, ps in by_key.items()
                  if ps.definition.category in ("migration:country", "migration:unallocated")]
    if place_keys:
        summed = sum(values[k].get(latest_total, 0.0) for k in place_keys)
        tolerance = max(COUNTRY_TOLERANCE_ABS, COUNTRY_TOLERANCE_REL * total)
        if abs(summed - total) > tolerance:
            error("country_sum",
                  f"countries (excluding regions) sum to {summed:g} for {latest_total} but total "
                  f"arrivals are {total:g} (tolerance {tolerance:g})")
    return findings
```

- [ ] **Step 4: Run to verify pass, then re-run the adapter tests; lint**

Run: `cd backend && pytest tests/validate tests/adapters -v && ruff check --fix . && ruff format .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add migration validation rules

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Runtime, discovery, ingestion pipeline and CLI

**Files:**
- Create: `backend/src/nzstats/runtime.py`, `backend/src/nzstats/pipeline/{__init__,discover,ingest}.py`, `backend/src/nzstats/cli.py`
- Test support: `backend/tests/support.py` (FakeSite and helpers), fixtures `site` and `rt` appended to `backend/tests/conftest.py`
- Test: `backend/tests/pipeline/{__init__,test_discover,test_ingest}.py`, `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 0–8.
- Produces:
  - `Runtime(settings, conn, fetcher, artifacts, adapters: Mapping[str, Adapter], lock: threading.RLock)`; `build_runtime(settings: Settings, *, fetcher: Fetcher | None = None) -> Runtime`; `build_adapters(settings) -> dict[str, Adapter]`
  - `pipeline.discover.discover(rt: Runtime, *, months: Sequence[str] = (), now_fn=utc_now) -> DiscoveryResult(refs: int, errors: tuple[str, ...])`; `current_and_next_months(now: datetime) -> list[str]`
  - `pipeline.ingest.IngestOutcome(release_key: str, outcome: str, error_class: ErrorClass | None = None, detail: str | None = None, warnings: tuple[str, ...] = ())` where `outcome ∈ {"ingested", "unchanged", "not_available", "failed", "skipped_no_adapter"}`
  - `pipeline.ingest.ingest_release(rt: Runtime, release_key: str, *, now_fn=utc_now) -> IngestOutcome`
  - `pipeline.ingest.backfill(rt: Runtime, *, since: str, until: str | None = None, now_fn=utc_now) -> list[IngestOutcome]`
  - CLI: `nzstats {migrate, discover, ingest (--release-key KEY | --due), backfill [--since YYYY-MM], serve [--host --port], health, backup DEST, openapi}`; `cli.main(argv: Sequence[str] | None = None) -> int`

Semantics: `backfill_since` is the oldest **reference period** to ingest; publication months are scanned from that month forward. A failed or not-yet-available ingestion writes no vintage and never touches existing data. `not_available` (HTTP 404 on the release page or a data file) does not change source health; `failed` marks `release:<slug>` degraded; success marks it ok.

- [ ] **Step 1: Write the test harness (fake Stats NZ site backed by real fixtures)**

`backend/tests/support.py`:

```python
import calendar
from datetime import datetime, timezone

import httpx

from nzstats.domain import ReleaseRef, ReleaseStatus
from nzstats.sources.calendar import make_release_key, parse_title
from nzstats.sources.fetcher import Fetcher
from nzstats.sources.release_page import classify_download, parse_release_page
from tests.conftest import fixture_bytes, fixture_text

BASE = "https://www.stats.govt.nz"
NOW = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)


def page_url(month: str) -> str:
    year, mm = month.split("-")
    return f"{BASE}/information-releases/international-migration-" \
           f"{calendar.month_name[int(mm)].lower()}-{year}/"


def release_ref_for(month: str, status: ReleaseStatus = ReleaseStatus.PUBLISHED) -> ReleaseRef:
    page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
    parts = parse_title(page.title)
    return ReleaseRef(
        release_key=make_release_key(page.title), series_slug=parts.series_slug, title=page.title,
        period_label=parts.period_label, reference_period=parts.reference_period,
        published_at=page.published_at, status=status, page_url=page_url(month),
    )


class FakeSite:
    """Serves real fixture bytes; individual URLs can be overridden to simulate failures."""

    def __init__(self, months=("2026-06", "2026-07")) -> None:
        self.routes: dict[str, tuple[int, bytes, str]] = {}
        self.requests: list[str] = []
        for month in months:
            html_text = fixture_text(f"im_{month}_page.html")
            self.routes[page_url(month)] = (200, html_text.encode(), "text/html; charset=utf-8")
            for url in parse_release_page(html_text, BASE).download_urls:
                kind = classify_download(url)
                name = {"age_sex": "age_sex", "citizenship_visa_country": "citizenship_country"}
                if kind in name:
                    self.routes[url] = (
                        200, fixture_bytes(f"im_{month}_{name[kind]}.csv"),
                        "application/octet-stream")
        self.routes[f"{BASE}/release-calendar/calendar-export/"] = (
            200, fixture_bytes("calendar_export_excerpt.ics"), "text/calendar; charset=UTF-8")
        for m in ("2026-09", "2026-10"):
            self.routes[f"{BASE}/api/v1/releaseCalendarMonth/{m}"] = (
                200, fixture_bytes(f"release_month_{m}.json"), "application/json")

    def file_url(self, month: str, kind: str) -> str:
        page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
        return next(u for u in page.download_urls if classify_download(u) == kind)

    def override(self, url: str, status: int = 200, body: bytes = b"",
                 ctype: str = "application/octet-stream") -> None:
        self.routes[url] = (status, body, ctype)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        status, body, ctype = self.routes.get(url, (404, b"", "text/html"))
        return httpx.Response(status, content=body, headers={"content-type": ctype})

    def fetcher(self) -> Fetcher:
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return Fetcher(client, sleep=lambda s: None, clock=lambda: 0.0)


```

Append to `backend/tests/conftest.py` (imports are lazy so earlier tasks' tests never import pipeline code):

```python
import pytest


@pytest.fixture()
def site():
    from tests.support import FakeSite

    return FakeSite()


@pytest.fixture()
def rt(tmp_path, site):
    from nzstats.config import load_settings
    from nzstats.runtime import build_runtime
    from tests.support import BASE

    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path), "NZSTATS_BASE_URL": BASE})
    return build_runtime(settings, fetcher=site.fetcher())
```

- [ ] **Step 2: Write the failing discovery and ingestion tests**

`backend/tests/pipeline/test_discover.py`:

```python
from datetime import datetime, timezone

from nzstats.domain import ReleaseStatus
from nzstats.pipeline.discover import current_and_next_months, discover
from nzstats.store import repo
from tests.support import BASE, NOW, release_ref_for


def test_current_and_next_months_use_auckland_calendar() -> None:
    # 2026-09-30 20:00 UTC is already 1 Oct in Auckland (NZDT, UTC+13)
    assert current_and_next_months(datetime(2026, 9, 30, 20, tzinfo=timezone.utc)) == \
        ["2026-10", "2026-11"]
    assert current_and_next_months(datetime(2026, 12, 20, tzinfo=timezone.utc)) == \
        ["2026-12", "2027-01"]


def test_discover_upserts_calendar_and_months_idempotently(rt) -> None:
    first = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    n = rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0]
    second = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    assert first.refs > 0 and not first.errors and not second.errors
    assert rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] == n
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health == {"calendar_ics": "ok", "calendar_month": "ok"}


def test_ics_failure_degrades_health_but_month_endpoint_still_runs(rt, site) -> None:
    site.override(f"{BASE}/release-calendar/calendar-export/", 403, b"", "text/html")
    result = discover(rt, months=["2026-09"], now_fn=lambda: NOW)
    assert len(result.errors) == 1 and "blocked" in result.errors[0]
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["calendar_ics"] == "degraded" and health["calendar_month"] == "ok"
    assert rt.conn.execute("SELECT COUNT(*) FROM release").fetchone()[0] > 0


def test_calendar_never_downgrades_a_published_release(rt) -> None:
    ref = release_ref_for("2026-07")
    repo.upsert_release(rt.conn, ref, NOW)
    discover(rt, months=[], now_fn=lambda: NOW)  # ICS lists only upcoming events
    row = repo.get_release(rt.conn, ref.release_key)
    assert row["status"] == ReleaseStatus.PUBLISHED.value
```

`backend/tests/pipeline/test_ingest.py`:

```python
import io

import pandas as pd
import pytest

from nzstats.domain import ErrorClass, ReleaseStatus
from nzstats.pipeline.ingest import backfill, ingest_release
from nzstats.stats.revision import revisions
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_bytes
from tests.support import NOW, release_ref_for


def _seed(rt, *months) -> list[str]:
    keys = []
    for m in months:
        ref = release_ref_for(m)
        repo.upsert_release(rt.conn, ref, NOW)
        keys.append(ref.release_key)
    return keys


def _count(rt, table: str) -> int:
    return rt.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _ingest(rt, key):
    return ingest_release(rt, key, now_fn=lambda: NOW)


def test_happy_path_ingests_real_fixtures_in_order(rt) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    assert _ingest(rt, june).outcome == "ingested"
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.latest_points(rt.conn, "mig.m.net")["2026-07"].value == 5170.0
    row = repo.get_release(rt.conn, july)
    assert row["status"] == "published" and row["headline"]
    assert len(repo.list_vintages(rt.conn, "mig.m.net")) == 2
    assert _count(rt, "ingest_run") == 2
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["release:international-migration"] == "ok"


def test_reingesting_identical_files_is_a_noop(rt) -> None:
    (july,) = _seed(rt, "2026-07")
    assert _ingest(rt, july).outcome == "ingested"
    before = (_count(rt, "vintage"), _count(rt, "observation"))
    assert _ingest(rt, july).outcome == "unchanged"
    assert (_count(rt, "vintage"), _count(rt, "observation")) == before


def _net(name: str) -> dict[str, int]:
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


def test_revisions_between_real_vintages_match_independent_calculation(rt) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _ingest(rt, june)
    _ingest(rt, july)
    a, b = _net("im_2026-06_age_sex.csv"), _net("im_2026-07_age_sex.csv")
    expected = {p for p in a.keys() & b.keys() if a[p] != b[p]}
    v = repo.list_vintages(rt.conn, "mig.m.net")
    got = {r.period for r in revisions(repo.vintage_points(rt.conn, v[0].vintage_id),
                                       repo.vintage_points(rt.conn, v[1].vintage_id))
           if r.absolute != 0}
    assert got == expected and expected, "the July release should revise earlier months"


def _drop_month(data: bytes, period: str) -> bytes:
    df = pd.read_csv(io.BytesIO(data))
    return df[df.year_month != period].to_csv(index=False, quoting=1).encode()


def test_validation_failure_writes_nothing_and_keeps_last_known_good(rt, site) -> None:
    june, july = _seed(rt, "2026-06", "2026-07")
    _ingest(rt, june)
    good = repo.latest_points(rt.conn, "mig.m.net")
    url = site.file_url("2026-07", "age_sex")
    site.override(url, 200, _drop_month(fixture_bytes("im_2026-07_age_sex.csv"), "2015-05"))
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.VALIDATION_FAILED
    assert "continuity" in (out.detail or "") or "missing months" in (out.detail or "")
    assert repo.latest_points(rt.conn, "mig.m.net") == good
    assert len(repo.list_vintages(rt.conn, "mig.m.net")) == 1
    assert repo.get_release(rt.conn, july)["status"] == "published"  # from seed, unchanged
    run = rt.conn.execute("SELECT * FROM ingest_run ORDER BY id DESC LIMIT 1").fetchone()
    assert run["outcome"] == "failed" and run["error_class"] == "validation_failed"
    health = {r["source"]: r["state"] for r in rt.conn.execute("SELECT * FROM source_health")}
    assert health["release:international-migration"] == "degraded"


def test_page_live_but_data_file_missing_is_not_available_and_writes_no_vintage(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    site.override(site.file_url("2026-07", "citizenship_visa_country"), 404, b"", "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "not_available" and out.error_class is ErrorClass.NOT_FOUND
    assert _count(rt, "vintage") == 0 and _count(rt, "observation") == 0
    assert _count(rt, "source_health") == 0  # polling before files exist is not a failure


def test_block_page_served_as_200_is_failed_blocked(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    body = b"<html>Request unsuccessful. Incapsula incident ID: 42</html>"
    site.override(site.file_url("2026-07", "age_sex"), 200, body, "text/html")
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.BLOCKED
    assert _count(rt, "vintage") == 0


def _bump(data: bytes, period: str, delta: int) -> bytes:
    df = pd.read_csv(io.BytesIO(data))
    sel = (df.sex == "TOTAL") & (df.age == "TOTAL") & (df.year_month == period)
    df.loc[sel & df.direction.isin(["Arrivals", "Net"]), "estimate"] += delta
    return df.to_csv(index=False, quoting=1).encode()


def test_corrected_republication_adds_a_vintage_without_duplicates(rt, site) -> None:
    (july,) = _seed(rt, "2026-07")
    _ingest(rt, july)
    obs_before = _count(rt, "observation")
    url = site.file_url("2026-07", "age_sex")
    site.override(url, 200, _bump(fixture_bytes("im_2026-07_age_sex.csv"), "2010-01", 10))
    out = _ingest(rt, july)
    assert out.outcome == "ingested", out.detail
    assert repo.get_release(rt.conn, july)["status"] == ReleaseStatus.CORRECTED.value
    v = repo.list_vintages(rt.conn, "mig.m.arrivals")
    assert len(v) == 2
    first, second = (repo.vintage_points(rt.conn, i.vintage_id) for i in v)
    assert second["2010-01"].value == first["2010-01"].value + 10
    assert _count(rt, "observation") > obs_before
    assert _ingest(rt, july).outcome == "unchanged"  # same corrected bytes again


def test_release_without_registered_adapter_is_skipped(rt) -> None:
    from nzstats.sources.calendar import events_to_refs, parse_ics
    from tests.conftest import fixture_text

    ref = next(r for r in events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
               if r.series_slug != "international-migration")
    repo.upsert_release(rt.conn, ref, NOW)
    out = _ingest(rt, ref.release_key)
    assert out.outcome == "skipped_no_adapter" and _count(rt, "ingest_run") == 0


def test_unexpected_errors_are_classified_not_swallowed(rt, site, monkeypatch) -> None:
    (july,) = _seed(rt, "2026-07")

    def boom(*a, **k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(rt.adapters["international-migration"], "parse", boom)
    out = _ingest(rt, july)
    assert out.outcome == "failed" and out.error_class is ErrorClass.UNEXPECTED
    assert "parser exploded" in (out.detail or "")


def test_backfill_ingests_releases_from_reference_period_in_order(rt, site) -> None:
    site.routes[f"{rt.settings.base_url}/api/v1/releaseCalendarMonth/2026-08"] = (
        200, _month_payload(release_ref_for("2026-06")), "application/json")
    site.routes[f"{rt.settings.base_url}/api/v1/releaseCalendarMonth/2026-09"] = (
        200, _month_payload(release_ref_for("2026-07")), "application/json")
    outcomes = backfill(rt, since="2026-06", until="2026-09", now_fn=lambda: NOW)
    assert [o.outcome for o in outcomes] == ["ingested", "ingested"]
    assert [o.release_key.split(":")[1] for o in outcomes] == ["june 2026", "july 2026"]


def _month_payload(ref) -> bytes:
    import json

    from nzstats.clock import AKL

    stamp = ref.published_at.astimezone(AKL).strftime("%Y-%m-%d %H:%M:%S")
    path = ref.page_url.removeprefix("https://www.stats.govt.nz")
    return json.dumps({"items": {"published": [{
        "ID": "1", "PageLink": path, "MetaDescription": "headline text for the release page",
        "DateTaxonomyTerm": {"DisplayName": ref.title, "PublicationDate": stamp}}],
        "upcoming": []}}).encode()
```

`backend/tests/test_cli.py`:

```python
import sqlite3

from nzstats.cli import main


def test_migrate_then_backup_produces_valid_copy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["migrate"]) == 0
    dest = tmp_path / "backup.db"
    assert main(["backup", str(dest)]) == 0
    tables = {r[0] for r in sqlite3.connect(dest).execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"release", "observation", "vintage"} <= tables


def test_health_prints_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["health"]) == 0
    assert '"sources"' in capsys.readouterr().out
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && pytest tests/pipeline tests/test_cli.py -v`
Expected: `ModuleNotFoundError: No module named 'nzstats.runtime'`.

- [ ] **Step 4: Implement the runtime**

`backend/src/nzstats/runtime.py`:

```python
"""Wiring: everything a pipeline run needs, built once per process."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field

from nzstats.adapters.base import Adapter
from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.config import Settings
from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import Fetcher, build_client
from nzstats.store.db import connect, migrate


def build_adapters(settings: Settings) -> dict[str, Adapter]:
    migration = MigrationAdapter(settings.country_window_months)
    return {migration.series_slug: migration}


@dataclass
class Runtime:
    settings: Settings
    conn: sqlite3.Connection
    fetcher: Fetcher
    artifacts: ArtifactStore
    adapters: Mapping[str, Adapter]
    lock: threading.RLock = field(default_factory=threading.RLock)


def build_runtime(settings: Settings, *, fetcher: Fetcher | None = None) -> Runtime:
    conn = connect(settings.db_path)
    migrate(conn)
    fetcher = fetcher or Fetcher(build_client(settings.user_agent),
                                 min_interval=settings.min_interval_seconds)
    return Runtime(settings, conn, fetcher, ArtifactStore(settings.raw_dir),
                   build_adapters(settings))
```

- [ ] **Step 5: Implement discovery**

`backend/src/nzstats/pipeline/__init__.py` (empty). `backend/src/nzstats/pipeline/discover.py`:

```python
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import AKL, utc_now
from nzstats.domain import IngestError, ReleaseRef
from nzstats.runtime import Runtime
from nzstats.sources.calendar import fetch_calendar, fetch_release_month
from nzstats.stats.periods import add_months
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveryResult:
    refs: int
    errors: tuple[str, ...]


def current_and_next_months(now: datetime) -> list[str]:
    local = now.astimezone(AKL)
    current = f"{local.year:04d}-{local.month:02d}"
    return [current, add_months(current, 1)]


def _store(rt: Runtime, refs: Sequence[ReleaseRef], now: datetime) -> None:
    with transaction(rt.conn):
        for ref in refs:
            repo.upsert_release(rt.conn, ref, now)


def attempt(rt: Runtime, source: str, now_fn: Callable[[], datetime],
             fetch: Callable[[], list[ReleaseRef]], errors: list[str]) -> int:
    try:
        refs = fetch()
        _store(rt, refs, now_fn())
        repo.set_source_health(rt.conn, source, now_fn(), ok=True, detail=None)
        return len(refs)
    except IngestError as exc:
        message = f"{source}: {exc.error_class.value}: {exc}"
        log.warning("discovery failed: %s", message)
        repo.set_source_health(rt.conn, source, now_fn(), ok=False, detail=message)
        errors.append(message)
        return 0


def discover(
    rt: Runtime, *, months: Sequence[str] = (), now_fn: Callable[[], datetime] = utc_now
) -> DiscoveryResult:
    s = rt.settings
    errors: list[str] = []
    total = attempt(rt, "calendar_ics", now_fn,
                     lambda: fetch_calendar(rt.fetcher, s.base_url, s.calendar_ics_path), errors)
    for month in months:
        total += attempt(
            rt, "calendar_month", now_fn,
            lambda m=month: fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m),
            errors)
    return DiscoveryResult(total, tuple(errors))
```

- [ ] **Step 6: Implement ingestion and backfill**

`backend/src/nzstats/pipeline/ingest.py`:

```python
"""discover -> fetch -> validate -> normalise -> persist, with last-known-good preserved."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import AKL, from_utc_iso, utc_now
from nzstats.domain import ErrorClass, IngestError, ReleaseStatus
from nzstats.pipeline.discover import attempt
from nzstats.runtime import Runtime
from nzstats.slug import slugify
from nzstats.sources.calendar import fetch_release_month
from nzstats.sources.release_page import classify_download, parse_release_page
from nzstats.stats.periods import month_range
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

HTML = ("text/html",)
DATA_TYPES = ("text/csv", "application/octet-stream", "text/plain", "application/vnd.ms-excel")


@dataclass(frozen=True)
class IngestOutcome:
    release_key: str
    outcome: str  # ingested | unchanged | not_available | failed | skipped_no_adapter
    error_class: ErrorClass | None = None
    detail: str | None = None
    warnings: tuple[str, ...] = ()


def ingest_release(
    rt: Runtime, release_key: str, *, now_fn: Callable[[], datetime] = utc_now
) -> IngestOutcome:
    row = repo.get_release(rt.conn, release_key)
    if row is None:
        raise KeyError(f"unknown release {release_key!r}")
    adapter = rt.adapters.get(row["series_slug"])
    if adapter is None:
        return IngestOutcome(release_key, "skipped_no_adapter")
    started = now_fn()
    try:
        outcome = _ingest(rt, row, adapter, now_fn)
    except IngestError as exc:
        kind = "not_available" if exc.error_class is ErrorClass.NOT_FOUND else "failed"
        outcome = IngestOutcome(release_key, kind, exc.error_class, str(exc))
    except Exception as exc:  # classified and recorded, never silently swallowed
        log.exception("unexpected error ingesting %s", release_key)
        outcome = IngestOutcome(release_key, "failed", ErrorClass.UNEXPECTED, repr(exc))
    finished = now_fn()
    detail = outcome.detail
    if outcome.warnings:
        detail = "; ".join(filter(None, [detail, "warnings: " + " | ".join(outcome.warnings)]))
    repo.record_ingest_run(rt.conn, release_key, started, finished, outcome.outcome,
                           outcome.error_class.value if outcome.error_class else None, detail)
    source = f"release:{row['series_slug']}"
    if outcome.outcome in ("ingested", "unchanged"):
        repo.set_source_health(rt.conn, source, finished, ok=True, detail=None)
    elif outcome.outcome == "failed":
        repo.set_source_health(rt.conn, source, finished, ok=False, detail=detail)
    return outcome


def _ingest(rt, row, adapter, now_fn) -> IngestOutcome:
    key, settings = row["release_key"], rt.settings
    page_url = row["page_url"] or settings.base_url + settings.release_page_path.format(
        slug=slugify(row["title"]))

    page_result = rt.fetcher.get(page_url, expect=HTML)
    repo.record_artifact(rt.conn, rt.artifacts.save(page_result))
    page = parse_release_page(page_result.body.decode("utf-8"), settings.base_url)

    wanted: dict[str, str] = {}
    for url in page.download_urls:
        kind = classify_download(url)
        if kind in adapter.required_downloads and kind not in wanted:
            wanted[kind] = url
    missing = [k for k in adapter.required_downloads if k not in wanted]
    if missing:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release page lists no {missing} download")

    files: dict[str, bytes] = {}
    digests: list[str] = []
    for kind, url in wanted.items():
        result = rt.fetcher.get(url, expect=DATA_TYPES)
        record = rt.artifacts.save(result)
        repo.record_artifact(rt.conn, record)
        files[kind] = result.body
        digests.append(record.sha256)
    bundle_sha = hashlib.sha256("".join(sorted(digests)).encode()).hexdigest()

    release_id = int(row["id"])
    if repo.has_vintage(rt.conn, release_id, bundle_sha):
        return IngestOutcome(key, "unchanged")

    bundle = adapter.parse(page, files)
    published_at = from_utc_iso(row["published_at"])
    previous = {k: repo.previous_points(rt.conn, k, published_at) for k in adapter.previous_keys}
    findings = adapter.validate(bundle, reference_period=row["reference_period"],
                                previous=previous)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise IngestError(ErrorClass.VALIDATION_FAILED,
                          "; ".join(f"[{f.rule}] {f.message}" for f in errors[:5]))

    now = now_fn()
    corrected = repo.has_any_vintage(rt.conn, release_id)
    with transaction(rt.conn):
        for ps in bundle.series:
            series_id = repo.upsert_series(rt.conn, ps.definition)
            vintage_id = repo.create_vintage(rt.conn, release_id, series_id, now,
                                             "release_files", bundle.layout_version, bundle_sha)
            if vintage_id is not None:
                repo.insert_observations(rt.conn, vintage_id, ps.observations)
        repo.set_release_headline(rt.conn, key, page.headline, page_url)
        repo.set_release_status(
            rt.conn, key, ReleaseStatus.CORRECTED if corrected else ReleaseStatus.PUBLISHED, now)
    return IngestOutcome(key, "ingested",
                         warnings=tuple(f.message for f in findings if f.severity == "warning"))


def backfill(
    rt: Runtime, *, since: str, until: str | None = None,
    now_fn: Callable[[], datetime] = utc_now,
) -> list[IngestOutcome]:
    """Ingest every published release whose reference period is >= `since`, oldest first."""
    s = rt.settings
    local_now = now_fn().astimezone(AKL)
    until = until or f"{local_now.year:04d}-{local_now.month:02d}"
    errors: list[str] = []
    for month in month_range(since, until):
        attempt(rt, "calendar_month", now_fn,
                 lambda m=month: fetch_release_month(rt.fetcher, s.base_url,
                                                     s.release_month_path, m), errors)
    slugs = list(rt.adapters)
    marks = ",".join("?" * len(slugs))
    keys = [r["release_key"] for r in rt.conn.execute(
        f"SELECT release_key FROM release WHERE series_slug IN ({marks}) AND reference_period >= ?"
        f" AND status IN ('published', 'corrected') ORDER BY published_at",
        (*slugs, since))]
    return [ingest_release(rt, k, now_fn=now_fn) for k in keys]
```


- [ ] **Step 7: Implement the CLI**

`backend/src/nzstats/cli.py`:

```python
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections.abc import Sequence

from nzstats.clock import utc_now
from nzstats.config import load_settings
from nzstats.pipeline.discover import current_and_next_months, discover
from nzstats.pipeline.ingest import backfill, ingest_release
from nzstats.runtime import build_runtime
from nzstats.scheduler.planner import releases_needing_ingest
from nzstats.store.db import connect, migrate

log = logging.getLogger("nzstats")


def _health_payload(conn: sqlite3.Connection) -> dict:
    sources = [dict(r) for r in conn.execute("SELECT * FROM source_health ORDER BY source")]
    runs = [dict(r) for r in conn.execute(
        "SELECT release_key, started_at, outcome, error_class, detail FROM ingest_run"
        " ORDER BY id DESC LIMIT 10")]
    return {"sources": sources, "recent_runs": runs}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="nzstats")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="create or upgrade the database")
    sub.add_parser("discover", help="refresh the release calendar")
    p_ingest = sub.add_parser("ingest", help="ingest one release or all that are due")
    group = p_ingest.add_mutually_exclusive_group(required=True)
    group.add_argument("--release-key")
    group.add_argument("--due", action="store_true")
    p_back = sub.add_parser("backfill", help="ingest historical releases")
    p_back.add_argument("--since", help="oldest reference period, YYYY-MM")
    p_serve = sub.add_parser("serve", help="run the API, UI and scheduler")
    p_serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container default
    p_serve.add_argument("--port", type=int, default=8000)
    sub.add_parser("health", help="print source health as JSON")
    p_backup = sub.add_parser("backup", help="write a consistent copy of the database")
    p_backup.add_argument("dest")
    sub.add_parser("openapi", help="print the OpenAPI document")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.command == "migrate":
        conn = connect(settings.db_path)
        print(f"schema version {migrate(conn)} at {settings.db_path}")
        return 0
    if args.command == "health":
        conn = connect(settings.db_path)
        migrate(conn)
        print(json.dumps(_health_payload(conn), indent=2))
        return 0
    if args.command == "backup":
        conn = connect(settings.db_path)
        migrate(conn)
        dest = sqlite3.connect(args.dest)
        conn.backup(dest)
        dest.close()
        print(f"backup written to {args.dest}")
        return 0
    if args.command == "openapi":
        from nzstats.api.app import create_app

        print(json.dumps(create_app(settings, start_scheduler=False).openapi(), indent=2))
        return 0
    if args.command == "serve":
        import uvicorn

        from nzstats.api.app import create_app

        uvicorn.run(create_app(settings, start_scheduler=True), host=args.host, port=args.port)
        return 0

    rt = build_runtime(settings)
    if args.command == "discover":
        result = discover(rt, months=current_and_next_months(utc_now()))
        print(f"{result.refs} releases seen; errors: {list(result.errors)}")
        return 1 if result.errors else 0
    if args.command == "ingest":
        keys = ([args.release_key] if args.release_key
                else releases_needing_ingest(rt.conn, rt.adapters, utc_now(), settings.catch_up_days))
        outcomes = [ingest_release(rt, k) for k in keys]
    else:  # backfill
        outcomes = backfill(rt, since=args.since or settings.backfill_since)
    for o in outcomes:
        print(f"{o.release_key}: {o.outcome}" + (f" ({o.error_class.value}: {o.detail})"
                                                  if o.error_class else ""))
    return 1 if any(o.outcome == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
```

`releases_needing_ingest` is implemented in Task 10 (`scheduler/planner.py`). To keep this task green, create `backend/src/nzstats/scheduler/__init__.py` and a first version of `planner.py` containing only:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
import sqlite3

from nzstats.clock import to_utc_iso


def releases_needing_ingest(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime, catch_up_days: int
) -> list[str]:
    """Releases already due (published_at <= now, within the catch-up window) with no vintage."""
    slugs = list(adapters)
    marks = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"SELECT r.release_key FROM release r WHERE r.series_slug IN ({marks})"
        " AND r.published_at <= ? AND r.published_at >= ?"
        " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        " ORDER BY r.published_at",
        (*slugs, to_utc_iso(now), to_utc_iso(now - timedelta(days=catch_up_days))))
    return [r["release_key"] for r in rows]
```

(Task 10 extends this file and tests it.) `cli.py` imports `create_app` lazily, so `openapi`/`serve` work only after Task 12.

- [ ] **Step 8: Run to verify pass; lint**

Run: `cd backend && pytest tests/pipeline tests/test_cli.py -v && ruff check --fix . && ruff format .`
Expected: PASS. If `test_happy_path…` fails on a validation finding, print `out.detail`, then inspect the real fixture values for that rule. Never relax a threshold to make real data pass without evidence; follow `superpowers:systematic-debugging`.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: add discovery, ingestion pipeline, backfill and CLI

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Release-aware scheduler

**Files:**
- Modify: `backend/src/nzstats/scheduler/planner.py`
- Create: `backend/src/nzstats/scheduler/jobs.py`
- Test: `backend/tests/scheduler/{__init__,test_planner,test_jobs}.py`

**Interfaces:**
- Consumes: `Runtime`, `pipeline.discover.{discover, current_and_next_months}`, `pipeline.ingest.{ingest_release, IngestOutcome}`, `store.repo`, `clock.*`.
- Produces:
  - `planner.next_poll_due(published_at: datetime, attempts: int, now: datetime, offsets_minutes: Sequence[int]) -> bool`
  - `planner.poll_candidates(conn, adapters, now: datetime, offsets_minutes: Sequence[int]) -> list[str]`
  - `planner.mark_unavailable(conn, adapters, now: datetime, offsets_minutes: Sequence[int]) -> list[str]`
  - `planner.releases_needing_ingest(...)` (from Task 9, unchanged)
  - `jobs.job_refresh_calendar(rt, *, now_fn=utc_now) -> DiscoveryResult`; `jobs.job_release_watch(rt, *, now_fn=utc_now) -> list[IngestOutcome]`; `jobs.job_catch_up(rt, *, now_fn=utc_now) -> list[IngestOutcome]`; `jobs.build_scheduler(rt) -> BackgroundScheduler`

Polling rules: a release (scheduled, delayed or published-without-vintage) is polled at `published_at + offsets[attempts]` where `attempts` counts `ingest_run` rows started at or after `published_at`; polling stops after all offsets are used. Network is touched only when a release is due. After offsets are exhausted without a vintage, a scheduled/delayed release is marked `unavailable` (evidence: scheduled time passed and no files). The daily catch-up job (and startup) retries anything published within `catch_up_days` that still has no vintage, so downtime and `unavailable` releases recover.

- [ ] **Step 1: Write the failing tests**

`backend/tests/scheduler/test_planner.py`:

```python
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from nzstats.adapters.migration.series import monthly_def
from nzstats.clock import parse_akl_naive
from nzstats.domain import ReleaseStatus
from nzstats.scheduler.planner import (mark_unavailable, next_poll_due, poll_candidates,
                                       releases_needing_ingest)
from nzstats.store import repo
from tests.support import release_ref_for

OFFSETS = [0, 1, 2, 5, 10, 15, 30, 60, 120, 180]
PUB = parse_akl_naive("2026-10-14 10:45:00")
SEEDED = datetime(2026, 10, 11, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("minutes_after", "attempts", "due"),
    [(-1, 0, False), (0, 0, True), (0.5, 1, False), (1, 1, True), (4, 3, False), (5, 3, True),
     (500, 10, False)],
)
def test_next_poll_due(minutes_after, attempts, due) -> None:
    now = PUB + timedelta(minutes=minutes_after)
    assert next_poll_due(PUB, attempts, now, OFFSETS) is due


def _seed(conn, month="2026-07", status=ReleaseStatus.SCHEDULED, at="2026-10-14 10:45:00") -> str:
    ref = dataclasses.replace(release_ref_for(month, status), published_at=parse_akl_naive(at))
    repo.upsert_release(conn, ref, SEEDED)
    return ref.release_key


def _run(conn, key, at) -> None:
    repo.record_ingest_run(conn, key, at, at, "not_available", "not_found", None)


def test_candidate_follows_offset_schedule(rt) -> None:
    key = _seed(rt.conn)
    assert poll_candidates(rt.conn, rt.adapters, PUB - timedelta(minutes=1), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB, OFFSETS) == [key]
    _run(rt.conn, key, PUB)
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(seconds=30), OFFSETS) == []
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=1), OFFSETS) == [key]


def test_runs_before_the_scheduled_time_do_not_count_as_attempts(rt) -> None:
    key = _seed(rt.conn)
    _run(rt.conn, key, PUB - timedelta(days=1))
    assert poll_candidates(rt.conn, rt.adapters, PUB, OFFSETS) == [key]


def test_no_candidates_once_a_vintage_exists(rt) -> None:
    key = _seed(rt.conn)
    series_id = repo.upsert_series(rt.conn, monthly_def("net"))
    release_id = repo.get_release(rt.conn, key)["id"]
    repo.create_vintage(rt.conn, release_id, series_id, PUB, "release_files", "v", "sha")
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=1), OFFSETS) == []


def test_window_expires_and_marks_unavailable(rt) -> None:
    key = _seed(rt.conn)
    for minute in OFFSETS:
        _run(rt.conn, key, PUB + timedelta(minutes=minute))
    later = PUB + timedelta(minutes=181)
    assert poll_candidates(rt.conn, rt.adapters, later, OFFSETS) == []
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == [key]
    assert repo.get_release(rt.conn, key)["status"] == "unavailable"
    assert mark_unavailable(rt.conn, rt.adapters, later, OFFSETS) == []  # idempotent


def test_published_release_without_vintage_is_polled_but_never_marked_unavailable(rt) -> None:
    key = _seed(rt.conn, status=ReleaseStatus.PUBLISHED)
    assert poll_candidates(rt.conn, rt.adapters, PUB + timedelta(minutes=3), OFFSETS) == [key]
    for minute in OFFSETS:
        _run(rt.conn, key, PUB + timedelta(minutes=minute))
    assert mark_unavailable(rt.conn, rt.adapters, PUB + timedelta(hours=5), OFFSETS) == []


def test_catch_up_window(rt) -> None:
    old = _seed(rt.conn, month="2026-06", at="2026-09-01 10:45:00")
    recent = _seed(rt.conn, month="2026-07", at="2026-10-12 10:45:00")
    assert old != recent
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 7) == [recent]
    assert releases_needing_ingest(rt.conn, rt.adapters, PUB, 60) == [old, recent]
```

`backend/tests/scheduler/test_jobs.py`:

```python
import dataclasses
from datetime import timedelta

from nzstats.clock import parse_akl_naive
from nzstats.domain import ReleaseStatus
from nzstats.scheduler.jobs import (build_scheduler, job_catch_up, job_refresh_calendar,
                                    job_release_watch)
from nzstats.store import repo
from tests.support import NOW, release_ref_for

PUB = parse_akl_naive("2026-09-14 10:45:00")  # real publication time of the July 2026 release


def _seed_scheduled(rt) -> str:
    ref = dataclasses.replace(release_ref_for("2026-07"), status=ReleaseStatus.SCHEDULED,
                              page_url=None)
    repo.upsert_release(rt.conn, ref, NOW)
    return ref.release_key


def test_watch_does_nothing_and_makes_no_requests_before_publication(rt, site) -> None:
    _seed_scheduled(rt)
    outcomes = job_release_watch(rt, now_fn=lambda: PUB - timedelta(minutes=5))
    assert outcomes == [] and site.requests == []


def test_watch_ingests_at_publication_time_then_goes_quiet(rt, site) -> None:
    key = _seed_scheduled(rt)
    at = PUB + timedelta(seconds=5)
    outcomes = job_release_watch(rt, now_fn=lambda: at)
    assert [o.outcome for o in outcomes] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"
    requests = len(site.requests)
    assert job_release_watch(rt, now_fn=lambda: at + timedelta(minutes=2)) == []
    assert len(site.requests) == requests


def test_watch_retries_when_files_appear_late(rt, site) -> None:
    key = _seed_scheduled(rt)
    url = site.file_url("2026-07", "age_sex")
    good = site.routes[url]
    site.override(url, 404, b"", "text/html")
    first = job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=5))
    assert [o.outcome for o in first] == ["not_available"]
    site.routes[url] = good  # files appear
    assert job_release_watch(rt, now_fn=lambda: PUB + timedelta(seconds=30)) == []  # not due yet
    later = job_release_watch(rt, now_fn=lambda: PUB + timedelta(minutes=1, seconds=5))
    assert [o.outcome for o in later] == ["ingested"]
    assert repo.get_release(rt.conn, key)["status"] == "published"


def test_catch_up_recovers_after_downtime(rt, site) -> None:
    key = _seed_scheduled(rt)
    outcomes = job_catch_up(rt, now_fn=lambda: PUB + timedelta(days=2))
    assert [o.release_key for o in outcomes] == [key]
    assert outcomes[0].outcome == "ingested"


def test_refresh_calendar_job_reports_result(rt) -> None:
    result = job_refresh_calendar(rt, now_fn=lambda: NOW)
    assert result.refs > 0


def test_scheduler_registers_three_jobs_in_auckland_time(rt) -> None:
    sched = build_scheduler(rt)
    assert {j.id for j in sched.get_jobs()} == {"refresh_calendar", "release_watch", "catch_up"}
    assert str(sched.timezone) == "Pacific/Auckland"
    assert not sched.running
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/scheduler -v`
Expected: `ImportError: cannot import name 'mark_unavailable'` / `ModuleNotFoundError: nzstats.scheduler.jobs`.

- [ ] **Step 3: Implement the planner**

Replace `backend/src/nzstats/scheduler/planner.py`:

```python
"""Pure-ish scheduling decisions: which releases are due for a poll right now."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from nzstats.clock import from_utc_iso, to_utc_iso
from nzstats.domain import ReleaseStatus
from nzstats.store import repo


def next_poll_due(
    published_at: datetime, attempts: int, now: datetime, offsets_minutes: Sequence[int]
) -> bool:
    if attempts >= len(offsets_minutes):
        return False
    return now >= published_at + timedelta(minutes=offsets_minutes[attempts])


def _attempts(conn: sqlite3.Connection, release_key: str, published_at_utc: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM ingest_run WHERE release_key = ? AND started_at >= ?",
        (release_key, published_at_utc)).fetchone()[0]


def _unvintaged(conn: sqlite3.Connection, adapters: Mapping[str, object], statuses: Sequence[str],
                not_before: str, not_after: str) -> list[sqlite3.Row]:
    slugs = list(adapters)
    return conn.execute(
        f"SELECT r.release_key, r.published_at FROM release r"
        f" WHERE r.series_slug IN ({','.join('?' * len(slugs))})"
        f" AND r.status IN ({','.join('?' * len(statuses))})"
        f" AND r.published_at >= ? AND r.published_at <= ?"
        f" AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        f" ORDER BY r.published_at",
        (*slugs, *statuses, not_before, not_after)).fetchall()


def _window(offsets_minutes: Sequence[int]) -> timedelta:
    return timedelta(minutes=max(offsets_minutes) + 60)


def poll_candidates(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime,
    offsets_minutes: Sequence[int],
) -> list[str]:
    statuses = (ReleaseStatus.SCHEDULED.value, ReleaseStatus.DELAYED.value,
                ReleaseStatus.PUBLISHED.value)
    rows = _unvintaged(conn, adapters, statuses, to_utc_iso(now - _window(offsets_minutes)),
                       to_utc_iso(now))
    return [r["release_key"] for r in rows
            if next_poll_due(from_utc_iso(r["published_at"]),
                             _attempts(conn, r["release_key"], r["published_at"]),
                             now, offsets_minutes)]


def mark_unavailable(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime,
    offsets_minutes: Sequence[int],
) -> list[str]:
    """Scheduled/delayed releases whose polling budget is spent without any data become unavailable."""
    statuses = (ReleaseStatus.SCHEDULED.value, ReleaseStatus.DELAYED.value)
    rows = _unvintaged(conn, adapters, statuses, "0000", to_utc_iso(now))
    marked = []
    for r in rows:
        if _attempts(conn, r["release_key"], r["published_at"]) >= len(offsets_minutes):
            repo.set_release_status(conn, r["release_key"], ReleaseStatus.UNAVAILABLE, now)
            marked.append(r["release_key"])
    return marked


def releases_needing_ingest(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime, catch_up_days: int
) -> list[str]:
    """Releases already due (published_at <= now, within the catch-up window) with no vintage."""
    slugs = list(adapters)
    rows = conn.execute(
        f"SELECT r.release_key FROM release r WHERE r.series_slug IN ({','.join('?' * len(slugs))})"
        " AND r.published_at <= ? AND r.published_at >= ?"
        " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        " ORDER BY r.published_at",
        (*slugs, to_utc_iso(now), to_utc_iso(now - timedelta(days=catch_up_days))))
    return [r["release_key"] for r in rows]
```

- [ ] **Step 4: Implement the jobs**

`backend/src/nzstats/scheduler/jobs.py`:

```python
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nzstats.clock import AKL, utc_now
from nzstats.pipeline.discover import DiscoveryResult, current_and_next_months, discover
from nzstats.pipeline.ingest import IngestOutcome, ingest_release
from nzstats.runtime import Runtime
from nzstats.scheduler.planner import mark_unavailable, poll_candidates, releases_needing_ingest

log = logging.getLogger(__name__)
NowFn = Callable[[], datetime]


def job_refresh_calendar(rt: Runtime, *, now_fn: NowFn = utc_now) -> DiscoveryResult:
    with rt.lock:
        return discover(rt, months=current_and_next_months(now_fn()), now_fn=now_fn)


def job_release_watch(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    """Cheap per-minute tick: touches the network only when a release is due for a poll."""
    with rt.lock:
        now = now_fn()
        offsets = rt.settings.poll_offsets_minutes
        keys = poll_candidates(rt.conn, rt.adapters, now, offsets)
        outcomes = [ingest_release(rt, k, now_fn=now_fn) for k in keys]
        for key in mark_unavailable(rt.conn, rt.adapters, now, offsets):
            log.warning("release %s marked unavailable: polling budget spent", key)
        return outcomes


def job_catch_up(rt: Runtime, *, now_fn: NowFn = utc_now) -> list[IngestOutcome]:
    with rt.lock:
        keys = releases_needing_ingest(rt.conn, rt.adapters, now_fn(), rt.settings.catch_up_days)
        return [ingest_release(rt, k, now_fn=now_fn) for k in keys]


def build_scheduler(rt: Runtime) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=AKL)
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    sched.add_job(job_refresh_calendar, CronTrigger(hour=6, minute=0, timezone=AKL), args=[rt],
                  id="refresh_calendar", **common)
    sched.add_job(job_release_watch, IntervalTrigger(minutes=1), args=[rt],
                  id="release_watch", **common)
    sched.add_job(job_catch_up, CronTrigger(hour=7, minute=30, timezone=AKL), args=[rt],
                  id="catch_up", **common)
    return sched


def schedule_startup_tasks(sched: BackgroundScheduler, rt: Runtime) -> None:
    """Refresh the calendar and recover anything missed while the process was down."""
    soon = datetime.now(AKL) + timedelta(seconds=5)
    sched.add_job(job_refresh_calendar, "date", run_date=soon, args=[rt], id="startup_refresh")
    sched.add_job(job_catch_up, "date", run_date=soon + timedelta(seconds=60), args=[rt],
                  id="startup_catch_up")
```

- [ ] **Step 5: Run to verify pass; lint**

Run: `cd backend && pytest tests/scheduler -v && ruff check --fix . && ruff format .`
Expected: PASS. Then run the whole backend suite: `pytest` — expected all green.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add release-aware polling scheduler and catch-up jobs

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```


### Task 11: Response models, catalog and deterministic release analysis

**Files:**
- Create: `backend/src/nzstats/models.py`, `backend/src/nzstats/catalog.py`
- Create: `backend/src/nzstats/insights/{__init__,format,summary,migration}.py`
- Modify: `backend/src/nzstats/store/repo.py` (read helpers), `backend/tests/support.py` (`ingest_months`)
- Test: `backend/tests/insights/{__init__,test_format,test_analysis}.py`, `backend/tests/store/test_repo_views.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 7, 9 (ingested vintages via the `rt` fixture).
- Produces (`store/repo.py`, new):
  - `ObservationRow(period: str, value: float, status: ObsStatus, std_error: float | None, released_in: str | None)`
  - `get_series_row(conn, key: str) -> sqlite3.Row | None`
  - `get_release_by_id(conn, release_id: int) -> sqlite3.Row | None`
  - `vintage_observations(conn, vintage_id: int) -> dict[str, ObservationRow]`
  - `release_vintage(conn, series_key: str, release_id: int) -> VintageInfo | None` (newest vintage of that release)
  - `previous_vintage(conn, series_key: str, published_before_utc: str) -> VintageInfo | None`
  - `series_overview(conn, category_prefix: str | None = None) -> list[sqlite3.Row]` (columns of `series` plus `n_vintages`, `latest_period`)
- Produces (`models.py`): the Pydantic response models listed in Step 3 — `ChangeOut, Evidence, Insight, Metric, RevisionRowOut, RevisionBlock, Decomposition, PreviousComparison, Methodology, ReleaseSummary, ReleaseAnalysis, ReleaseDetail, SourceHealthOut, RunOut, HealthOut, CalendarOut, SeriesOut, PointOut, VintageOut, SeriesDataOut, RevisionHistoryRow, Coverage, RevisionsOut, CountryRank, CountriesOut, Kpi, FeaturedOut, InactiveCategory, OverviewOut`.
- Produces (`catalog.py`): `CategoryInfo(category: str, importance: str)`, `category_for(series_slug: str) -> CategoryInfo`, `INACTIVE_CATEGORIES: tuple[tuple[str, str], ...]`.
- Produces (`insights/`): `fmt_int(v) -> str`, `fmt_signed(v) -> str`, `fmt_net(v) -> str`, `dir_word(v) -> str`; `release_summary(conn, row, *, analysable_slugs) -> ReleaseSummary`; `build_release_analysis(conn, release_id: int, *, analysable_slugs: Collection[str]) -> ReleaseAnalysis | None`.
- Produces (`tests/support.py`): `ingest_months(rt, *months: str) -> dict[str, int]` mapping month → release id.

Design rules enforced here (from the spec): every insight carries evidence (series, period, value, release) that resolves to a stored observation; observation and inference are separate kinds; a new reference period is separated from revisions of earlier ones via a decomposition; percentages are `None` when not meaningful; rank statements carry the "rarity is not significance" caveat; no causal claims.

- [ ] **Step 1: Write the failing tests**

`backend/tests/insights/test_format.py`:

```python
import pytest

from nzstats.insights.format import dir_word, fmt_int, fmt_net, fmt_signed


@pytest.mark.parametrize(("v", "text"), [(20350.0, "20,350"), (0.0, "0"), (-38335.4, "-38,335"),
                                         (999.5, "1,000")])
def test_fmt_int(v, text) -> None:
    assert fmt_int(v) == text


def test_fmt_signed() -> None:
    assert fmt_signed(12.0) == "+12"
    assert fmt_signed(-12.0) == "-12"
    assert fmt_signed(0.0) == "0"


def test_fmt_net_words() -> None:
    assert fmt_net(20350.0) == "a net gain of 20,350 people"
    assert fmt_net(-38335.0) == "a net loss of 38,335 people"
    assert fmt_net(0.0) == "no net change"


def test_dir_word() -> None:
    assert (dir_word(5.0), dir_word(-5.0), dir_word(0.0)) == ("rose", "fell", "was unchanged")
```

`backend/tests/store/test_repo_views.py`:

```python
from datetime import datetime, timezone

import pytest

from nzstats.adapters.migration.series import monthly_def
from nzstats.clock import parse_akl_naive, to_utc_iso
from nzstats.domain import Observation, ObsStatus
from nzstats.store import repo
from nzstats.store.db import connect, migrate, transaction
from tests.support import release_ref_for

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


@pytest.fixture()
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c


def _vintage(conn, month, value):
    ref = release_ref_for(month)
    rid = repo.upsert_release(conn, ref, NOW)
    sid = repo.upsert_series(conn, monthly_def("net"))
    with transaction(conn):
        vid = repo.create_vintage(conn, rid, sid, NOW, "release_files", "v1", f"sha-{month}")
        repo.insert_observations(conn, vid, [
            Observation("mig.m.net", "2026-05", value, ObsStatus.PROVISIONAL, 7.0, "2026-07")])
    return ref, rid


def test_release_and_previous_vintage_and_rows(conn) -> None:
    june, jid = _vintage(conn, "2026-06", 100.0)
    july, lid = _vintage(conn, "2026-07", 120.0)
    assert repo.release_vintage(conn, "mig.m.net", lid).release_key == july.release_key
    assert repo.release_vintage(conn, "mig.m.net", 9999) is None
    prev = repo.previous_vintage(conn, "mig.m.net", to_utc_iso(july.published_at))
    assert prev.release_key == june.release_key and prev.title == june.title
    assert repo.previous_vintage(conn, "mig.m.net", to_utc_iso(june.published_at)) is None
    rows = repo.vintage_observations(conn, prev.vintage_id)
    assert rows["2026-05"].std_error == 7.0 and rows["2026-05"].released_in == "2026-07"
    assert rows["2026-05"].status is ObsStatus.PROVISIONAL


def test_series_row_release_row_and_overview(conn) -> None:
    _, rid = _vintage(conn, "2026-07", 120.0)
    assert repo.get_series_row(conn, "mig.m.net")["unit"] == "people"
    assert repo.get_series_row(conn, "nope") is None
    assert repo.get_release_by_id(conn, rid)["series_slug"] == "international-migration"
    (row,) = repo.series_overview(conn)
    assert (row["key"], row["n_vintages"], row["latest_period"]) == ("mig.m.net", 1, "2026-05")
    assert repo.series_overview(conn, "nothing") == []
    assert len(repo.series_overview(conn, "migration")) == 1
```

`backend/tests/insights/test_analysis.py`:

```python
import csv
import io
from datetime import datetime

import pandas as pd
import pytest

from nzstats.insights.migration import build_release_analysis
from nzstats.sources.release_page import parse_release_page
from nzstats.store import repo
from tests.conftest import FIXTURES, fixture_text
from tests.support import BASE, ingest_months

SLUGS = {"international-migration"}
DIRECTION_CHART = "Estimated migration by direction, rolling year"


def _rolling_net(month: str) -> dict[str, float]:
    """Independent reading of the published rolling-year net series from the page fixture."""
    page = parse_release_page(fixture_text(f"im_{month}_page.html"), BASE)
    rows = list(csv.reader(io.StringIO(page.chart_starting_with(DIRECTION_CHART).csv)))
    net = next(r for r in rows if r[0] == "Net migration")
    return {datetime.strptime(h, "%b-%Y").strftime("%Y-%m"): float(v)
            for h, v in zip(rows[0][1:], net[1:], strict=True)}


def _monthly_net(name: str) -> dict[str, int]:
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


@pytest.fixture()
def both(rt):
    ids = ingest_months(rt, "2026-06", "2026-07")
    return rt, ids


def _analysis(rt, release_id):
    return build_release_analysis(rt.conn, release_id, analysable_slugs=SLUGS)


def _metric(analysis, key):
    return next(m for m in analysis.headline_metrics if m.series_key == key)


def test_headline_metrics_match_published_values(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    july = _rolling_net("2026-07")
    m = _metric(a, "mig.ry.net")
    assert (m.value, m.period, m.unit, m.status) == (july["2026-07"], "2026-07", "people",
                                                     "provisional")
    assert m.period_label == "Year ended July 2026"
    yago = m.change_year_ago
    assert yago.comparison_period == "2025-07"
    assert yago.absolute == pytest.approx(july["2026-07"] - july["2025-07"])
    assert yago.percent == pytest.approx((july["2026-07"] - july["2025-07"]) / july["2025-07"] * 100)
    monthly = _metric(a, "mig.m.net")
    assert monthly.value == 5170.0 and monthly.std_error == 545.0 and monthly.status == "provisional"


def test_negative_base_gives_no_percentage(both) -> None:
    rt, ids = both
    nz = _metric(_analysis(rt, ids["2026-07"]), "mig.ry.net.nz")
    assert nz.value < 0
    assert nz.change_year_ago is not None and nz.change_year_ago.percent is None


def test_executive_summary_is_traceable_to_stored_observations(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    assert [i.id for i in a.executive_summary] == [
        "headline", "monthly", "drivers", "revisions", "provisional"]
    assert 3 <= len(a.executive_summary) <= 5
    for insight in [*a.executive_summary, *a.context, *a.interpretation]:
        assert insight.kind in ("observation", "inference") and insight.text
        assert insight.evidence, f"{insight.id} has no evidence"
        for e in insight.evidence:
            release_id = repo.get_release(rt.conn, e.release_key)["id"]
            vintage = repo.release_vintage(rt.conn, e.series_key, release_id)
            stored = repo.vintage_observations(rt.conn, vintage.vintage_id)[e.period]
            assert stored.value == e.value, (insight.id, e)


def test_new_period_is_separated_from_revision_of_the_earlier_period(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    june, july = _rolling_net("2026-06"), _rolling_net("2026-07")
    d = next(x for x in a.previous_comparison.decompositions if x.series_key == "mig.ry.net")
    assert (d.previous_period, d.new_period) == ("2026-06", "2026-07")
    assert d.previous_published_value == june["2026-06"]
    assert d.same_period_now == july["2026-06"]
    assert d.new_value == july["2026-07"]
    assert d.revision_component == pytest.approx(july["2026-06"] - june["2026-06"])
    assert d.new_period_component == pytest.approx(july["2026-07"] - july["2026-06"])
    assert d.revision_component + d.new_period_component == pytest.approx(d.total_change)


def test_revision_block_matches_independent_calculation(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    old, new = _monthly_net("im_2026-06_age_sex.csv"), _monthly_net("im_2026-07_age_sex.csv")
    changed = {p: new[p] - old[p] for p in old.keys() & new.keys() if new[p] != old[p]}
    r = a.revisions
    assert r.available and r.n_revised == len(changed) and r.n_common == len(old.keys() & new.keys())
    top = max(changed, key=lambda p: abs(changed[p]))
    assert r.largest[0].period == top and r.largest[0].absolute == changed[top]
    assert [abs(x.absolute) for x in r.largest] == sorted(
        (abs(x.absolute) for x in r.largest), reverse=True)


def test_history_rank_matches_independent_ranking(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    series = _rolling_net("2026-07")
    latest = series["2026-07"]
    rank = 1 + sum(v > latest for v in series.values())
    history = next(i for i in a.context if i.id == "history")
    assert f"#{rank} highest of {len(series)}" in history.text
    assert "does not indicate economic significance" in (history.caveat or "")


def test_first_release_has_explicit_limitations_not_errors(rt) -> None:
    ids = ingest_months(rt, "2026-06")
    a = _analysis(rt, ids["2026-06"])
    assert a is not None
    assert a.revisions.available is False and "No earlier vintage" in a.revisions.note
    assert a.previous_comparison.available is False
    assert 3 <= len(a.executive_summary) <= 5


def test_none_when_no_vintage_or_other_series(rt) -> None:
    from tests.support import NOW, release_ref_for

    ref = release_ref_for("2026-07")
    release_id = repo.upsert_release(rt.conn, ref, NOW)
    assert _analysis(rt, release_id) is None  # known release, nothing ingested yet
    assert build_release_analysis(rt.conn, 99999, analysable_slugs=SLUGS) is None
    from nzstats.sources.calendar import events_to_refs, parse_ics

    other = next(r for r in events_to_refs(parse_ics(fixture_text("calendar_export_excerpt.ics")))
                 if r.series_slug != "international-migration")
    assert _analysis(rt, repo.upsert_release(rt.conn, other, NOW)) is None


def test_inference_is_labelled_and_hedged(both) -> None:
    rt, ids = both
    a = _analysis(rt, ids["2026-07"])
    for insight in a.interpretation:
        if insight.kind == "inference":
            assert "not" in insight.text.lower() or "mechanical" in insight.text.lower()
    banned = ("because of", "caused by", "due to", "driven by policy", "as a result of")
    for insight in [*a.executive_summary, *a.context, *a.interpretation]:
        assert not any(b in insight.text.lower() for b in banned), insight.text
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && pytest tests/insights tests/store/test_repo_views.py -v`
Expected: collection errors (`nzstats.insights`, `repo.release_vintage`, `tests.support.ingest_months` missing).

- [ ] **Step 3: Implement repo additions, support helper, models, catalog**

Append to `backend/tests/support.py`:

```python
def ingest_months(rt, *months: str) -> dict[str, int]:
    """Seed releases as published and ingest their real fixture files, oldest first."""
    from nzstats.pipeline.ingest import ingest_release
    from nzstats.store import repo

    ids: dict[str, int] = {}
    for month in months:
        ref = release_ref_for(month)
        ids[month] = repo.upsert_release(rt.conn, ref, NOW)
        outcome = ingest_release(rt, ref.release_key, now_fn=lambda: NOW)
        assert outcome.outcome == "ingested", outcome.detail
    return ids
```

Append to `store/repo.py`:

```python
@dataclass(frozen=True)
class ObservationRow:
    period: str
    value: float
    status: ObsStatus
    std_error: float | None
    released_in: str | None


def get_series_row(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM series WHERE key = ?", (key,)).fetchone()


def get_release_by_id(conn: sqlite3.Connection, release_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM release WHERE id = ?", (release_id,)).fetchone()


def vintage_observations(conn: sqlite3.Connection, vintage_id: int) -> dict[str, ObservationRow]:
    rows = conn.execute(
        "SELECT period, value, status, std_error, released_in FROM observation"
        " WHERE vintage_id = ? ORDER BY period", (vintage_id,)).fetchall()
    return {r["period"]: ObservationRow(r["period"], r["value"], ObsStatus(r["status"]),
                                        r["std_error"], r["released_in"]) for r in rows}


def release_vintage(
    conn: sqlite3.Connection, series_key: str, release_id: int
) -> VintageInfo | None:
    row = conn.execute(
        "SELECT v.id, r.release_key, r.title, r.published_at, v.captured_at, v.source_kind,"
        " v.layout_version FROM vintage v JOIN release r ON r.id = v.release_id"
        " JOIN series s ON s.id = v.series_id WHERE s.key = ? AND v.release_id = ?"
        " ORDER BY v.id DESC LIMIT 1", (series_key, release_id)).fetchone()
    return VintageInfo(*tuple(row)) if row else None


def previous_vintage(
    conn: sqlite3.Connection, series_key: str, published_before_utc: str
) -> VintageInfo | None:
    prior = [i for i in list_vintages(conn, series_key) if i.published_at < published_before_utc]
    return prior[-1] if prior else None


def series_overview(
    conn: sqlite3.Connection, category_prefix: str | None = None
) -> list[sqlite3.Row]:
    like = None if category_prefix is None else category_prefix + "%"
    return conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM vintage v WHERE v.series_id = s.id) AS n_vintages,"
        " (SELECT MAX(o.period) FROM observation o WHERE o.vintage_id = ("
        "   SELECT v.id FROM vintage v JOIN release r ON r.id = v.release_id"
        "   WHERE v.series_id = s.id ORDER BY r.published_at DESC, v.id DESC LIMIT 1))"
        " AS latest_period FROM series s WHERE (? IS NULL OR s.category LIKE ?) ORDER BY s.key",
        (like, like)).fetchall()
```

Because `previous_points` compares `published_at < cutoff` on UTC strings, `previous_vintage` takes the cutoff as a UTC ISO string (callers pass the release row's `published_at`).

`backend/src/nzstats/catalog.py`:

```python
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
    "household-labour-force-survey-estimated-working-age-population":
        CategoryInfo("Labour market", "low"),
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
```

`backend/src/nzstats/models.py`:

```python
"""Response contracts shared by insights and the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChangeOut(BaseModel):
    label: str
    comparison_period: str
    previous: float
    absolute: float
    percent: float | None  # None = not meaningful (zero/negative base or sign change)


class Evidence(BaseModel):
    series_key: str
    period: str
    value: float
    release_key: str  # the release whose vintage holds this observation


class Insight(BaseModel):
    id: str
    kind: Literal["observation", "inference"]
    text: str
    evidence: list[Evidence]
    caveat: str | None = None


class Metric(BaseModel):
    series_key: str
    label: str
    value: float
    unit: str
    frequency: str
    period: str
    period_label: str
    status: str
    std_error: float | None
    change_prior: ChangeOut | None
    change_year_ago: ChangeOut | None


class RevisionRowOut(BaseModel):
    period: str
    original: float
    revised: float
    absolute: float
    percent: float | None
    original_status: str
    revised_status: str


class RevisionBlock(BaseModel):
    available: bool
    note: str
    series_key: str
    against_title: str | None
    n_common: int
    n_revised: int
    mean_abs: float | None
    largest: list[RevisionRowOut]


class Decomposition(BaseModel):
    label: str
    series_key: str
    previous_release_title: str
    previous_period: str
    previous_published_value: float
    same_period_now: float
    new_period: str
    new_value: float
    revision_component: float
    new_period_component: float
    total_change: float


class PreviousComparison(BaseModel):
    available: bool
    note: str
    previous_release_title: str | None
    decompositions: list[Decomposition]


class Methodology(BaseModel):
    definitions: list[str]
    notes: list[str]
    source_url: str | None


class ReleaseSummary(BaseModel):
    id: int
    release_key: str
    title: str
    series_slug: str
    category: str
    importance: str
    period_label: str | None
    published_at: str  # Pacific/Auckland ISO-8601 with offset
    status: str
    headline: str | None
    page_url: str | None
    has_analysis: bool


class ReleaseAnalysis(BaseModel):
    release: ReleaseSummary
    executive_summary: list[Insight]
    headline_metrics: list[Metric]
    context: list[Insight]
    previous_comparison: PreviousComparison
    revisions: RevisionBlock
    interpretation: list[Insight]
    methodology: Methodology
    vintage_captured_at: str


class ReleaseDetail(BaseModel):
    release: ReleaseSummary
    analysis: ReleaseAnalysis | None
    unavailable_reason: str | None


class SourceHealthOut(BaseModel):
    source: str
    state: str
    last_checked_at: str | None
    last_success_at: str | None
    detail: str | None


class RunOut(BaseModel):
    release_key: str
    started_at: str
    outcome: str
    error_class: str | None
    detail: str | None


class HealthOut(BaseModel):
    generated_at: str
    database_ok: bool
    sources: list[SourceHealthOut]
    recent_runs: list[RunOut]
    release_counts: dict[str, int]
    series_count: int
    vintage_count: int


class CalendarOut(BaseModel):
    items: list[ReleaseSummary]
    last_checked_at: str | None
    last_success_at: str | None


class SeriesOut(BaseModel):
    key: str
    name: str
    unit: str
    frequency: str
    adjustment: str
    category: str
    definition: str
    definition_id: str
    latest_period: str | None
    n_vintages: int


class PointOut(BaseModel):
    period: str
    value: float
    status: str
    std_error: float | None
    released_in: str | None


class VintageOut(BaseModel):
    release_key: str
    title: str
    published_at: str
    captured_at: str
    source_kind: str
    layout_version: str


class SeriesDataOut(BaseModel):
    series: SeriesOut
    vintage: VintageOut
    points: list[PointOut]
    source_url: str | None
    caveat: str


class RevisionHistoryRow(BaseModel):
    release_key: str
    title: str
    published_at: str
    n_common: int
    n_revised: int
    mean_abs: float | None
    max_abs_period: str | None
    max_abs: float | None


class Coverage(BaseModel):
    kind: Literal["release_files", "snapshot", "none"]
    n_vintages: int
    earliest_release: str | None
    note: str


class RevisionsOut(BaseModel):
    series: SeriesOut
    coverage: Coverage
    base: VintageOut | None
    compare: VintageOut | None
    n_common: int
    n_revised: int
    rows: list[RevisionRowOut]  # revised periods only, oldest first
    history: list[RevisionHistoryRow]


class CountryRank(BaseModel):
    name: str
    series_key: str
    value: float
    prior_value: float | None
    change: float | None
    change_percent: float | None
    share_percent: float | None
    provisional: bool


class CountriesOut(BaseModel):
    available: bool
    months: int
    period_start: str | None
    period_end: str | None
    total: float | None
    countries: list[CountryRank]
    regions: list[CountryRank]
    unallocated: CountryRank | None
    derived: bool
    note: str


class Kpi(BaseModel):
    metric: Metric
    release_id: int
    published_at: str
    source_url: str | None


class FeaturedOut(BaseModel):
    release: ReleaseSummary
    headline: str | None
    first_insight: str | None


class InactiveCategory(BaseModel):
    name: str
    reason: str


class OverviewOut(BaseModel):
    generated_at: str
    kpis: list[Kpi]
    latest_releases: list[ReleaseSummary]
    upcoming: list[ReleaseSummary]
    freshness: list[SourceHealthOut]
    featured: FeaturedOut | None
    inactive_categories: list[InactiveCategory]
```

- [ ] **Step 4: Implement formatting, summary and the analysis builder**

`backend/src/nzstats/insights/__init__.py` (empty). `insights/format.py`:

```python
from __future__ import annotations


def fmt_int(v: float) -> str:
    return f"{round(v):,}"


def fmt_signed(v: float) -> str:
    n = round(v)
    return "0" if n == 0 else f"{'+' if n > 0 else '-'}{abs(n):,}"


def fmt_net(v: float) -> str:
    n = round(v)
    if n == 0:
        return "no net change"
    return f"a net {'gain' if n > 0 else 'loss'} of {abs(n):,} people"


def dir_word(v: float) -> str:
    return "rose" if v > 0 else "fell" if v < 0 else "was unchanged"
```

`insights/summary.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Collection

from nzstats.clock import to_akl_iso
from nzstats.models import ReleaseSummary
from nzstats.store import repo


def release_summary(
    conn: sqlite3.Connection, row: sqlite3.Row, *, analysable_slugs: Collection[str]
) -> ReleaseSummary:
    info = category_for(row["series_slug"])
    return ReleaseSummary(
        id=row["id"], release_key=row["release_key"], title=row["title"],
        series_slug=row["series_slug"], category=info.category, importance=info.importance,
        period_label=row["period_label"], published_at=to_akl_iso(row["published_at"]),
        status=row["status"], headline=row["headline"], page_url=row["page_url"],
        has_analysis=row["series_slug"] in analysable_slugs
        and repo.has_any_vintage(conn, row["id"]),
    )
```

`insights/migration.py`:

```python
"""Deterministic analysis of an International migration release (no LLM, no causal claims)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection
from dataclasses import dataclass

from nzstats.adapters.migration.series import OUTCOMES_DEFINITION
from nzstats.clock import to_akl_iso
from nzstats.domain import ObsStatus, Point
from nzstats.insights.format import dir_word, fmt_int, fmt_net, fmt_signed
from nzstats.insights.summary import release_summary
from nzstats.models import (ChangeOut, Decomposition, Evidence, Insight, Methodology, Metric,
                            PreviousComparison, ReleaseAnalysis, RevisionBlock, RevisionRowOut)
from nzstats.stats.changes import Change, lagged_change
from nzstats.stats.percentile import percentile_context
from nzstats.stats.periods import month_label
from nzstats.stats.revision import revisions, summarise
from nzstats.store import repo

SLUG = "international-migration"
NEEDED = ("mig.m.arrivals", "mig.m.departures", "mig.m.net", "mig.ry.arrivals",
          "mig.ry.departures", "mig.ry.net", "mig.ry.net.nz", "mig.ry.net.nonnz")
METRICS = (
    ("mig.ry.net", "Net migration, year ended"),
    ("mig.m.net", "Net migration, month"),
    ("mig.ry.arrivals", "Migrant arrivals, year ended"),
    ("mig.ry.departures", "Migrant departures, year ended"),
    ("mig.m.arrivals", "Migrant arrivals, month"),
    ("mig.m.departures", "Migrant departures, month"),
    ("mig.ry.net.nonnz", "Net migration, non-NZ citizens, year ended"),
    ("mig.ry.net.nz", "Net migration, NZ citizens, year ended"),
)
PERFECT = {"rose": "risen", "fell": "fallen"}
RANK_CAVEAT = ("Rank describes position within the published series only; it does not indicate "
               "economic significance.")


@dataclass(frozen=True)
class _S:
    key: str
    unit: str
    frequency: str
    vintage: repo.VintageInfo
    obs: dict[str, repo.ObservationRow]

    @property
    def values(self) -> dict[str, float]:
        return {p: o.value for p, o in self.obs.items()}

    @property
    def latest(self) -> str:
        return max(self.obs)

    def label(self, period: str) -> str:
        if self.frequency == "rolling_annual":
            return f"year ended {month_label(period)}"
        return month_label(period)

    def evidence(self, period: str) -> Evidence:
        return Evidence(series_key=self.key, period=period, value=self.obs[period].value,
                        release_key=self.vintage.release_key)


def _load(
    conn: sqlite3.Connection, pick: Callable[[str], repo.VintageInfo | None]
) -> dict[str, _S] | None:
    out: dict[str, _S] = {}
    for key in NEEDED:
        vintage, series = pick(key), repo.get_series_row(conn, key)
        if vintage is None or series is None:
            return None
        out[key] = _S(key, series["unit"], series["frequency"], vintage,
                      repo.vintage_observations(conn, vintage.vintage_id))
    return out


def _change(s: _S, lag: int) -> tuple[Change | None, ChangeOut | None]:
    ch = lagged_change(s.values, s.latest, lag)
    if ch is None:
        return None, None
    return ch, ChangeOut(label=f"vs {s.label(ch.comparison_period)}",
                         comparison_period=ch.comparison_period, previous=ch.previous,
                         absolute=ch.absolute, percent=ch.percent)


def _metric(s: _S, label: str) -> Metric:
    o = s.obs[s.latest]
    _, prior = _change(s, 1)
    _, yago = _change(s, 12)
    period_label = s.label(s.latest)
    return Metric(
        series_key=s.key, label=label, value=o.value, unit=s.unit, frequency=s.frequency,
        period=s.latest, period_label=period_label[0].upper() + period_label[1:],
        status=o.status.value, std_error=o.std_error if o.status is ObsStatus.PROVISIONAL else None,
        change_prior=prior, change_year_ago=yago,
    )


def _points(s: _S) -> dict[str, Point]:
    return {p: Point(p, o.value, o.status) for p, o in s.obs.items()}


def _streak(values: dict[str, float]) -> tuple[int, str]:
    """Consecutive changes in the same direction ending at the latest period."""
    periods = sorted(values)
    direction, count = "", 0
    for i in range(len(periods) - 1, 0, -1):
        delta = values[periods[i]] - values[periods[i - 1]]
        step = "rose" if delta > 0 else "fell" if delta < 0 else ""
        if not step or (direction and step != direction):
            break
        direction, count = step, count + 1
    return count, direction


def build_release_analysis(
    conn: sqlite3.Connection, release_id: int, *, analysable_slugs: Collection[str]
) -> ReleaseAnalysis | None:
    row = repo.get_release_by_id(conn, release_id)
    if row is None or row["series_slug"] != SLUG:
        return None
    cur = _load(conn, lambda k: repo.release_vintage(conn, k, release_id))
    if cur is None:
        return None
    prev = _load(conn, lambda k: repo.previous_vintage(conn, k, row["published_at"]))
    summary = release_summary(conn, row, analysable_slugs=analysable_slugs)

    ry_net, ry_arr, ry_dep = cur["mig.ry.net"], cur["mig.ry.arrivals"], cur["mig.ry.departures"]
    m_net, m_arr, m_dep = cur["mig.m.net"], cur["mig.m.arrivals"], cur["mig.m.departures"]
    nz, nonnz = cur["mig.ry.net.nz"], cur["mig.ry.net.nonnz"]
    ye = ry_net.latest

    # ---- executive summary (observations)
    summary_items: list[Insight] = []
    net_now = ry_net.obs[ye].value
    status = ry_net.obs[ye].status.value
    ch_net, _ = _change(ry_net, 12)
    text = f"Net migration for the {ry_net.label(ye)} was {fmt_net(net_now)} ({status})"
    ev = [ry_net.evidence(ye)]
    if ch_net:
        text += f", compared with {fmt_net(ch_net.previous)} in the {ry_net.label(ch_net.comparison_period)}"
        ev.append(ry_net.evidence(ch_net.comparison_period))
    summary_items.append(Insight(id="headline", kind="observation", text=text + ".", evidence=ev))

    mp = m_net.latest
    summary_items.append(Insight(
        id="monthly", kind="observation",
        text=(f"In {month_label(mp)}, estimated migrant arrivals were {fmt_int(m_arr.obs[mp].value)} "
              f"and departures {fmt_int(m_dep.obs[mp].value)}, giving {fmt_net(m_net.obs[mp].value)} "
              f"({m_net.obs[mp].status.value})."),
        evidence=[m_arr.evidence(mp), m_dep.evidence(mp), m_net.evidence(mp)]))

    ch_arr, _ = _change(ry_arr, 12)
    ch_dep, _ = _change(ry_dep, 12)
    if ch_net and ch_arr and ch_dep:
        yp = ch_net.comparison_period
        summary_items.append(Insight(
            id="drivers", kind="observation",
            text=(f"Compared with the {ry_net.label(yp)}, arrivals {dir_word(ch_arr.absolute)} by "
                  f"{fmt_int(abs(ch_arr.absolute))} and departures {dir_word(ch_dep.absolute)} by "
                  f"{fmt_int(abs(ch_dep.absolute))}; the change in net migration "
                  f"({fmt_signed(ch_net.absolute)}) is the difference between the two."),
            evidence=[ry_arr.evidence(ye), ry_arr.evidence(yp), ry_dep.evidence(ye),
                      ry_dep.evidence(yp), ry_net.evidence(ye), ry_net.evidence(yp)]))

    # ---- previous release: revisions vs genuinely new reference periods
    rev_block, prev_cmp, rev_insight = _previous(cur, prev, m_net)
    summary_items.append(rev_insight)

    prov = sorted(p for p, o in m_net.obs.items() if o.status is ObsStatus.PROVISIONAL)
    if prov:
        se = m_net.obs[mp].std_error
        suffix = f"; the latest monthly net estimate has a standard error of {fmt_int(se)}" if se else ""
        summary_items.append(Insight(
            id="provisional", kind="observation",
            text=(f"Estimates from {month_label(prov[0])} to {month_label(prov[-1])} are provisional "
                  f"and will be revised as travel outcomes become known{suffix}."),
            evidence=[m_net.evidence(prov[0]), m_net.evidence(prov[-1])]))
    else:
        summary_items.append(Insight(
            id="provisional", kind="observation",
            text="All estimates in this release are final.", evidence=[m_net.evidence(mp)]))

    # ---- context
    context: list[Insight] = []
    ctx = percentile_context(net_now, list(ry_net.values.values()))
    if ctx:
        first = min(ry_net.obs)
        context.append(Insight(
            id="history", kind="observation",
            text=(f"The {ry_net.label(ye)} net figure ranks #{ctx.rank} highest of {ctx.n} "
                  f"year-ended observations since {month_label(first)}."),
            evidence=[ry_net.evidence(ye)], caveat=RANK_CAVEAT))
    context.append(Insight(
        id="citizenship", kind="observation",
        text=(f"By citizenship, net migration of non-NZ citizens was {fmt_net(nonnz.obs[nonnz.latest].value)} "
              f"and of NZ citizens {fmt_net(nz.obs[nz.latest].value)} ({nonnz.label(nonnz.latest)})."),
        evidence=[nonnz.evidence(nonnz.latest), nz.evidence(nz.latest)]))

    # ---- interpretation (arithmetic observation + one hedged inference)
    interpretation: list[Insight] = []
    if ch_arr and ch_dep and (abs(ch_arr.absolute) + abs(ch_dep.absolute)) > 0:
        arr_part, dep_part = abs(ch_arr.absolute), abs(ch_dep.absolute)
        lead, share = (("Arrivals", arr_part) if arr_part >= dep_part else ("Departures", dep_part))
        interpretation.append(Insight(
            id="driver-share", kind="observation",
            text=(f"{lead} account for {share / (arr_part + dep_part):.0%} of the combined movement "
                  f"in arrivals and departures behind the year-on-year change in net migration."),
            evidence=[ry_arr.evidence(ye), ry_dep.evidence(ye)]))
    streak, direction = _streak(ry_net.values)
    if streak >= 3:
        interpretation.append(Insight(
            id="streak", kind="inference",
            text=(f"The year-ended net figure has {PERFECT[direction]} for {streak} consecutive months. "
                  f"Adjacent year-ended values share eleven of twelve months, so this persistence "
                  f"is partly mechanical and is not by itself evidence of a sustained shift or "
                  f"of its cause."),
            evidence=[ry_net.evidence(ye)],
            caveat="Inference from the published series; the data do not identify causes."))

    methodology = Methodology(
        definitions=[
            OUTCOMES_DEFINITION,
            "Monthly figures are mean estimates; year-ended figures are Stats NZ's published "
            "rolling twelve-month totals. The two are different series and are never combined.",
        ],
        notes=[
            "Figures are the unrounded values in Stats NZ's published data files; the release "
            "headline text may state rounded figures.",
            "Final estimates are reported with a standard error of zero in the source files.",
        ],
        source_url=row["page_url"],
    )
    return ReleaseAnalysis(
        release=summary, executive_summary=summary_items,
        headline_metrics=[_metric(cur[k], label) for k, label in METRICS],
        context=context, previous_comparison=prev_cmp, revisions=rev_block,
        interpretation=interpretation, methodology=methodology,
        vintage_captured_at=to_akl_iso(m_net.vintage.captured_at),
    )


def _previous(
    cur: dict[str, _S], prev: dict[str, _S] | None, m_net: _S
) -> tuple[RevisionBlock, PreviousComparison, Insight]:
    if prev is None:
        note = ("No earlier vintage is stored for this series, so revisions and changes since the "
                "previous release cannot be assessed. Revision history only covers releases "
                "ingested by this monitor.")
        block = RevisionBlock(available=False, note=note, series_key="mig.m.net",
                              against_title=None, n_common=0, n_revised=0, mean_abs=None,
                              largest=[])
        cmp_ = PreviousComparison(available=False, note=note, previous_release_title=None,
                                  decompositions=[])
        return block, cmp_, Insight(id="revisions", kind="observation", text=note,
                                    evidence=[m_net.evidence(m_net.latest)])

    prev_net = prev["mig.m.net"]
    revs = revisions(_points(prev_net), _points(m_net))
    summ = summarise(revs)
    changed = sorted((r for r in revs if r.absolute != 0), key=lambda r: abs(r.absolute),
                     reverse=True)
    largest = [RevisionRowOut(period=r.period, original=r.original, revised=r.revised,
                              absolute=r.absolute, percent=r.percent,
                              original_status=r.original_status.value,
                              revised_status=r.revised_status.value) for r in changed[:8]]
    title = prev_net.vintage.title
    block = RevisionBlock(
        available=True, note=f"Compared with the {title} release.", series_key="mig.m.net",
        against_title=title, n_common=summ.n_common, n_revised=summ.n_revised,
        mean_abs=summ.mean_abs, largest=largest)
    if summ.max_abs is not None:
        top = summ.max_abs
        text = (f"Compared with the {title} release, {summ.n_revised} of {summ.n_common} overlapping "
                f"monthly net estimates were revised; the largest was {month_label(top.period)}: "
                f"{fmt_int(top.original)} to {fmt_int(top.revised)} ({fmt_signed(top.absolute)}).")
        evidence = [prev_net.evidence(top.period), m_net.evidence(top.period)]
    else:
        text = (f"Compared with the {title} release, none of the {summ.n_common} overlapping "
                f"monthly net estimates were revised.")
        evidence = [m_net.evidence(m_net.latest)]
    insight = Insight(id="revisions", kind="observation", text=text, evidence=evidence)

    decomposition = []
    for key, label in (("mig.ry.net", "Net migration, year ended"),
                       ("mig.m.net", "Net migration, month")):
        c, p = cur[key], prev[key]
        old_latest, new_latest = p.latest, c.latest
        if new_latest == old_latest or old_latest not in c.obs:
            continue
        a, b, n = p.obs[old_latest].value, c.obs[old_latest].value, c.obs[new_latest].value
        decomposition.append(Decomposition(
            label=label, series_key=key, previous_release_title=title,
            previous_period=old_latest, previous_published_value=a, same_period_now=b,
            new_period=new_latest, new_value=n, revision_component=b - a,
            new_period_component=n - b, total_change=n - a))
    cmp_ = PreviousComparison(
        available=True,
        note=("Change since the previous release is split into the revision of the previous "
              "reference period and the movement to the new reference period."),
        previous_release_title=title, decompositions=decomposition)
    return block, cmp_, insight
```

- [ ] **Step 5: Run to verify pass; lint**

Run: `cd backend && pytest tests/insights tests/store -v && ruff check --fix . && ruff format .`
Expected: PASS. If `test_history_rank…` fails, print `history.text` and compare with the independent rank before changing either side; a mismatch means the stored series differs from the published chart.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add response models, catalog and deterministic release analysis

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Revision view, country ranking, overview and the read-only API

**Files:**
- Create: `backend/src/nzstats/insights/{revisions,countries,overview}.py`
- Create: `backend/src/nzstats/api/{__init__,deps,routes,app}.py`
- Modify: `backend/src/nzstats/pipeline/discover.py` (add `discovery_months`), `backend/src/nzstats/scheduler/jobs.py` and `backend/src/nzstats/cli.py` (use it)
- Test: `backend/tests/insights/test_revisions.py`, `test_countries.py`, `backend/tests/api/{__init__,test_api,test_empty_db,test_static}.py`, extend `backend/tests/pipeline/test_discover.py`

**Interfaces:**
- Consumes: Task 11 models and `build_release_analysis`; repo views; `stats.*`.
- Produces:
  - `discover.discovery_months(now: datetime) -> list[str]` (previous, current, next Auckland months)
  - `insights.revisions.revision_view(conn, series_key: str, *, base_release_key: str | None = None, compare_release_key: str | None = None) -> RevisionsOut | None`
  - `insights.countries.rank_countries(conn, *, months: int = 12, top: int = 15) -> CountriesOut`
  - `insights.overview.build_overview(conn, *, analysable_slugs, now: datetime) -> OverviewOut`
  - `api.app.create_app(settings: Settings | None = None, *, start_scheduler: bool = False, runtime: Runtime | None = None) -> FastAPI`
  - HTTP (all under `/api`, JSON unless stated): `GET /health`, `GET /overview`, `GET /releases?status=&category=&limit=&offset=`, `GET /releases/{id}`, `GET /calendar?from=&to=`, `GET /series?category=`, `GET /series/{key}?vintage=&from=&to=`, `GET /series/{key}/csv` (text/csv), `GET /revisions/{key}?base=&compare=`, `GET /migration/countries?months=&top=`. Unknown series/release/vintage → 404 with `{"detail": ...}`.

Semantics: country ranking is **derived** (sum of the last `months` monthly estimates of arrivals by country of last permanent residence; rows absent in the source are treated as zero — consistent with the per-release country-sum reconciliation check); regions and "Not Stated" are reported separately and never ranked among countries; `prior_value`/change are `None` when the prior window is not fully stored. Revision coverage states honestly whether vintages come from official release files or monitor snapshots.

- [ ] **Step 1: Add `discovery_months` (previous, current, next) with a test**

Append to `tests/pipeline/test_discover.py`:

```python
def test_discovery_months_include_the_previous_month() -> None:
    from nzstats.pipeline.discover import discovery_months

    assert discovery_months(datetime(2026, 10, 11, tzinfo=timezone.utc)) == [
        "2026-09", "2026-10", "2026-11"]
    assert discovery_months(datetime(2027, 1, 5, tzinfo=timezone.utc)) == [
        "2026-12", "2027-01", "2027-02"]
```

Add to `pipeline/discover.py`:

```python
def discovery_months(now: datetime) -> list[str]:
    current, following = current_and_next_months(now)
    return [add_months(current, -1), current, following]
```

In `scheduler/jobs.py` use `discovery_months(now_fn())` instead of `current_and_next_months(now_fn())` in `job_refresh_calendar`; in `cli.py` use it for the `discover` command. Run `pytest tests/pipeline tests/scheduler -v` — expected PASS (the existing `current_and_next_months` test remains valid).

- [ ] **Step 2: Write the failing insight tests**

`backend/tests/insights/test_revisions.py`:

```python
import pandas as pd

from nzstats.insights.revisions import revision_view
from nzstats.store import repo
from tests.conftest import FIXTURES
from tests.support import ingest_months


def _net(name):
    df = pd.read_csv(FIXTURES / name)
    t = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    return dict(zip(t.year_month, t.estimate, strict=True))


def test_default_view_compares_latest_with_previous_vintage(rt) -> None:
    ingest_months(rt, "2026-06", "2026-07")
    view = revision_view(rt.conn, "mig.m.net")
    old, new = _net("im_2026-06_age_sex.csv"), _net("im_2026-07_age_sex.csv")
    expected = {p for p in old.keys() & new.keys() if old[p] != new[p]}
    assert {r.period for r in view.rows} == expected
    assert view.n_revised == len(expected) and view.n_common == len(old.keys() & new.keys())
    assert view.base.title.endswith("June 2026") and view.compare.title.endswith("July 2026")
    assert view.coverage.kind == "release_files" and view.coverage.n_vintages == 2
    assert [h.title for h in view.history] == [view.compare.title]
    assert [r.period for r in view.rows] == sorted(r.period for r in view.rows)


def test_explicit_vintages_and_unknown_vintage(rt) -> None:
    ids = ingest_months(rt, "2026-06", "2026-07")
    june = repo.get_release_by_id(rt.conn, ids["2026-06"])["release_key"]
    july = repo.get_release_by_id(rt.conn, ids["2026-07"])["release_key"]
    swapped = revision_view(rt.conn, "mig.m.net", base_release_key=july, compare_release_key=june)
    assert swapped.base.release_key == july and swapped.compare.release_key == june
    assert revision_view(rt.conn, "mig.m.net", base_release_key="nope") is None


def test_single_vintage_states_the_limitation(rt) -> None:
    ingest_months(rt, "2026-07")
    view = revision_view(rt.conn, "mig.m.net")
    assert view.rows == [] and view.base is None and view.compare is None
    assert "at least two vintages" in view.coverage.note
    assert view.coverage.n_vintages == 1


def test_unknown_series_is_none(rt) -> None:
    assert revision_view(rt.conn, "nope") is None
```

`backend/tests/insights/test_countries.py`:

```python
import pandas as pd
import pytest

from nzstats.adapters.migration.parse import REGIONS, UNALLOCATED
from nzstats.insights.countries import rank_countries
from tests.conftest import FIXTURES
from tests.support import ingest_months


def _expected():
    df = pd.read_csv(FIXTURES / "im_2026-07_citizenship_country.csv")
    sel = df[(df.visa == "TOTAL") & (df.citizenship == "TOTAL") & (df.direction == "Arrivals")
             & (df.year_month >= "2025-08")]
    countries = sel[~sel.country_of_residence.isin(REGIONS | UNALLOCATED | {"TOTAL"})]
    return countries.groupby("country_of_residence").estimate.sum().sort_values(ascending=False)


def test_ranking_matches_independent_sums_and_excludes_regions(rt) -> None:
    ingest_months(rt, "2026-07")
    out = rank_countries(rt.conn, months=12, top=5)
    expected = _expected()
    assert out.available and out.derived
    assert (out.period_start, out.period_end) == ("2025-08", "2026-07")
    assert [c.name for c in out.countries] == list(expected.index[:5])
    assert [c.value for c in out.countries] == [float(v) for v in expected.values[:5]]
    assert {r.name for r in out.regions} == set(REGIONS)
    assert out.unallocated is not None and out.unallocated.name == "Not Stated"
    assert all(c.name not in REGIONS for c in out.countries)
    assert out.countries[0].share_percent == pytest.approx(
        out.countries[0].value / out.total * 100)
    assert all(c.prior_value is None and c.change is None for c in out.countries)  # 14 months stored
    assert any(c.provisional for c in out.countries)


def test_not_available_before_any_ingestion(rt) -> None:
    out = rank_countries(rt.conn)
    assert out.available is False and out.countries == [] and "No country data" in out.note

```

- [ ] **Step 3: Implement revisions and countries**

`backend/src/nzstats/insights/revisions.py`:

```python
from __future__ import annotations

import sqlite3

from nzstats.clock import to_akl_iso
from nzstats.domain import Point
from nzstats.models import (Coverage, RevisionHistoryRow, RevisionRowOut, RevisionsOut,
                            SeriesOut, VintageOut)
from nzstats.stats.revision import revisions, summarise
from nzstats.store import repo


def series_out(row: sqlite3.Row, n_vintages: int, latest_period: str | None) -> SeriesOut:
    return SeriesOut(key=row["key"], name=row["name"], unit=row["unit"],
                     frequency=row["frequency"], adjustment=row["seasonal_adjustment"],
                     category=row["category"], definition=row["definition"],
                     definition_id=row["definition_id"], latest_period=latest_period,
                     n_vintages=n_vintages)


def vintage_out(v: repo.VintageInfo) -> VintageOut:
    return VintageOut(release_key=v.release_key, title=v.title,
                      published_at=to_akl_iso(v.published_at), captured_at=to_akl_iso(v.captured_at),
                      source_kind=v.source_kind, layout_version=v.layout_version)


def _points(conn: sqlite3.Connection, v: repo.VintageInfo) -> dict[str, Point]:
    return repo.vintage_points(conn, v.vintage_id)


def _coverage(vintages: list[repo.VintageInfo]) -> Coverage:
    if not vintages:
        return Coverage(kind="none", n_vintages=0, earliest_release=None,
                        note="No data has been ingested for this series yet.")
    kinds = {v.source_kind for v in vintages}
    earliest = vintages[0]
    if kinds == {"release_files"}:
        note = (f"Vintages are the official data files published with each Stats NZ release: "
                f"{len(vintages)} stored, earliest {earliest.title}. Revisions before that "
                f"release cannot be observed.")
        kind = "release_files"
    else:
        note = (f"Revision history only covers snapshots captured since this monitor began "
                f"operating (earliest {earliest.title}).")
        kind = "snapshot"
    if len(vintages) < 2:
        note += " At least two vintages are needed to show revisions."
    return Coverage(kind=kind, n_vintages=len(vintages), earliest_release=earliest.title, note=note)


def revision_view(
    conn: sqlite3.Connection, series_key: str, *,
    base_release_key: str | None = None, compare_release_key: str | None = None,
) -> RevisionsOut | None:
    row = repo.get_series_row(conn, series_key)
    if row is None:
        return None
    vintages = repo.list_vintages(conn, series_key)
    latest = max(repo.vintage_points(conn, vintages[-1].vintage_id)) if vintages else None
    series = series_out(row, len(vintages), latest)
    coverage = _coverage(vintages)
    if len(vintages) < 2:
        return RevisionsOut(series=series, coverage=coverage, base=None, compare=None,
                            n_common=0, n_revised=0, rows=[], history=[])

    by_key = {v.release_key: v for v in vintages}  # later vintages of a release win
    compare = by_key.get(compare_release_key) if compare_release_key else vintages[-1]
    if compare is None:
        return None
    if base_release_key:
        base = by_key.get(base_release_key)
    else:
        earlier = [v for v in vintages if v.vintage_id < compare.vintage_id
                   and v.published_at <= compare.published_at]
        base = earlier[-1] if earlier else None
    if base is None:
        return None

    revs = revisions(_points(conn, base), _points(conn, compare))
    summary = summarise(revs)
    rows = [RevisionRowOut(period=r.period, original=r.original, revised=r.revised,
                           absolute=r.absolute, percent=r.percent,
                           original_status=r.original_status.value,
                           revised_status=r.revised_status.value)
            for r in revs if r.absolute != 0]

    history = []
    for older, newer in zip(vintages, vintages[1:], strict=False):
        s = summarise(revisions(_points(conn, older), _points(conn, newer)))
        history.append(RevisionHistoryRow(
            release_key=newer.release_key, title=newer.title,
            published_at=to_akl_iso(newer.published_at), n_common=s.n_common,
            n_revised=s.n_revised, mean_abs=s.mean_abs,
            max_abs_period=s.max_abs.period if s.max_abs else None,
            max_abs=s.max_abs.absolute if s.max_abs else None))
    return RevisionsOut(series=series, coverage=coverage, base=vintage_out(base),
                        compare=vintage_out(compare), n_common=summary.n_common,
                        n_revised=summary.n_revised, rows=rows, history=history)
```

`backend/src/nzstats/insights/countries.py`:

```python
"""Derived country ranking: sum of the last N monthly arrivals by country of last residence."""

from __future__ import annotations

import sqlite3

from nzstats.domain import ObsStatus
from nzstats.models import CountriesOut, CountryRank
from nzstats.stats.periods import add_months, month_range
from nzstats.store import repo

NOTE = ("Derived: Stats NZ's published monthly estimates summed over the window. Months absent "
        "from the source are treated as zero. Regions and 'Not Stated' are not ranked as "
        "countries.")
CATEGORIES = ("migration:country", "migration:region", "migration:unallocated")


def _first_country_period(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT MIN(o.period) FROM observation o JOIN vintage v ON v.id = o.vintage_id"
        " JOIN series s ON s.id = v.series_id WHERE s.category = 'migration:country'").fetchone()
    return row[0]


def rank_countries(conn: sqlite3.Connection, *, months: int = 12, top: int = 15) -> CountriesOut:
    totals = {p: pt.value for p, pt in repo.latest_points(conn, "mig.m.arrivals").items()}
    first_stored = _first_country_period(conn)
    if not totals or first_stored is None:
        return CountriesOut(available=False, months=months, period_start=None, period_end=None,
                            total=None, countries=[], regions=[], unallocated=None, derived=True,
                            note="No country data has been ingested yet.")
    end = max(totals)
    start = add_months(end, -(months - 1))
    window = month_range(start, end)
    prior_window = month_range(add_months(start, -months), add_months(start, -1))
    prior_stored = prior_window[0] >= first_stored  # prior window fully inside stored history
    total = sum(totals.get(p, 0.0) for p in window)

    groups: dict[str, list[CountryRank]] = {c: [] for c in CATEGORIES}
    for row in repo.series_overview(conn, "migration:"):
        if row["category"] not in groups:
            continue
        points = repo.latest_points(conn, row["key"])
        if not points:
            continue
        value = sum(points[p].value for p in window if p in points)
        provisional = any(points[p].status is ObsStatus.PROVISIONAL for p in window if p in points)
        prior = sum(points[p].value for p in prior_window if p in points) if prior_stored else None
        name = row["name"].removeprefix("Migrant arrivals from ").removesuffix(" (monthly estimate)")
        groups[row["category"]].append(CountryRank(
            name=name, series_key=row["key"], value=value, prior_value=prior,
            change=None if prior is None else value - prior,
            change_percent=None if prior is None or prior <= 0 else (value - prior) / prior * 100,
            share_percent=(value / total * 100) if total > 0 else None, provisional=provisional))

    def ordered(items: list[CountryRank]) -> list[CountryRank]:
        return sorted(items, key=lambda c: (-c.value, c.name))

    unallocated = ordered(groups["migration:unallocated"])
    return CountriesOut(
        available=bool(groups["migration:country"]), months=months, period_start=start,
        period_end=end, total=total, countries=ordered(groups["migration:country"])[:top],
        regions=ordered(groups["migration:region"]),
        unallocated=unallocated[0] if unallocated else None, derived=True, note=NOTE)
```

`backend/src/nzstats/insights/overview.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Collection
from datetime import datetime

from nzstats.clock import to_akl_iso, to_utc_iso
from nzstats.insights.migration import SLUG, build_release_analysis
from nzstats.insights.summary import release_summary
from nzstats.catalog import INACTIVE_CATEGORIES
from nzstats.models import FeaturedOut, InactiveCategory, Kpi, OverviewOut, SourceHealthOut


def health_rows(conn: sqlite3.Connection) -> list[SourceHealthOut]:
    return [SourceHealthOut(
        source=r["source"], state=r["state"],
        last_checked_at=to_akl_iso(r["last_checked_at"]) if r["last_checked_at"] else None,
        last_success_at=to_akl_iso(r["last_success_at"]) if r["last_success_at"] else None,
        detail=r["detail"]) for r in conn.execute("SELECT * FROM source_health ORDER BY source")]


def build_overview(
    conn: sqlite3.Connection, *, analysable_slugs: Collection[str], now: datetime
) -> OverviewOut:
    now_s = to_utc_iso(now)
    latest = conn.execute(
        "SELECT r.* FROM release r WHERE r.series_slug = ? AND EXISTS ("
        " SELECT 1 FROM vintage v WHERE v.release_id = r.id) ORDER BY r.published_at DESC LIMIT 1",
        (SLUG,)).fetchone()
    kpis: list[Kpi] = []
    featured = None
    if latest is not None:
        analysis = build_release_analysis(conn, latest["id"], analysable_slugs=analysable_slugs)
        if analysis is not None:
            kpis = [Kpi(metric=m, release_id=latest["id"],
                        published_at=analysis.release.published_at, source_url=latest["page_url"])
                    for m in analysis.headline_metrics]
            featured = FeaturedOut(
                release=analysis.release, headline=analysis.release.headline,
                first_insight=analysis.executive_summary[0].text if analysis.executive_summary
                else None)

    def summaries(sql: str, params: tuple) -> list:
        return [release_summary(conn, r, analysable_slugs=analysable_slugs)
                for r in conn.execute(sql, params)]

    published = summaries(
        "SELECT * FROM release WHERE status IN ('published', 'corrected') AND published_at <= ?"
        " ORDER BY published_at DESC LIMIT 8", (now_s,))
    upcoming = summaries(
        "SELECT * FROM release WHERE status IN ('scheduled', 'delayed') AND published_at >= ?"
        " ORDER BY published_at ASC LIMIT 10", (now_s,))
    return OverviewOut(
        generated_at=to_akl_iso(now), kpis=kpis, latest_releases=published, upcoming=upcoming,
        freshness=health_rows(conn), featured=featured,
        inactive_categories=[InactiveCategory(name=n, reason=r) for n, r in INACTIVE_CATEGORIES])
```

- [ ] **Step 4: Write the failing API tests**

`backend/tests/api/test_api.py`:

```python
import csv
import io
from datetime import date, datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.clock import AKL
from nzstats.pipeline.discover import discover
from tests.conftest import FIXTURES
from tests.support import NOW, ingest_months


@pytest.fixture()
def client(rt):
    ids = ingest_months(rt, "2026-06", "2026-07")
    discover(rt, months=["2026-09", "2026-10"], now_fn=lambda: NOW)
    app = create_app(rt.settings)
    app.state.now = lambda: NOW  # deterministic "now" for the overview and calendar defaults
    with TestClient(app) as c:
        c.ids = ids
        yield c


def test_health(client) -> None:
    body = client.get("/api/health").json()
    assert body["database_ok"] is True
    sources = {s["source"]: s["state"] for s in body["sources"]}
    assert sources["release:international-migration"] == "ok"
    assert body["vintage_count"] > 0 and body["series_count"] > 10
    assert body["recent_runs"][0]["outcome"] in ("ingested", "unchanged")
    assert body["release_counts"].get("published", 0) >= 2


def test_releases_listing_and_filters(client) -> None:
    items = client.get("/api/releases").json()
    july = next(r for r in items if r["id"] == client.ids["2026-07"])
    assert july["has_analysis"] is True and july["category"] == "Migration"
    assert july["importance"] == "high" and july["published_at"].endswith("+12:00")
    assert items == sorted(items, key=lambda r: r["published_at"], reverse=True)
    only_sched = client.get("/api/releases", params={"status": "scheduled"}).json()
    assert only_sched and all(r["status"] == "scheduled" for r in only_sched)
    migration = client.get("/api/releases", params={"category": "Migration"}).json()
    assert migration and all(r["category"] == "Migration" for r in migration)
    assert len(client.get("/api/releases", params={"limit": 1}).json()) == 1


def test_release_detail_with_and_without_analysis(client) -> None:
    detail = client.get(f"/api/releases/{client.ids['2026-07']}").json()
    assert detail["analysis"]["executive_summary"] and detail["unavailable_reason"] is None
    scheduled = client.get("/api/releases", params={"status": "scheduled",
                                                    "category": "Migration"}).json()
    assert scheduled, "the ICS fixture always lists upcoming migration releases"
    d2 = client.get(f"/api/releases/{scheduled[0]['id']}").json()
    assert d2["analysis"] is None and "Scheduled" in d2["unavailable_reason"]
    other = client.get("/api/releases", params={"status": "scheduled"}).json()
    non_migration = next(r for r in other if r["category"] != "Migration")
    reason = client.get(f"/api/releases/{non_migration['id']}").json()["unavailable_reason"]
    assert "not yet available" in reason
    assert client.get("/api/releases/987654").status_code == 404


def test_calendar_range_and_freshness(client) -> None:
    scheduled = client.get("/api/releases", params={"status": "scheduled"}).json()
    first_day = min(s["published_at"][:10] for s in scheduled)
    last_day = (date.fromisoformat(first_day) + timedelta(days=20)).isoformat()
    body = client.get("/api/calendar", params={"from": first_day, "to": last_day}).json()
    assert body["items"] and body["last_checked_at"] and body["last_success_at"]
    dates = [i["published_at"][:10] for i in body["items"]]
    assert dates == sorted(dates) and all(first_day <= d <= last_day for d in dates)
    for item in body["items"]:  # offsets follow Auckland daylight saving for that date
        stamp = datetime.fromisoformat(item["published_at"])
        assert stamp.utcoffset() == AKL.utcoffset(stamp.replace(tzinfo=None))
    assert client.get("/api/calendar", params={"from": "nonsense"}).status_code == 422


def test_series_listing_and_data(client) -> None:
    listing = client.get("/api/series", params={"category": "migration"}).json()
    keys = {s["key"] for s in listing}
    assert {"mig.m.net", "mig.ry.net"} <= keys
    net = client.get("/api/series/mig.m.net").json()
    assert net["points"][-1] == {"period": "2026-07", "value": 5170.0, "status": "provisional",
                                 "std_error": 545.0, "released_in": "2026-07"}
    assert net["series"]["frequency"] == "monthly" and net["vintage"]["title"].endswith("July 2026")
    sliced = client.get("/api/series/mig.m.net", params={"from": "2026-01", "to": "2026-03"}).json()
    assert [p["period"] for p in sliced["points"]] == ["2026-01", "2026-02", "2026-03"]
    june = client.get("/api/series/mig.m.net", params={
        "vintage": client.get(f"/api/releases/{client.ids['2026-06']}").json()["release"]["release_key"]
    }).json()
    assert june["vintage"]["title"].endswith("June 2026")
    assert client.get("/api/series/nope").status_code == 404
    assert client.get("/api/series/mig.m.net", params={"vintage": "nope"}).status_code == 404
    assert client.get("/api/series/mig.m.net", params={"from": "2026"}).status_code == 422


def test_series_csv_download(client) -> None:
    r = client.get("/api/series/mig.m.net/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "mig.m.net.csv" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    df = pd.read_csv(FIXTURES / "im_2026-07_age_sex.csv")
    total = df[(df.sex == "TOTAL") & (df.age == "TOTAL") & (df.direction == "Net")]
    assert len(rows) == len(total)
    assert {"series_key", "unit", "period", "value", "status", "release", "source"} <= set(rows[0])
    assert "CC BY 4.0" in rows[0]["source"]


def test_revisions_endpoint(client) -> None:
    body = client.get("/api/revisions/mig.m.net").json()
    assert body["coverage"]["kind"] == "release_files" and body["n_revised"] > 0
    assert body["rows"] and body["history"]
    assert client.get("/api/revisions/nope").status_code == 404
    assert client.get("/api/revisions/mig.m.net", params={"base": "nope"}).status_code == 404


def test_countries_endpoint(client) -> None:
    body = client.get("/api/migration/countries", params={"months": 12, "top": 3}).json()
    assert body["available"] and len(body["countries"]) == 3 and body["derived"] is True
    assert client.get("/api/migration/countries", params={"months": 0}).status_code == 422


def test_overview(client) -> None:
    body = client.get("/api/overview").json()
    kpi = {k["metric"]["series_key"]: k for k in body["kpis"]}
    assert kpi["mig.ry.net"]["metric"]["period"] == "2026-07"
    assert kpi["mig.ry.net"]["source_url"].startswith("https://www.stats.govt.nz/")
    assert body["featured"]["release"]["id"] == client.ids["2026-07"]
    assert body["upcoming"] and all(u["status"] in ("scheduled", "delayed") for u in body["upcoming"])
    assert {c["name"] for c in body["inactive_categories"]} >= {"Prices and inflation"}
    assert any(f["source"] == "calendar_ics" for f in body["freshness"])


def test_openapi_builds(client) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/overview" in paths and "/api/series/{key}/csv" in paths
```

`backend/tests/api/test_empty_db.py`:

```python
from fastapi.testclient import TestClient

from nzstats.api.app import create_app


def test_every_endpoint_renders_an_empty_state(tmp_path) -> None:
    from nzstats.config import load_settings

    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path)})
    with TestClient(create_app(settings)) as c:
        overview = c.get("/api/overview").json()
        assert overview["kpis"] == [] and overview["featured"] is None
        assert overview["latest_releases"] == [] and overview["upcoming"] == []
        assert c.get("/api/releases").json() == []
        assert c.get("/api/calendar").json()["items"] == []
        assert c.get("/api/series").json() == []
        health = c.get("/api/health").json()
        assert health["database_ok"] and health["vintage_count"] == 0
        countries = c.get("/api/migration/countries").json()
        assert countries["available"] is False and "No country data" in countries["note"]
        assert c.get("/api/series/mig.m.net").status_code == 404
```

`backend/tests/api/test_static.py`:

```python
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings


def test_spa_is_served_with_client_side_routing_fallback(tmp_path) -> None:
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("console.log(1)")
    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path / "data"),
                              "NZSTATS_STATIC_DIR": str(static)})
    with TestClient(create_app(settings)) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/migration").text == "<html>app</html>"  # client-side route
        assert c.get("/releases/12").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "console.log(1)"
        missing = c.get("/api/nope")
        assert missing.status_code == 404 and missing.headers["content-type"].startswith(
            "application/json")
```

- [ ] **Step 5: Run to verify failure**

Run: `cd backend && pytest tests/insights/test_revisions.py tests/insights/test_countries.py tests/api -v`
Expected: `ModuleNotFoundError: No module named 'nzstats.api'` / `nzstats.insights.revisions`.

- [ ] **Step 6: Implement the API**

`backend/src/nzstats/api/__init__.py` (empty). `api/deps.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request

from nzstats.clock import utc_now
from nzstats.store.db import connect


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_now(request: Request) -> datetime:
    now = getattr(request.app.state, "now", None)
    return now() if now else utc_now()


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
Now = Annotated[datetime, Depends(get_now)]
```

`api/routes.py`:

```python
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from nzstats.api.deps import Conn, Now
from nzstats.catalog import category_for
from nzstats.clock import AKL, to_akl_iso, to_utc_iso
from nzstats.insights.countries import rank_countries
from nzstats.insights.migration import build_release_analysis
from nzstats.insights.overview import build_overview, health_rows
from nzstats.insights.revisions import revision_view, series_out, vintage_out
from nzstats.insights.summary import release_summary
from nzstats.models import (CalendarOut, CountriesOut, HealthOut, OverviewOut, PointOut,
                            ReleaseDetail, ReleaseSummary, RevisionsOut, RunOut, SeriesDataOut,
                            SeriesOut)
from nzstats.store import repo

router = APIRouter()
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CAVEATS = {
    "monthly": "Monthly estimates; provisional values are revised in later releases.",
    "rolling_annual": ("Rolling twelve-month total published by Stats NZ. Not comparable with "
                       "monthly figures."),
}


def _slugs(request: Request) -> set[str]:
    return request.app.state.analysable_slugs


@router.get("/health", response_model=HealthOut)
def health(conn: Conn, now: Now) -> HealthOut:
    runs = [RunOut(release_key=r["release_key"], started_at=to_akl_iso(r["started_at"]),
                   outcome=r["outcome"], error_class=r["error_class"], detail=r["detail"])
            for r in conn.execute("SELECT * FROM ingest_run ORDER BY id DESC LIMIT 15")]
    counts = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM release GROUP BY status")}
    return HealthOut(
        generated_at=to_akl_iso(now), database_ok=conn.execute("SELECT 1").fetchone()[0] == 1,
        sources=health_rows(conn), recent_runs=runs, release_counts=counts,
        series_count=conn.execute("SELECT COUNT(*) FROM series").fetchone()[0],
        vintage_count=conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0])


@router.get("/overview", response_model=OverviewOut)
def overview(request: Request, conn: Conn, now: Now) -> OverviewOut:
    return build_overview(conn, analysable_slugs=_slugs(request), now=now)


@router.get("/releases", response_model=list[ReleaseSummary])
def releases(
    request: Request, conn: Conn,
    status: str | None = None, category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReleaseSummary]:
    statuses = [s for s in (status or "").split(",") if s]
    sql, params = "SELECT * FROM release", []
    if statuses:
        sql += f" WHERE status IN ({','.join('?' * len(statuses))})"
        params = statuses
    rows = conn.execute(sql + " ORDER BY published_at DESC, id DESC", params).fetchall()
    items = [release_summary(conn, r, analysable_slugs=_slugs(request)) for r in rows]
    if category:
        items = [i for i in items if i.category == category]
    return items[offset: offset + limit]


def _unavailable_reason(conn, row, summary: ReleaseSummary, analysable: set[str]) -> str:
    if row["series_slug"] not in analysable:
        return "Detailed analysis is not yet available for this category (planned for Phase 2)."
    if row["status"] in ("scheduled", "delayed"):
        word = "Delayed; now scheduled" if row["status"] == "delayed" else "Scheduled"
        return f"{word} for {summary.published_at[:16].replace('T', ' ')} (Pacific/Auckland)."
    if row["status"] == "unavailable":
        return "Stats NZ files were not available during the polling window; retrying daily."
    run = conn.execute("SELECT * FROM ingest_run WHERE release_key = ? ORDER BY id DESC LIMIT 1",
                       (row["release_key"],)).fetchone()
    if run is None:
        return "Published, awaiting ingestion."
    extra = f": {run['error_class']}: {run['detail']}" if run["error_class"] else ""
    return f"Last ingestion attempt {run['outcome']}{extra}."


@router.get("/releases/{release_id}", response_model=ReleaseDetail)
def release_detail(release_id: int, request: Request, conn: Conn) -> ReleaseDetail:
    row = repo.get_release_by_id(conn, release_id)
    if row is None:
        raise HTTPException(404, "release not found")
    slugs = _slugs(request)
    summary = release_summary(conn, row, analysable_slugs=slugs)
    analysis = build_release_analysis(conn, release_id, analysable_slugs=slugs)
    reason = None if analysis else _unavailable_reason(conn, row, summary, slugs)
    return ReleaseDetail(release=summary, analysis=analysis, unavailable_reason=reason)


@router.get("/calendar", response_model=CalendarOut)
def calendar(
    request: Request, conn: Conn, now: Now,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> CalendarOut:
    today = now.astimezone(AKL).date()
    start = from_ or today - timedelta(days=45)
    end = to or today + timedelta(days=90)
    lo = to_utc_iso(datetime.combine(start, time.min, AKL))
    hi = to_utc_iso(datetime.combine(end + timedelta(days=1), time.min, AKL))
    rows = conn.execute("SELECT * FROM release WHERE published_at >= ? AND published_at < ?"
                        " ORDER BY published_at, id", (lo, hi)).fetchall()
    health = {h.source: h for h in health_rows(conn)}
    sources = [health[s] for s in ("calendar_ics", "calendar_month") if s in health]
    return CalendarOut(
        items=[release_summary(conn, r, analysable_slugs=_slugs(request)) for r in rows],
        last_checked_at=max((s.last_checked_at for s in sources if s.last_checked_at),
                            default=None),
        last_success_at=max((s.last_success_at for s in sources if s.last_success_at),
                            default=None))


@router.get("/series", response_model=list[SeriesOut])
def series_list(conn: Conn, category: str | None = None) -> list[SeriesOut]:
    return [series_out(r, r["n_vintages"], r["latest_period"])
            for r in repo.series_overview(conn, category)]


def _vintage_for(conn, series_key: str, vintage: str | None) -> repo.VintageInfo:
    vintages = repo.list_vintages(conn, series_key)
    if not vintages:
        raise HTTPException(404, "series has no data")
    if vintage in (None, "latest"):
        return vintages[-1]
    matches = [v for v in vintages if v.release_key == vintage]
    if not matches:
        raise HTTPException(404, "vintage not found for this series")
    return matches[-1]


def _series_data(conn, key: str, vintage: str | None, from_: str | None, to: str | None):
    for value in (from_, to):
        if value is not None and not PERIOD.match(value):
            raise HTTPException(422, "from/to must be YYYY-MM")
    row = repo.get_series_row(conn, key)
    if row is None:
        raise HTTPException(404, "series not found")
    v = _vintage_for(conn, key, vintage)
    obs = repo.vintage_observations(conn, v.vintage_id)
    periods = [p for p in sorted(obs) if (not from_ or p >= from_) and (not to or p <= to)]
    return row, v, [obs[p] for p in periods], max(obs) if obs else None


@router.get("/series/{key}", response_model=SeriesDataOut)
def series_data(key: str, conn: Conn, vintage: str | None = None,
                from_: Annotated[str | None, Query(alias="from")] = None,
                to: str | None = None) -> SeriesDataOut:
    row, v, obs, latest = _series_data(conn, key, vintage, from_, to)
    release = repo.get_release(conn, v.release_key)
    return SeriesDataOut(
        series=series_out(row, len(repo.list_vintages(conn, key)), latest), vintage=vintage_out(v),
        points=[PointOut(period=o.period, value=o.value, status=o.status.value,
                         std_error=o.std_error, released_in=o.released_in) for o in obs],
        source_url=release["page_url"] if release else None,
        caveat=CAVEATS.get(row["frequency"], ""))


@router.get("/series/{key}/csv")
def series_csv(key: str, conn: Conn, vintage: str | None = None,
               from_: Annotated[str | None, Query(alias="from")] = None,
               to: str | None = None) -> Response:
    row, v, obs, _ = _series_data(conn, key, vintage, from_, to)
    release = repo.get_release(conn, v.release_key)
    source = f"Stats NZ (CC BY 4.0) {release['page_url'] or ''}".strip()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["series_key", "series_name", "unit", "frequency", "period", "value",
                     "status", "std_error", "released_in", "release", "published_at", "source"])
    for o in obs:
        writer.writerow([key, row["name"], row["unit"], row["frequency"], o.period, o.value,
                         o.status.value, "" if o.std_error is None else o.std_error,
                         o.released_in or "", v.title, to_akl_iso(v.published_at), source])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})


@router.get("/revisions/{key}", response_model=RevisionsOut)
def revisions_view(key: str, conn: Conn, base: str | None = None,
                   compare: str | None = None) -> RevisionsOut:
    view = revision_view(conn, key, base_release_key=base, compare_release_key=compare)
    if view is None:
        raise HTTPException(404, "series or vintage not found")
    return view


@router.get("/migration/countries", response_model=CountriesOut)
def countries(conn: Conn, months: Annotated[int, Query(ge=1, le=36)] = 12,
              top: Annotated[int, Query(ge=1, le=50)] = 15) -> CountriesOut:
    return rank_countries(conn, months=months, top=top)
```

A 422 for `from=nonsense` comes from FastAPI's `date` validation.

`api/app.py`:

```python
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from nzstats import __version__
from nzstats.api.routes import router
from nzstats.config import Settings, load_settings
from nzstats.runtime import Runtime, build_adapters, build_runtime
from nzstats.store.db import connect, migrate

log = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA; unknown non-asset paths fall back to index.html for client routing."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def create_app(
    settings: Settings | None = None, *, start_scheduler: bool = False,
    runtime: Runtime | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    migrate(connect(settings.db_path))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if start_scheduler:
            from nzstats.scheduler.jobs import build_scheduler, schedule_startup_tasks

            rt = runtime or build_runtime(settings)
            scheduler = build_scheduler(rt)
            schedule_startup_tasks(scheduler, rt)
            scheduler.start()
            log.info("scheduler started with jobs %s", [j.id for j in scheduler.get_jobs()])
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="NZ Stats Intelligence Dashboard", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.analysable_slugs = set(build_adapters(settings))
    app.include_router(router, prefix="/api")

    static = settings.static_dir
    if static and Path(static).is_dir():
        app.mount("/", SPAStaticFiles(directory=str(static), html=True), name="spa")
    return app
```

The `/api/nope` case must return JSON 404: FastAPI handles unmatched `/api/*` before the `/` mount only if the router matched; for unmatched `/api/...` the mount at `/` would swallow it and return `index.html`. Prevent that by adding, before the mount, a catch-all in `routes.py`:

```python
@router.api_route("/{path:path}", methods=["GET"], include_in_schema=False)
def api_not_found(path: str) -> None:
    raise HTTPException(404, "not found")
```

placed **last** in `routes.py`.

- [ ] **Step 7: Run to verify pass; lint; full suite**

Run: `cd backend && pytest -v && ruff check --fix . && ruff format .`
Expected: PASS for the whole backend suite. Then `python -m nzstats.cli openapi > /dev/null && echo ok` — expected `ok`.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add revision view, country ranking, overview and read-only API

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```


### Task 13: Frontend foundation (scaffold, tokens, API client, formatting, shell, states)

**Files:**
- Create: `frontend/` (Vite React-TS app), `frontend/components.json` (by shadcn), `frontend/src/{main.tsx,App.tsx,index.css}`
- Create: `frontend/src/api/{client.ts,hooks.ts,types.ts}`, generated `frontend/src/api/schema.d.ts`
- Create: `frontend/src/lib/{format.ts,csv.ts,utils.ts}`, `frontend/src/components/{Layout.tsx,QueryBoundary.tsx,StatusBadge.tsx}`
- Create: `scripts/seed_e2e_db.py`, `scripts/dump_frontend_fixtures.py`; modify `backend/tests/support.py` (`seed_from_fixtures`)
- Test: `frontend/src/lib/format.test.ts`, `csv.test.ts`, `frontend/src/components/QueryBoundary.test.tsx`, `Layout.test.tsx`

**Interfaces:**
- Consumes: the API from Task 12 (`/api/*`).
- Produces:
  - `api/client.ts`: `class ApiError(status: number, message: string)`, `getJson<T>(path: string, signal?: AbortSignal): Promise<T>`
  - `api/hooks.ts`: `useOverview()`, `useReleases(params)`, `useRelease(id: number)`, `useCalendar(from?: string, to?: string)`, `useSeries(key: string, vintage?: string)`, `useRevisions(key: string, base?: string, compare?: string)`, `useCountries(months?: number, top?: number)`, `useHealth()` (all TanStack Query hooks)
  - `api/types.ts`: aliases of generated schema types: `Overview, Kpi, Metric, ReleaseSummary, ReleaseDetail, ReleaseAnalysis, Insight, SeriesData, PointOut, RevisionsOut, CountriesOut, CalendarOut, Health, SourceHealth`
  - `lib/format.ts`: `formatNumber(v: number, o?: {signed?: boolean; decimals?: number}): string`, `formatPercent(p: number | null | undefined, decimals?: number): string` (`"n/a"` when null), `formatNet(v: number): string`, `periodLabel(period: string, frequency: string): string`, `formatAklDateTime(iso: string): string`, `formatAklDate(iso: string): string`
  - `lib/csv.ts`: `toCsv(rows: Record<string, string | number | null>[]): string`
  - `components/QueryBoundary.tsx`: `QueryBoundary<T>({query, isEmpty?, empty?, children: (data: T) => ReactNode})`, `EmptyState({title, body})`, `ErrorState({error, onRetry})`
  - `components/StatusBadge.tsx`: `StatusBadge({status: string})` for observation (`provisional|final|unknown`) and release (`scheduled|published|delayed|corrected|unavailable`) statuses

- [ ] **Step 1: State the Design Read and load the design guidance**

Read the applicable sections of Kevin's installed taste skill (never the whole 87 KB file) and the `dataviz` skill:

```bash
sed -n '13,81p;519,551p;572,704p;910,986p' ~/.agents/skills/design-taste-frontend/SKILL.md
```

Then invoke `dataviz` (Skill tool) for chart colour, mark and tooltip rules. Write, in your next message, the one-line Design Read the skill requires: *"Reading this as: a professional economic-intelligence dashboard for analysts and executives (public-sector data, trust-first), with a restrained, dense, editorial-data language (DESIGN_VARIANCE 5, MOTION_INTENSITY 2, VISUAL_DENSITY 7), leaning toward shadcn/ui on Tailwind with a neutral palette, one accent, and ECharts for charts."* Apply §6 (accessibility/performance), §8 (dark mode via `prefers-color-scheme`), §9 (AI tells), and run §14's pre-flight at the end of Tasks 15 and 16. Where the skill's landing-page rules conflict with spec §9 (it declares dashboards out of scope), spec §9 wins.

- [ ] **Step 2: Scaffold the app and install dependencies**

From the worktree root:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm i react-router-dom @tanstack/react-query @tanstack/react-table echarts \
  class-variance-authority clsx tailwind-merge lucide-react @fontsource-variable/ibm-plex-sans
npm i -D tailwindcss @tailwindcss/vite @types/node vitest jsdom @testing-library/react \
  @testing-library/user-event @testing-library/jest-dom openapi-typescript @playwright/test
npx shadcn@latest init -d
npx shadcn@latest add button badge card toggle-group select skeleton table tooltip separator
```

`shadcn init` may ask for a base colour: choose **Neutral**. Expected: `components.json`, `src/lib/utils.ts` and `src/components/ui/*.tsx` exist; `npm run build` succeeds. Replace `vite.config.ts`:

```ts
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
```

`src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => cleanup());

// jsdom lacks these; components that observe size or media only need harmless stubs.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver ?? (RO as unknown as typeof ResizeObserver);
// Radix Select/Toggle need these pointer and scroll APIs, which jsdom does not implement.
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
window.matchMedia =
  window.matchMedia ??
  ((q: string) =>
    ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} }) as MediaQueryList);
```

Add to `package.json` scripts: `"test": "vitest run"`, `"typecheck": "tsc -b"`, `"gen:api": "cd ../backend && python -m nzstats.cli openapi > ../frontend/openapi.json && cd ../frontend && openapi-typescript openapi.json -o src/api/schema.d.ts"`. Make sure the `@/*` path alias is present in `tsconfig.json` and `tsconfig.app.json` (`"baseUrl": "."`, `"paths": {"@/*": ["./src/*"]}`; the shadcn init normally writes it) and add `"types": ["vitest/globals"]` to `tsconfig.app.json` `compilerOptions`.

- [ ] **Step 3: Design tokens**

Append to `src/index.css` after the shadcn variables (values are concrete starting points; the dataviz validator in Step 4 must pass or the colours are adjusted until it does):

```css
@import "@fontsource-variable/ibm-plex-sans";

:root {
  --font-sans: "IBM Plex Sans Variable", system-ui, -apple-system, "Segoe UI", sans-serif;
  /* chart tokens: restrained, colour-blind-aware, one hue per concept */
  --chart-1: #1f4e79; /* primary series: navy */
  --chart-2: #b4651a; /* comparison series: amber */
  --chart-3: #3f7f6e; /* third series: green-teal */
  --chart-4: #6b5b95; /* fourth series: muted violet */
  --chart-text: #292524;
  --chart-muted: #6b6560;
  --chart-grid: #e7e5e4;
  --chart-surface: #ffffff;
  --chart-positive: #2f6f5e;
  --chart-negative: #a23b3b;
  --chart-provisional-band: rgba(180, 101, 26, 0.10);
  --chart-provisional-bar: #8fb0cc;
}

@media (prefers-color-scheme: dark) {
  :root {
    --chart-1: #7fb2e0;
    --chart-2: #e0a15c;
    --chart-3: #7cc2ad;
    --chart-4: #b3a5d9;
    --chart-text: #e7e5e4;
    --chart-muted: #a8a29e;
    --chart-grid: #3a3836;
    --chart-surface: #1c1917;
    --chart-positive: #7cc2ad;
    --chart-negative: #e08a8a;
    --chart-provisional-band: rgba(224, 161, 92, 0.14);
    --chart-provisional-bar: #476b8a;
  }
}

body {
  font-family: var(--font-sans);
  font-variant-numeric: tabular-nums;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

- [ ] **Step 4: Validate the palette against the dataviz rules**

Using the `dataviz` skill's runnable validator (see its `references/palette.md`), check `--chart-1..4` against `--chart-surface` in light and dark for contrast and colour-blind separability. If any check fails, adjust the hex values in `index.css` (keep hue families), re-run until it passes, and record the validator output in `docs/progress.md` (created in Task 17; keep the text in your scratch notes until then).

- [ ] **Step 5: Write the failing tests for formatting, CSV and states**

`frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  formatAklDate, formatAklDateTime, formatNet, formatNumber, formatPercent, periodLabel,
} from "./format";

describe("formatNumber", () => {
  it("groups thousands and uses a typographic minus", () => {
    expect(formatNumber(20350)).toBe("20,350");
    expect(formatNumber(-38335)).toBe("−38,335");
    expect(formatNumber(0)).toBe("0");
  });
  it("supports signed output and decimals", () => {
    expect(formatNumber(12, { signed: true })).toBe("+12");
    expect(formatNumber(-12, { signed: true })).toBe("−12");
    expect(formatNumber(0, { signed: true })).toBe("0");
    expect(formatNumber(1.234, { decimals: 1 })).toBe("1.2");
  });
});

describe("formatPercent", () => {
  it("shows n/a when the change is not meaningful", () => {
    expect(formatPercent(null)).toBe("n/a");
    expect(formatPercent(undefined)).toBe("n/a");
  });
  it("is signed with one decimal", () => {
    expect(formatPercent(112.04)).toBe("+112.0%");
    expect(formatPercent(-3.26)).toBe("−3.3%");
  });
});

describe("formatNet", () => {
  it("words gains and losses", () => {
    expect(formatNet(20350)).toBe("net gain of 20,350");
    expect(formatNet(-38335)).toBe("net loss of 38,335");
    expect(formatNet(0)).toBe("no net change");
  });
});

describe("periodLabel", () => {
  it("labels monthly and year-ended periods differently", () => {
    expect(periodLabel("2026-07", "monthly")).toBe("Jul 2026");
    expect(periodLabel("2026-07", "rolling_annual")).toBe("Year ended Jul 2026");
  });
});

describe("Auckland date formatting", () => {
  it("renders the wall-clock time in Pacific/Auckland regardless of the viewer's timezone", () => {
    expect(formatAklDateTime("2026-10-14T10:45:00+13:00")).toMatch(/14 Oct 2026.*10:45/);
    expect(formatAklDateTime("2026-10-13T21:45:00Z")).toMatch(/14 Oct 2026.*10:45/);
    expect(formatAklDate("2026-09-14T10:45:00+12:00")).toBe("14 Sep 2026");
  });
});
```

`frontend/src/lib/csv.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { toCsv } from "./csv";

describe("toCsv", () => {
  it("writes a header and rows", () => {
    expect(toCsv([{ period: "2026-07", value: 5170 }, { period: "2026-06", value: null }])).toBe(
      "period,value\n2026-07,5170\n2026-06,\n",
    );
  });
  it("quotes commas, quotes and newlines", () => {
    expect(toCsv([{ a: 'x,"y"', b: "l1\nl2" }])).toBe('a,b\n"x,""y""","l1\nl2"\n');
  });
  it("returns an empty string for no rows", () => {
    expect(toCsv([])).toBe("");
  });
});
```

`frontend/src/components/QueryBoundary.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { QueryBoundary } from "./QueryBoundary";

const base = { data: undefined, error: null, isLoading: false, isError: false, refetch: vi.fn() };

describe("QueryBoundary", () => {
  it("shows a loading skeleton", () => {
    render(<QueryBoundary query={{ ...base, isLoading: true }}>{() => <p>data</p>}</QueryBoundary>);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  });

  it("shows the error and a working retry", async () => {
    const refetch = vi.fn();
    render(
      <QueryBoundary
        query={{ ...base, isError: true, error: new ApiError(500, "boom"), refetch }}
      >
        {() => <p>data</p>}
      </QueryBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/boom/);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("shows the empty explanation when there is nothing to show", () => {
    render(
      <QueryBoundary
        query={{ ...base, data: [] }}
        isEmpty={(d: unknown[]) => d.length === 0}
        empty={<p>Nothing ingested yet</p>}
      >
        {() => <p>data</p>}
      </QueryBoundary>,
    );
    expect(screen.getByText("Nothing ingested yet")).toBeInTheDocument();
  });

  it("renders children with the data", () => {
    render(
      <QueryBoundary query={{ ...base, data: { n: 3 } }}>{(d: { n: number }) => <p>n={d.n}</p>}</QueryBoundary>,
    );
    expect(screen.getByText("n=3")).toBeInTheDocument();
  });
});
```

`frontend/src/components/Layout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Layout } from "./Layout";

describe("Layout", () => {
  it("has landmarks, a skip link, navigation and the licence attribution", () => {
    render(
      <MemoryRouter initialEntries={["/migration"]}>
        <Layout>
          <p>content</p>
        </Layout>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /skip to content/i })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveTextContent("content");
    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(nav).toHaveTextContent(/overview/i);
    expect(screen.getByRole("link", { name: /migration/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("contentinfo")).toHaveTextContent(/CC BY 4\.0/);
  });
});
```

- [ ] **Step 6: Run to verify failure**

Run: `cd frontend && npm test`
Expected: FAIL — modules `./format`, `./csv`, `./QueryBoundary`, `./Layout` not found.

- [ ] **Step 7: Implement formatting, CSV and the API layer**

`frontend/src/lib/format.ts`:

```ts
const AKL = "Pacific/Auckland";
const MINUS = "\u2212";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatNumber(
  value: number,
  { signed = false, decimals = 0 }: { signed?: boolean; decimals?: number } = {},
): string {
  const abs = Math.abs(value).toLocaleString("en-NZ", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  if (value < 0 && Number(abs.replace(/,/g, "")) !== 0) return `${MINUS}${abs}`;
  return signed && value > 0 ? `+${abs}` : abs;
}

export function formatPercent(p: number | null | undefined, decimals = 1): string {
  if (p === null || p === undefined) return "n/a";
  return `${formatNumber(p, { signed: true, decimals })}%`;
}

export function formatNet(v: number): string {
  const n = Math.round(v);
  if (n === 0) return "no net change";
  return `net ${n > 0 ? "gain" : "loss"} of ${formatNumber(Math.abs(n))}`;
}

export function monthLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export function periodLabel(period: string, frequency: string): string {
  return frequency === "rolling_annual" ? `Year ended ${monthLabel(period)}` : monthLabel(period);
}

const clock = new Intl.DateTimeFormat("en-NZ", {
  timeZone: AKL, year: "numeric", month: "numeric", day: "numeric",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZoneName: "short",
});

function auckland(iso: string): Record<string, string> {
  return Object.fromEntries(clock.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
}

export function formatAklDate(iso: string): string {
  const p = auckland(iso);
  return `${Number(p.day)} ${MONTHS[Number(p.month) - 1]} ${p.year}`;
}

export function formatAklDateTime(iso: string): string {
  const p = auckland(iso);
  return `${formatAklDate(iso)}, ${p.hour}:${p.minute} ${p.timeZoneName}`;
}
```

`frontend/src/lib/csv.ts`:

```ts
export function toCsv(rows: Record<string, string | number | null>[]): string {
  if (rows.length === 0) return "";
  const columns = Object.keys(rows[0]);
  const cell = (v: string | number | null): string => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.join(",")];
  for (const row of rows) lines.push(columns.map((c) => cell(row[c])).join(","));
  return lines.join("\n") + "\n";
}
```

`frontend/src/api/client.ts`:

```ts
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body: keep the status text */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}
```

Generate the schema: `cd frontend && npm run gen:api` (requires the backend venv active). Expected: `src/api/schema.d.ts` exists and contains `ReleaseAnalysis`.

`frontend/src/api/types.ts`:

```ts
import type { components } from "./schema";

type S = components["schemas"];
export type Overview = S["OverviewOut"];
export type Kpi = S["Kpi"];
export type Metric = S["Metric"];
export type ChangeOut = S["ChangeOut"];
export type ReleaseSummary = S["ReleaseSummary"];
export type ReleaseDetail = S["ReleaseDetail"];
export type ReleaseAnalysis = S["ReleaseAnalysis"];
export type Insight = S["Insight"];
export type SeriesData = S["SeriesDataOut"];
export type PointOut = S["PointOut"];
export type RevisionsOut = S["RevisionsOut"];
export type CountriesOut = S["CountriesOut"];
export type CountryRank = S["CountryRank"];
export type CalendarOut = S["CalendarOut"];
export type Health = S["HealthOut"];
export type SourceHealth = S["SourceHealthOut"];
```

`frontend/src/api/hooks.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { getJson } from "./client";
import type {
  CalendarOut, CountriesOut, Health, Overview, ReleaseDetail, ReleaseSummary, RevisionsOut,
  SeriesData,
} from "./types";

const qs = (params: Record<string, string | number | undefined>): string => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: ({ signal }) => getJson<Overview>("/api/overview", signal), refetchInterval: 60_000 });

export const useReleases = (params: { status?: string; category?: string; limit?: number } = {}) =>
  useQuery({
    queryKey: ["releases", params],
    queryFn: ({ signal }) => getJson<ReleaseSummary[]>(`/api/releases${qs(params)}`, signal),
  });

export const useRelease = (id: number) =>
  useQuery({
    queryKey: ["release", id],
    queryFn: ({ signal }) => getJson<ReleaseDetail>(`/api/releases/${id}`, signal),
    enabled: Number.isFinite(id),
  });

export const useCalendar = (from?: string, to?: string) =>
  useQuery({
    queryKey: ["calendar", from, to],
    queryFn: ({ signal }) => getJson<CalendarOut>(`/api/calendar${qs({ from, to })}`, signal),
  });

export const useSeries = (key: string, vintage?: string) =>
  useQuery({
    queryKey: ["series", key, vintage],
    queryFn: ({ signal }) => getJson<SeriesData>(`/api/series/${key}${qs({ vintage })}`, signal),
  });

export const useRevisions = (key: string, base?: string, compare?: string) =>
  useQuery({
    queryKey: ["revisions", key, base, compare],
    queryFn: ({ signal }) => getJson<RevisionsOut>(`/api/revisions/${key}${qs({ base, compare })}`, signal),
  });

export const useCountries = (months = 12, top = 15) =>
  useQuery({
    queryKey: ["countries", months, top],
    queryFn: ({ signal }) => getJson<CountriesOut>(`/api/migration/countries${qs({ months, top })}`, signal),
  });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: ({ signal }) => getJson<Health>("/api/health", signal), refetchInterval: 30_000 });
```

- [ ] **Step 8: Implement states, status badge, layout, app entry**

`frontend/src/components/QueryBoundary.tsx`:

```tsx
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type QueryLike<T> = {
  data: T | undefined;
  error: Error | null;
  isLoading: boolean;
  isError: boolean;
  refetch: () => unknown;
};

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-dashed p-6 text-sm">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{body}</p>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-md border border-destructive/40 p-4 text-sm">
      <p className="font-medium">This could not be loaded.</p>
      <p className="mt-1 text-muted-foreground">{error?.message ?? "Unknown error"}</p>
      <Button className="mt-3" variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

export function QueryBoundary<T>({
  query, isEmpty, empty, children,
}: {
  query: QueryLike<T>;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) {
    return (
      <div role="status" aria-label="Loading" className="space-y-3">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.data === undefined) return null;
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState title="Nothing to show" body="No data is available yet." />}</>;
  return <>{children(query.data)}</>;
}
```

`frontend/src/components/StatusBadge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";

const LABEL: Record<string, string> = {
  provisional: "Provisional", final: "Final", unknown: "Status n/a",
  scheduled: "Scheduled", published: "Published", delayed: "Delayed",
  corrected: "Corrected", unavailable: "Unavailable",
};

export function StatusBadge({ status }: { status: string }) {
  const emphasised = ["provisional", "delayed", "corrected", "unavailable"].includes(status);
  return (
    <Badge variant={emphasised ? "outline" : "secondary"} className={emphasised ? "border-amber-600/60 text-amber-800 dark:text-amber-300" : ""}>
      {LABEL[status] ?? status}
    </Badge>
  );
}
```

`frontend/src/components/Layout.tsx`:

```tsx
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/migration", label: "Migration" },
  { to: "/calendar", label: "Release calendar" },
  { to: "/health", label: "Data health" },
];

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b print:hidden">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 lg:px-6">
          <span className="text-base font-semibold tracking-tight">NZ Stats Intelligence</span>
          <nav aria-label="Primary" className="-mx-1 flex gap-1 overflow-x-auto">
            {LINKS.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded px-2 py-1 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                    isActive ? "bg-muted font-medium" : "text-muted-foreground hover:text-foreground"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-6 lg:px-6">
        {children}
      </main>
      <footer className="border-t print:border-0">
        <p className="mx-auto max-w-[1400px] px-4 py-4 text-xs text-muted-foreground lg:px-6">
          Source: Stats NZ (stats.govt.nz), licensed under Creative Commons Attribution 4.0
          (CC BY 4.0). This dashboard is independent and not endorsed by Stats NZ.
        </p>
      </footer>
    </div>
  );
}
```

`frontend/src/App.tsx` and `main.tsx` (pages are added in Tasks 15–16; use lazy placeholders now so the app builds):

```tsx
// App.tsx
import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";

const Overview = lazy(() => import("@/pages/Overview"));
const Migration = lazy(() => import("@/pages/Migration"));
const ReleaseAnalysis = lazy(() => import("@/pages/ReleaseAnalysis"));
const Calendar = lazy(() => import("@/pages/Calendar"));
const Health = lazy(() => import("@/pages/Health"));

function NotFound() {
  return <p className="text-sm">That page does not exist. Use the navigation above.</p>;
}

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<p role="status">Loading…</p>}>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/migration" element={<Migration />} />
          <Route path="/releases/:id" element={<ReleaseAnalysis />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/health" element={<Health />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
```

```tsx
// main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const client = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
```

Create stub pages so the build passes until Tasks 15–16 replace them: `src/pages/{Overview,Migration,ReleaseAnalysis,Calendar,Health}.tsx`, each `export default function X() { return <h1 className="text-xl font-semibold">X</h1>; }`.

- [ ] **Step 9: Add the real-data seeding helpers (used by frontend fixtures and e2e)**

Append to `backend/tests/support.py`:

```python
def seed_from_fixtures(data_dir) -> None:
    """Build a database from the real fixture files (June + July 2026 releases plus the calendar).

    Used for frontend fixtures and end-to-end tests; never for production data.
    """
    from pathlib import Path

    from nzstats.config import load_settings
    from nzstats.pipeline.discover import discover
    from nzstats.runtime import build_runtime

    settings = load_settings({"NZSTATS_DATA_DIR": str(Path(data_dir)), "NZSTATS_BASE_URL": BASE})
    site = FakeSite()
    rt = build_runtime(settings, fetcher=site.fetcher())
    ingest_months(rt, "2026-06", "2026-07")
    discover(rt, months=["2026-09", "2026-10"], now_fn=lambda: NOW)
```

`scripts/seed_e2e_db.py`:

```python
"""Create a demo database from real fixture files. Usage: python scripts/seed_e2e_db.py DIR"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.support import seed_from_fixtures  # noqa: E402

if __name__ == "__main__":
    seed_from_fixtures(Path(sys.argv[1]))
    print(f"seeded {sys.argv[1]}")
```

`scripts/dump_frontend_fixtures.py`:

```python
"""Write API responses (from the seeded demo DB) as frontend test fixtures.

Usage: cd backend && python ../scripts/dump_frontend_fixtures.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

from nzstats.api.app import create_app  # noqa: E402
from nzstats.config import load_settings  # noqa: E402
from tests.support import BASE, NOW, seed_from_fixtures  # noqa: E402

OUT = ROOT / "frontend" / "src" / "test" / "fixtures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        seed_from_fixtures(tmp)
        settings = load_settings({"NZSTATS_DATA_DIR": tmp, "NZSTATS_BASE_URL": BASE})
        app = create_app(settings)
        app.state.now = lambda: NOW
        with TestClient(app) as c:
            releases = c.get("/api/releases").json()
            july = next(r for r in releases if r["title"].endswith("July 2026") and r["has_analysis"])
            scheduled = c.get("/api/releases", params={"status": "scheduled"}).json()
            payloads = {
                "overview": "/api/overview",
                "releases": "/api/releases",
                "release_detail": f"/api/releases/{july['id']}",
                "calendar": "/api/calendar",
                "series_net_m": "/api/series/mig.m.net",
                "series_net_ry": "/api/series/mig.ry.net",
                "series_arrivals_ry": "/api/series/mig.ry.arrivals",
                "series_departures_ry": "/api/series/mig.ry.departures",
                "countries": "/api/migration/countries",
                "revisions": "/api/revisions/mig.m.net",
                "health": "/api/health",
            }
            for name, url in payloads.items():
                (OUT / f"{name}.json").write_text(json.dumps(c.get(url).json(), indent=1))
            (OUT / "release_scheduled.json").write_text(
                json.dumps(c.get(f"/api/releases/{scheduled[0]['id']}").json(), indent=1))
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
```

Run: `cd backend && python ../scripts/dump_frontend_fixtures.py`. Expected: `frontend/src/test/fixtures/*.json` written (12 files). These are real API payloads built from real excerpts; regenerate (and review the diff) whenever the API schema changes.

- [ ] **Step 10: Run to verify pass; typecheck and build**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all vitest suites PASS; `tsc -b` clean; Vite build succeeds.

- [ ] **Step 11: Commit**

```bash
git add -A && git commit -m "feat: scaffold frontend with tokens, API layer, formatting and shell

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Chart infrastructure (option builders, ECharts wrapper, ChartCard)

**Files:**
- Create: `frontend/src/charts/{theme.ts,options.ts,EChart.tsx,ChartCard.tsx}`
- Test: `frontend/src/charts/options.test.ts`, `ChartCard.test.tsx`

**Interfaces:**
- Consumes: `lib/format.ts`, `lib/csv.ts`, `api/types.ts`.
- Produces:
  - `theme.ts`: `ChartTheme`, `readTheme(): ChartTheme`, `useChartTheme(): ChartTheme`, `TEST_THEME`
  - `options.ts`: `ChartPoint = {period: string; value: number; status: string}`; `LineSeriesInput = {name: string; points: ChartPoint[]; color: string; dashed?: boolean}`; `lineOption(input: {series: LineSeriesInput[]; unit: string; frequency: "monthly" | "rolling_annual"}, theme: ChartTheme): EChartsCoreOption`; `divergingBarOption(input: {name: string; points: ChartPoint[]; unit: string; frequency: "monthly" | "rolling_annual"}, theme): EChartsCoreOption`; `stackedPanelsOption(input: {monthly: ChartPoint[]; yearEnded: ChartPoint[]; unit: string}, theme): EChartsCoreOption`; `rankedBarOption(input: {items: {name: string; value: number; provisional: boolean}[]; unit: string}, theme): EChartsCoreOption`; `revisionBarOption(input: {rows: {period: string; absolute: number}[]; unit: string}, theme): EChartsCoreOption`; `sliceYears(points: ChartPoint[], years: number | null): ChartPoint[]`
  - `EChart.tsx`: `EChart({option, ariaLabel, height?, onReady?})`
  - `ChartCard.tsx`: `ChartCard({title, question, unit, source: {label: string; url?: string | null; updated?: string | null}, caveat?, option, ariaLabel, csvFilename, csvRows, height?, controls?})`

Chart rules enforced by these builders (spec §6): provisional values are visually distinct (shaded band on lines, lighter bars) and flagged in tooltips; the latest observation is highlighted with a labelled marker; non-negative series use a zero baseline; series that cross zero get a zero reference line; monthly and year-ended figures are never plotted on one axis (they use separate panels); every tooltip states the period (year-ended periods are labelled as such), value, unit and status.

- [ ] **Step 1: Write the failing tests**

`frontend/src/charts/options.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  divergingBarOption, lineOption, rankedBarOption, revisionBarOption, sliceYears,
  stackedPanelsOption, type ChartPoint,
} from "./options";
import { TEST_THEME } from "./theme";

const pts = (rows: [string, number, string?][]): ChartPoint[] =>
  rows.map(([period, value, status]) => ({ period, value, status: status ?? "final" }));

const input = (series: ChartPoint[], extra = {}) => ({
  series: [{ name: "Net", points: series, color: "#123456" }],
  unit: "people",
  frequency: "monthly" as const,
  ...extra,
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Opt = any;

describe("lineOption", () => {
  it("uses a zero baseline for non-negative series and none otherwise", () => {
    const nonNeg = lineOption(input(pts([["2026-01", 5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(nonNeg.yAxis.min).toBe(0);
    const mixed = lineOption(input(pts([["2026-01", -5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(mixed.yAxis.min).toBeUndefined();
  });

  it("draws a zero reference line only when values cross zero", () => {
    const mixed = lineOption(input(pts([["2026-01", -5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(mixed.series[0].markLine.data[0].yAxis).toBe(0);
    const nonNeg = lineOption(input(pts([["2026-01", 5], ["2026-02", 9]])), TEST_THEME) as Opt;
    expect(nonNeg.series[0].markLine).toBeUndefined();
  });

  it("shades from the first provisional period and only when one exists", () => {
    const withProv = lineOption(
      input(pts([["2026-01", 1], ["2026-02", 2, "provisional"], ["2026-03", 3, "provisional"]])),
      TEST_THEME,
    ) as Opt;
    const area = withProv.series[0].markArea.data[0];
    expect(area[0].xAxis).toBe("2026-02");
    expect(area[1].xAxis).toBe("2026-03");
    const none = lineOption(input(pts([["2026-01", 1], ["2026-02", 2]])), TEST_THEME) as Opt;
    expect(none.series[0].markArea).toBeUndefined();
  });

  it("highlights the latest observation with a labelled marker", () => {
    const o = lineOption(input(pts([["2026-01", 1], ["2026-02", 2]])), TEST_THEME) as Opt;
    expect(o.series[0].markPoint.data[0].coord).toEqual(["2026-02", 2]);
  });

  it("aligns series with different start periods using nulls", () => {
    const o = lineOption(
      {
        series: [
          { name: "A", points: pts([["2026-01", 1], ["2026-02", 2], ["2026-03", 3]]), color: "#111" },
          { name: "B", points: pts([["2026-02", 5], ["2026-03", 6]]), color: "#222" },
        ],
        unit: "people",
        frequency: "monthly",
      },
      TEST_THEME,
    ) as Opt;
    expect(o.xAxis.data).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(o.series[1].data).toEqual([null, 5, 6]);
    expect(o.legend).toBeDefined();
  });

  it("tooltips name the period, value, unit and provisional status", () => {
    const o = lineOption(
      input(pts([["2026-06", 100], ["2026-07", 5170, "provisional"]])),
      TEST_THEME,
    ) as Opt;
    const html: string = o.tooltip.formatter([{ axisValue: "2026-07", seriesName: "Net", value: 5170, marker: "●" }]);
    expect(html).toContain("Jul 2026");
    expect(html).toContain("5,170");
    expect(html).toContain("people");
    expect(html).toContain("(provisional)");
  });

  it("labels year-ended periods as such in tooltips", () => {
    const o = lineOption(input(pts([["2026-07", 20350]]), { frequency: "rolling_annual" }), TEST_THEME) as Opt;
    const html: string = o.tooltip.formatter([{ axisValue: "2026-07", seriesName: "Net", value: 20350, marker: "●" }]);
    expect(html).toContain("Year ended Jul 2026");
  });
});

describe("divergingBarOption", () => {
  it("colours bars by sign and lighter when provisional", () => {
    const o = divergingBarOption(
      { name: "Net", points: pts([["2026-05", -3], ["2026-06", 4], ["2026-07", 6, "provisional"]]), unit: "people", frequency: "monthly" },
      TEST_THEME,
    ) as Opt;
    const items = o.series[0].data;
    expect(items[0].itemStyle.color).toBe(TEST_THEME.negative);
    expect(items[1].itemStyle.color).toBe(TEST_THEME.positive);
    expect(items[2].itemStyle.opacity).toBeLessThan(1);
  });
});

describe("stackedPanelsOption", () => {
  it("keeps monthly and year-ended on separate axes and grids", () => {
    const o = stackedPanelsOption(
      { monthly: pts([["2026-06", 100], ["2026-07", 200]]), yearEnded: pts([["2026-07", 20350]]), unit: "people" },
      TEST_THEME,
    ) as Opt;
    expect(o.grid).toHaveLength(2);
    expect(o.yAxis).toHaveLength(2);
    expect(o.series.map((s: Opt) => s.yAxisIndex)).toEqual([0, 1]);
    expect(o.title.map((t: Opt) => t.text)).toEqual(["Monthly estimate", "Year ended (rolling 12 months)"]);
    expect(o.axisPointer.link[0].xAxisIndex).toBe("all");
  });
});

describe("rankedBarOption", () => {
  it("sorts descending top-to-bottom and dims provisional totals", () => {
    const o = rankedBarOption(
      { items: [{ name: "B", value: 2, provisional: false }, { name: "A", value: 9, provisional: true }], unit: "people" },
      TEST_THEME,
    ) as Opt;
    expect(o.yAxis.data).toEqual(["A", "B"]); // descending order; inverse axis puts the largest at the top
    expect(o.yAxis.inverse).toBe(true);
    expect(o.series[0].data[0].value).toBe(9);
  });
});

describe("revisionBarOption", () => {
  it("centres revisions on zero", () => {
    const o = revisionBarOption({ rows: [{ period: "2026-05", absolute: -10 }, { period: "2026-06", absolute: 25 }], unit: "people" }, TEST_THEME) as Opt;
    expect(o.series[0].markLine.data[0].yAxis).toBe(0);
    expect(o.series[0].data[0].itemStyle.color).toBe(TEST_THEME.negative);
  });
});

describe("sliceYears", () => {
  it("keeps the last N years relative to the latest period", () => {
    const all = pts([["2015-07", 1], ["2016-08", 2], ["2026-07", 3]]);
    expect(sliceYears(all, 10).map((p) => p.period)).toEqual(["2016-08", "2026-07"]);
    expect(sliceYears(all, null)).toHaveLength(3);
  });
});
```

`frontend/src/charts/ChartCard.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const chart = vi.hoisted(() => ({ getDataURL: vi.fn(() => "data:image/png;base64,AAA") }));

const readBlob = (blob: Blob) =>
  new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });

vi.mock("./EChart", () => ({
  EChart: ({ ariaLabel, onReady }: { ariaLabel: string; onReady?: (c: unknown) => void }) => {
    onReady?.(chart);
    return <div role="img" aria-label={ariaLabel} />;
  },
}));
vi.mock("./theme", async (orig) => ({ ...(await orig<typeof import("./theme")>()), useChartTheme: () => (({ surface: "#fff" }) as never) }));

import { ChartCard } from "./ChartCard";

const props = {
  title: "Year-ended net migration was a net gain of 20,350 in July 2026",
  question: "How has annual net migration moved since 2001?",
  unit: "people",
  source: { label: "Stats NZ, International migration: July 2026", url: "https://www.stats.govt.nz/x/", updated: "2026-09-14T10:45:00+12:00" },
  caveat: "Latest 16 months are provisional.",
  option: {},
  ariaLabel: "Line chart of year-ended net migration",
  csvFilename: "net.csv",
  csvRows: [{ period: "2026-06", value: 1 }, { period: "2026-07", value: 2 }],
};

describe("ChartCard", () => {
  beforeEach(() => {
    chart.getDataURL.mockClear();
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
  });

  it("shows title, question, unit, caveat and a linked source with the update date", () => {
    render(<ChartCard {...props} />);
    expect(screen.getByRole("heading", { name: props.title })).toBeInTheDocument();
    expect(screen.getByText(props.question)).toBeInTheDocument();
    expect(screen.getByText(/Latest 16 months are provisional/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /International migration: July 2026/ });
    expect(link).toHaveAttribute("href", "https://www.stats.govt.nz/x/");
    expect(screen.getByText(/14 Sep 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Unit: people/)).toBeInTheDocument();
  });

  it("downloads the chart data as CSV", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByRole("button", { name: /download data/i }));
    const blob = (URL.createObjectURL as ReturnType<typeof vi.fn>).mock.calls[0][0] as Blob;
    expect(await readBlob(blob)).toBe("period,value\n2026-06,1\n2026-07,2\n");
    expect(click).toHaveBeenCalled();
  });

  it("exports the chart image through the chart instance", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByRole("button", { name: /export image/i }));
    expect(chart.getDataURL).toHaveBeenCalledWith(expect.objectContaining({ type: "png" }));
    expect(click).toHaveBeenCalled();
  });

  it("offers the data as an accessible table", async () => {
    render(<ChartCard {...props} />);
    await userEvent.click(screen.getByText(/view data table/i));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("2026-07")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- src/charts`
Expected: FAIL — `./options`, `./theme`, `./ChartCard` not found.

- [ ] **Step 3: Implement theme and option builders**

`frontend/src/charts/theme.ts`:

```ts
import { useEffect, useState } from "react";

export type ChartTheme = {
  text: string; muted: string; grid: string; surface: string;
  series: string[]; positive: string; negative: string;
  provisionalBand: string; provisionalBar: string;
};

export const TEST_THEME: ChartTheme = {
  text: "#111", muted: "#666", grid: "#ddd", surface: "#fff",
  series: ["#1f4e79", "#b4651a", "#3f7f6e", "#6b5b95"],
  positive: "#2f6f5e", negative: "#a23b3b",
  provisionalBand: "rgba(180,101,26,0.10)", provisionalBar: "#8fb0cc",
};

export function readTheme(): ChartTheme {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => s.getPropertyValue(name).trim() || fallback;
  return {
    text: v("--chart-text", TEST_THEME.text),
    muted: v("--chart-muted", TEST_THEME.muted),
    grid: v("--chart-grid", TEST_THEME.grid),
    surface: v("--chart-surface", TEST_THEME.surface),
    series: [1, 2, 3, 4].map((i) => v(`--chart-${i}`, TEST_THEME.series[i - 1])),
    positive: v("--chart-positive", TEST_THEME.positive),
    negative: v("--chart-negative", TEST_THEME.negative),
    provisionalBand: v("--chart-provisional-band", TEST_THEME.provisionalBand),
    provisionalBar: v("--chart-provisional-bar", TEST_THEME.provisionalBar),
  };
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(() => readTheme());
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTheme(readTheme());
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return theme;
}
```

`frontend/src/charts/options.ts`:

```ts
import type { EChartsCoreOption } from "echarts/core";
import { formatNumber, monthLabel, periodLabel } from "@/lib/format";
import type { ChartTheme } from "./theme";

export type Frequency = "monthly" | "rolling_annual";
export type ChartPoint = { period: string; value: number; status: string };
export type LineSeriesInput = { name: string; points: ChartPoint[]; color: string; dashed?: boolean };

const axisNumber = (v: number) => (Math.abs(v) >= 1000 ? `${formatNumber(v / 1000, { decimals: v % 1000 === 0 ? 0 : 1 })}k` : formatNumber(v));
const yearTick = (v: string) => (v.endsWith("-01") ? v.slice(0, 4) : "");

export function sliceYears(points: ChartPoint[], years: number | null): ChartPoint[] {
  if (years === null || points.length === 0) return points;
  const last = points[points.length - 1].period;
  const [y, m] = last.split("-").map(Number);
  const cutoff = `${String(y - years).padStart(4, "0")}-${String(m).padStart(2, "0")}`;
  return points.filter((p) => p.period > cutoff);
}

function tooltip(series: LineSeriesInput[], unit: string, frequency: Frequency) {
  return {
    trigger: "axis" as const,
    formatter: (params: { axisValue: string; seriesName: string; value: number | null; marker: string }[] | { axisValue: string; seriesName: string; value: number | null; marker: string }) => {
      const list = Array.isArray(params) ? params : [params];
      const period = String(list[0].axisValue);
      const rows = list
        .filter((p) => p.value !== null && p.value !== undefined)
        .map((p) => {
          const pt = series.find((s) => s.name === p.seriesName)?.points.find((x) => x.period === period);
          const flag = pt?.status === "provisional" ? " (provisional)" : "";
          return `${p.marker} ${p.seriesName}: <b>${formatNumber(Number(p.value))}</b> ${unit}${flag}`;
        });
      return `<div>${periodLabel(period, frequency)}</div>${rows.join("<br/>")}`;
    },
  };
}

export function lineOption(
  input: { series: LineSeriesInput[]; unit: string; frequency: Frequency },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = [...new Set(input.series.flatMap((s) => s.points.map((p) => p.period)))].sort();
  const values = input.series.flatMap((s) => s.points.map((p) => p.value));
  const nonNegative = values.every((v) => v >= 0);
  const firstProvisional = periods.find((p) => input.series.some((s) => s.points.some((x) => x.period === p && x.status === "provisional")));
  const last = periods[periods.length - 1];

  const series = input.series.map((s, i) => {
    const byPeriod = new Map(s.points.map((p) => [p.period, p.value]));
    const latest = s.points[s.points.length - 1];
    const entry: Record<string, unknown> = {
      name: s.name, type: "line", showSymbol: false, connectNulls: false,
      lineStyle: { width: 2, color: s.color, type: s.dashed ? "dashed" : "solid" },
      itemStyle: { color: s.color },
      data: periods.map((p) => byPeriod.get(p) ?? null),
    };
    if (latest) {
      entry.markPoint = {
        symbol: "circle", symbolSize: 9, itemStyle: { color: s.color },
        label: { show: true, position: "right", color: theme.text, formatter: () => formatNumber(latest.value) },
        data: [{ coord: [latest.period, latest.value] }],
      };
    }
    if (i === 0) {
      if (!nonNegative) {
        entry.markLine = {
          silent: true, symbol: "none", label: { show: false },
          lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }],
        };
      }
      if (firstProvisional) {
        entry.markArea = {
          silent: true, itemStyle: { color: theme.provisionalBand },
          label: { show: true, color: theme.muted, position: "insideTop", formatter: "Provisional" },
          data: [[{ xAxis: firstProvisional }, { xAxis: last }]],
        };
      }
    }
    return entry;
  });

  return {
    aria: { enabled: true },
    animation: false,
    textStyle: { color: theme.text },
    grid: { left: 56, right: 72, top: input.series.length > 1 ? 36 : 24, bottom: 28 },
    legend: input.series.length > 1 ? { top: 0, textStyle: { color: theme.text } } : undefined,
    tooltip: tooltip(input.series, input.unit, input.frequency),
    xAxis: {
      type: "category", data: periods, boundaryGap: false,
      axisLabel: { interval: 0, color: theme.muted, formatter: yearTick },
      axisTick: { interval: (_: number, v: string) => v.endsWith("-01") },
      axisLine: { lineStyle: { color: theme.grid } },
    },
    yAxis: {
      type: "value", min: nonNegative ? 0 : undefined,
      axisLabel: { color: theme.muted, formatter: axisNumber },
      splitLine: { lineStyle: { color: theme.grid } },
    },
    series,
  };
}

export function divergingBarOption(
  input: { name: string; points: ChartPoint[]; unit: string; frequency: Frequency },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = input.points.map((p) => p.period);
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 24, bottom: 28 },
    tooltip: tooltip([{ name: input.name, points: input.points, color: theme.series[0] }], input.unit, input.frequency),
    xAxis: { type: "category", data: periods, axisLabel: { interval: 0, color: theme.muted, formatter: yearTick }, axisTick: { interval: (_: number, v: string) => v.endsWith("-01") }, axisLine: { lineStyle: { color: theme.muted } } },
    yAxis: { type: "value", axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    series: [{
      name: input.name, type: "bar",
      data: input.points.map((p) => ({
        value: p.value,
        itemStyle: { color: p.value < 0 ? theme.negative : theme.positive, opacity: p.status === "provisional" ? 0.55 : 1 },
      })),
    }],
  };
}

export function stackedPanelsOption(
  input: { monthly: ChartPoint[]; yearEnded: ChartPoint[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  const periods = [...new Set([...input.monthly, ...input.yearEnded].map((p) => p.period))].sort();
  const yearEnded = new Map(input.yearEnded.map((p) => [p.period, p.value]));
  const monthly = new Map(input.monthly.map((p) => [p.period, p]));
  const axisBase = { type: "category" as const, data: periods, axisLabel: { interval: 0, color: theme.muted, formatter: yearTick }, axisTick: { interval: (_: number, v: string) => v.endsWith("-01") } };
  const valueAxis = (gridIndex: number) => ({ type: "value" as const, gridIndex, axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } });
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    title: [
      { text: "Monthly estimate", left: 56, top: 0, textStyle: { fontSize: 12, color: theme.text } },
      { text: "Year ended (rolling 12 months)", left: 56, top: "52%", textStyle: { fontSize: 12, color: theme.text } },
    ],
    grid: [
      { left: 56, right: 72, top: 24, height: "36%" },
      { left: 56, right: 72, top: "58%", height: "32%" },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string; seriesName: string; value: number | null; marker: string }[]) => {
        const period = String(params[0].axisValue);
        const rows = params.filter((p) => p.value !== null).map((p) => {
          const monthlyPoint = monthly.get(period);
          const flag = p.seriesName.startsWith("Monthly") && monthlyPoint?.status === "provisional" ? " (provisional)" : "";
          return `${p.marker} ${p.seriesName}: <b>${formatNumber(Number(p.value))}</b> ${input.unit}${flag}`;
        });
        return `<div>${monthLabel(period)}</div>${rows.join("<br/>")}`;
      },
    },
    xAxis: [
      { ...axisBase, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: theme.muted } } },
      { ...axisBase, gridIndex: 1, boundaryGap: false },
    ],
    yAxis: [valueAxis(0), valueAxis(1)],
    series: [
      {
        name: "Monthly net migration", type: "bar", xAxisIndex: 0, yAxisIndex: 0,
        data: periods.map((p) => {
          const pt = monthly.get(p);
          return pt === undefined ? null : { value: pt.value, itemStyle: { color: pt.value < 0 ? theme.negative : theme.positive, opacity: pt.status === "provisional" ? 0.55 : 1 } };
        }),
      },
      {
        name: "Year-ended net migration", type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
        lineStyle: { width: 2, color: theme.series[0] }, itemStyle: { color: theme.series[0] },
        data: periods.map((p) => yearEnded.get(p) ?? null),
        markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }] },
      },
    ],
  };
}

export function rankedBarOption(
  input: { items: { name: string; value: number; provisional: boolean }[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  const items = [...input.items].sort((a, b) => b.value - a.value);
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 150, right: 56, top: 8, bottom: 24 },
    tooltip: {
      trigger: "item",
      formatter: (p: { name: string; value: number; data: { provisional: boolean } }) =>
        `${p.name}: <b>${formatNumber(p.value)}</b> ${input.unit}${p.data.provisional ? " (includes provisional months)" : ""}`,
    },
    xAxis: { type: "value", min: 0, axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    yAxis: { type: "category", inverse: true, data: items.map((i) => i.name), axisLabel: { color: theme.text }, axisLine: { lineStyle: { color: theme.muted } } },
    series: [{
      type: "bar", barMaxWidth: 18,
      label: { show: true, position: "right", color: theme.text, formatter: (p: { value: number }) => formatNumber(p.value) },
      data: items.map((i) => ({ value: i.value, provisional: i.provisional, itemStyle: { color: i.provisional ? theme.provisionalBar : theme.series[0] } })),
    }],
  };
}

export function revisionBarOption(
  input: { rows: { period: string; absolute: number }[]; unit: string },
  theme: ChartTheme,
): EChartsCoreOption {
  return {
    aria: { enabled: true }, animation: false, textStyle: { color: theme.text },
    grid: { left: 56, right: 24, top: 24, bottom: 40 },
    tooltip: {
      trigger: "axis",
      formatter: (params: { axisValue: string; value: number }[]) =>
        `${monthLabel(String(params[0].axisValue))}: <b>${formatNumber(params[0].value, { signed: true })}</b> ${input.unit} revision`,
    },
    xAxis: { type: "category", data: input.rows.map((r) => r.period), axisLabel: { color: theme.muted, rotate: 45, formatter: (v: string) => monthLabel(v) } },
    yAxis: { type: "value", axisLabel: { color: theme.muted, formatter: axisNumber }, splitLine: { lineStyle: { color: theme.grid } } },
    series: [{
      type: "bar",
      markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: theme.muted, width: 1 }, data: [{ yAxis: 0 }] },
      data: input.rows.map((r) => ({ value: r.absolute, itemStyle: { color: r.absolute < 0 ? theme.negative : theme.positive } })),
    }],
  };
}
```

- [ ] **Step 4: Implement the ECharts wrapper and ChartCard**

`frontend/src/charts/EChart.tsx`:

```tsx
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  AriaComponent, AxisPointerComponent, GridComponent, LegendComponent, MarkAreaComponent,
  MarkLineComponent, MarkPointComponent, TitleComponent, TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, MarkPointComponent,
  MarkAreaComponent, MarkLineComponent, TitleComponent, AriaComponent, AxisPointerComponent,
  CanvasRenderer,
]);

export type ChartInstance = echarts.ECharts;

export function EChart({
  option, ariaLabel, height = 320, onReady,
}: {
  option: EChartsCoreOption;
  ariaLabel: string;
  height?: number;
  onReady?: (chart: ChartInstance) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);
  const ready = useRef(onReady);
  ready.current = onReady;

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const instance = echarts.init(el, undefined, { renderer: "canvas" });
    chart.current = instance;
    ready.current?.(instance);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, { notMerge: true });
  }, [option]);

  return <div ref={host} role="img" aria-label={ariaLabel} style={{ height }} className="w-full" />;
}
```

`frontend/src/charts/ChartCard.tsx`:

```tsx
import { useRef, type ReactNode } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { Download, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toCsv } from "@/lib/csv";
import { formatAklDate } from "@/lib/format";
import { EChart, type ChartInstance } from "./EChart";
import { useChartTheme } from "./theme";

type Props = {
  title: string;
  question: string;
  unit: string;
  source: { label: string; url?: string | null; updated?: string | null };
  caveat?: string;
  option: EChartsCoreOption;
  ariaLabel: string;
  csvFilename: string;
  csvRows: Record<string, string | number | null>[];
  height?: number;
  controls?: ReactNode;
};

function save(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
}

export function ChartCard({
  title, question, unit, source, caveat, option, ariaLabel, csvFilename, csvRows, height, controls,
}: Props) {
  const chart = useRef<ChartInstance | null>(null);
  const theme = useChartTheme();
  const columns = csvRows.length ? Object.keys(csvRows[0]) : [];
  const tail = csvRows.slice(-24);

  const downloadCsv = () => {
    const url = URL.createObjectURL(new Blob([toCsv(csvRows)], { type: "text/csv;charset=utf-8" }));
    save(url, csvFilename);
    URL.revokeObjectURL(url);
  };
  const exportImage = () => {
    const url = chart.current?.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: theme.surface });
    if (url) save(url, csvFilename.replace(/\.csv$/, ".png"));
  };

  return (
    <figure className="break-inside-avoid rounded-md border bg-card p-4 print:border-0 print:p-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold leading-snug">{title}</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">{question}</p>
        </div>
        <div className="flex items-center gap-2 print:hidden">
          {controls}
          <Button variant="outline" size="sm" onClick={downloadCsv}>
            <Download className="size-4" aria-hidden /> Download data (CSV)
          </Button>
          <Button variant="outline" size="sm" onClick={exportImage}>
            <ImageIcon className="size-4" aria-hidden /> Export image (PNG)
          </Button>
        </div>
      </div>
      <div className="mt-3">
        <EChart option={option} ariaLabel={ariaLabel} height={height} onReady={(c) => (chart.current = c)} />
      </div>
      <figcaption className="mt-2 space-y-1 text-xs text-muted-foreground">
        <p>
          Unit: {unit}. Source:{" "}
          {source.url ? (
            <a className="underline underline-offset-2" href={source.url} target="_blank" rel="noreferrer">
              {source.label}
            </a>
          ) : (
            source.label
          )}
          {source.updated ? `, published ${formatAklDate(source.updated)}` : ""}.
        </p>
        {caveat && <p>{caveat}</p>}
        {csvRows.length > 0 && (
          <details className="print:hidden">
            <summary className="cursor-pointer">View data table</summary>
            <table className="mt-2 w-full text-left">
              <caption className="sr-only">{title}: latest {tail.length} rows</caption>
              <thead>
                <tr>{columns.map((c) => <th key={c} scope="col" className="pr-4 font-medium">{c}</th>)}</tr>
              </thead>
              <tbody>
                {tail.map((row, i) => (
                  <tr key={i}>{columns.map((c) => <td key={c} className="pr-4">{row[c] ?? ""}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 5: Run to verify pass; typecheck**

Run: `cd frontend && npm test && npm run typecheck`
Expected: PASS (options + ChartCard suites green; previous suites still green).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add chart option builders, ECharts wrapper and ChartCard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Migration page and Overview

**Files:**
- Create: `frontend/src/components/{KpiCard.tsx,InsightList.tsx,ReleaseRow.tsx,Freshness.tsx}`
- Create: `frontend/src/pages/migration/charts.tsx`; replace `frontend/src/pages/{Migration.tsx,Overview.tsx}`
- Test: `frontend/src/components/KpiCard.test.tsx`, `frontend/src/pages/Migration.test.tsx`, `frontend/src/pages/Overview.test.tsx`; shared helper `frontend/src/test/mockApi.ts`

**Interfaces:**
- Consumes: Task 13/14 modules; fixtures in `src/test/fixtures/*.json`.
- Produces:
  - `KpiCard({kpi: Kpi})`, `InsightList({insights: Insight[]})`, `ReleaseRow({release: ReleaseSummary})`, `Freshness({sources: SourceHealth[]})`
  - `pages/migration/charts.tsx`: `NetTrendChart({range})`, `ArrivalsDeparturesChart({range})`, `MonthlyVsAnnualChart({range})`, `CitizenshipChart({range})`, `CountryChart()`, `RevisionChart()`; `type Range = 5 | 10 | null`
  - `test/mockApi.ts`: `mockApi(routes: Record<string, unknown | (() => unknown)>): void` (stubs `fetch`), `renderWithProviders(ui, {route?})`

The Migration page answers, in order: key findings (from the latest release analysis), net migration trend (monthly bars / year-ended line toggle), arrivals versus departures, monthly versus year-ended in separate panels, by citizenship, by country, revisions. Every chart: informative computed title, analytical question, unit, source link + publication date, caveat, CSV/PNG export. Never one axis for monthly and year-ended figures.

- [ ] **Step 1: Write the test helper and failing tests**

`frontend/src/test/mockApi.ts`:

```tsx
import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export function mockApi(routes: Record<string, unknown | (() => unknown)>): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    const key = Object.keys(routes).find((k) => (k.includes("?") ? url.pathname + url.search === k : url.pathname === k));
    if (!key) return new Response(JSON.stringify({ detail: `no mock for ${url.pathname}` }), { status: 404 });
    const body = typeof routes[key] === "function" ? (routes[key] as () => unknown)() : routes[key];
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function renderWithProviders(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}
```

Also mock the chart wrapper in page tests (canvas is unavailable in jsdom) — each page test begins with:

```tsx
vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel, option }: { ariaLabel: string; option: unknown }) => (
    <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option, (_, v) => (typeof v === "function" ? "fn" : v))} />
  ),
}));
```

`frontend/src/components/KpiCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Kpi } from "@/api/types";
import { KpiCard } from "./KpiCard";

const kpi = (over: Partial<Kpi["metric"]> = {}): Kpi => ({
  release_id: 7,
  published_at: "2026-09-14T10:45:00+12:00",
  source_url: "https://www.stats.govt.nz/information-releases/international-migration-july-2026/",
  metric: {
    series_key: "mig.ry.net", label: "Net migration, year ended", value: 20350, unit: "people",
    frequency: "rolling_annual", period: "2026-07", period_label: "Year ended Jul 2026",
    status: "provisional", std_error: null,
    change_prior: { label: "vs year ended Jun 2026", comparison_period: "2026-06", previous: 17479, absolute: 2871, percent: 16.4 },
    change_year_ago: { label: "vs year ended Jul 2025", comparison_period: "2025-07", previous: 9600, absolute: 10750, percent: 112 },
    ...over,
  },
});

describe("KpiCard", () => {
  it("shows value, unit, reference period, comparisons, status, publication date and source", () => {
    render(<KpiCard kpi={kpi()} />);
    expect(screen.getByText("Net migration, year ended")).toBeInTheDocument();
    expect(screen.getByText("20,350")).toBeInTheDocument();
    expect(screen.getAllByText(/people/).length).toBeGreaterThan(0);
    expect(screen.getByText("Year ended Jul 2026")).toBeInTheDocument();
    expect(screen.getByText(/\+10,750/)).toBeInTheDocument();
    expect(screen.getByText(/\+112\.0%/)).toBeInTheDocument();
    expect(screen.getByText("Provisional")).toBeInTheDocument();
    expect(screen.getByText(/14 Sep 2026/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /source/i })).toHaveAttribute("href", expect.stringContaining("stats.govt.nz"));
  });

  it("shows n/a instead of a misleading percentage for a negative base", () => {
    const k = kpi({
      value: -38335,
      change_year_ago: { label: "vs year ended Jul 2025", comparison_period: "2025-07", previous: -40000, absolute: 1665, percent: null },
    });
    render(<KpiCard kpi={k} />);
    expect(screen.getByText("−38,335")).toBeInTheDocument();
    expect(screen.getByText(/n\/a/)).toBeInTheDocument();
  });
});
```

`frontend/src/pages/Overview.test.tsx`:

```tsx
import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import overview from "@/test/fixtures/overview.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import series from "@/test/fixtures/series_net_ry.json";
import Overview from "./Overview";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} />,
}));

describe("Overview", () => {
  beforeEach(() => {
    mockApi({ "/api/overview": overview, "/api/series/mig.ry.net": series });
  });

  it("answers the key question in the first screen: KPIs, featured release, panels, freshness", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("heading", { name: /economic overview/i })).toBeInTheDocument();
    const kpis = screen.getByRole("region", { name: /key indicators/i });
    expect(within(kpis).getAllByRole("article").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByRole("region", { name: /featured release/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /latest releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /upcoming releases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /data freshness/i })).toBeInTheDocument();
  });

  it("names the inactive categories rather than faking indicators", async () => {
    renderWithProviders(<Overview />);
    expect(await screen.findByText(/not yet active/i)).toHaveTextContent(/Prices and inflation/);
  });

  it("explains an empty database", async () => {
    mockApi({
      "/api/overview": { generated_at: "2026-10-11T16:00:00+13:00", kpis: [], latest_releases: [], upcoming: [], freshness: [], featured: null, inactive_categories: [] },
    });
    renderWithProviders(<Overview />);
    expect(await screen.findByText(/no data has been ingested yet/i)).toBeInTheDocument();
  });

  it("shows an error with a retry when the API fails", async () => {
    mockApi({});
    renderWithProviders(<Overview />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
```

`frontend/src/pages/Migration.test.tsx`:

```tsx
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import countries from "@/test/fixtures/countries.json";
import detail from "@/test/fixtures/release_detail.json";
import netM from "@/test/fixtures/series_net_m.json";
import netRy from "@/test/fixtures/series_net_ry.json";
import arrRy from "@/test/fixtures/series_arrivals_ry.json";
import depRy from "@/test/fixtures/series_departures_ry.json";
import overview from "@/test/fixtures/overview.json";
import releases from "@/test/fixtures/releases.json";
import revisions from "@/test/fixtures/revisions.json";
import Migration from "./Migration";

vi.mock("@/charts/EChart", () => ({
  EChart: ({ ariaLabel, option }: { ariaLabel: string; option: unknown }) => (
    <div role="img" aria-label={ariaLabel} data-option={JSON.stringify(option, (_, v) => (typeof v === "function" ? "fn" : v))} />
  ),
}));

const cit = (key: string) => ({ ...netRy, series: { ...netRy.series, key } });

describe("Migration page", () => {
  beforeEach(() => {
    mockApi({
      "/api/overview": overview,
      "/api/releases": releases,
      [`/api/releases/${detail.release.id}`]: detail,
      "/api/series/mig.m.net": netM,
      "/api/series/mig.ry.net": netRy,
      "/api/series/mig.ry.arrivals": arrRy,
      "/api/series/mig.ry.departures": depRy,
      "/api/series/mig.m.arrivals": netM,
      "/api/series/mig.m.departures": netM,
      "/api/series/mig.ry.net.nz": cit("mig.ry.net.nz"),
      "/api/series/mig.ry.net.nonnz": cit("mig.ry.net.nonnz"),
      "/api/series/mig.ry.arrivals.nz": cit("mig.ry.arrivals.nz"),
      "/api/series/mig.ry.arrivals.nonnz": cit("mig.ry.arrivals.nonnz"),
      "/api/series/mig.ry.departures.nz": cit("mig.ry.departures.nz"),
      "/api/series/mig.ry.departures.nonnz": cit("mig.ry.departures.nonnz"),
      "/api/migration/countries": countries,
      "/api/revisions/mig.m.net": revisions,
    });
  });

  it("renders findings first, then the seven analytical views, each with a source and export", async () => {
    renderWithProviders(<Migration />);
    expect(await screen.findByRole("heading", { name: /international migration/i, level: 1 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /key statistical findings/i })).toBeInTheDocument();
    const charts = await screen.findAllByRole("figure");
    expect(charts.length).toBeGreaterThanOrEqual(6);
    for (const name of [/net migration/i, /arrivals and departures/i, /monthly estimate .* year ended/i, /citizenship/i, /country/i, /revisions/i]) {
      expect(screen.getAllByRole("heading", { level: 3, name }).length).toBeGreaterThan(0);
    }
    expect((await screen.findAllByRole("button", { name: /download data/i })).length).toBeGreaterThanOrEqual(6);
  });

  it("keeps monthly and year-ended frequencies separate when toggled", async () => {
    renderWithProviders(<Migration />);
    const group = await screen.findByRole("group", { name: /net migration frequency/i });
    await userEvent.click(within(group).getByRole("radio", { name: /monthly/i }));
    const chart = await screen.findByRole("img", { name: "Monthly net migration chart" });
    expect(chart.getAttribute("data-option")).toContain('"type":"bar"');
    await userEvent.click(within(group).getByRole("radio", { name: /year ended/i }));
    expect(await screen.findByRole("img", { name: "Year-ended net migration chart" })).toBeInTheDocument();
  });

  it("states the revision coverage limitation", async () => {
    renderWithProviders(<Migration />);
    expect(await screen.findByText(revisions.coverage.note.slice(0, 40), { exact: false })).toBeInTheDocument();
  });

  it("derived country ranking says it is derived and excludes regions from the ranking", async () => {
    renderWithProviders(<Migration />);
    expect((await screen.findAllByText(/derived/i)).length).toBeGreaterThan(0);
  });
});
```

(`within` must be imported from `@testing-library/react` in that test file.)

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- src/components src/pages`
Expected: FAIL — `KpiCard`, pages not implemented.

- [ ] **Step 3: Implement the shared components**

`frontend/src/components/KpiCard.tsx`:

```tsx
import type { ChangeOut, Kpi } from "@/api/types";
import { formatAklDate, formatNumber, formatPercent } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

function Delta({ change, unit }: { change: ChangeOut | null | undefined; unit: string }) {
  if (!change) return null;
  return (
    <p className="text-xs text-muted-foreground">
      <span className="font-medium text-foreground">{formatNumber(change.absolute, { signed: true })}</span>{" "}
      {unit} ({formatPercent(change.percent)}) {change.label}
    </p>
  );
}

export function KpiCard({ kpi }: { kpi: Kpi }) {
  const m = kpi.metric;
  return (
    <article className="rounded-md border bg-card p-3" aria-label={m.label}>
      <p className="text-xs font-medium text-muted-foreground">{m.label}</p>
      <p className="mt-1 flex items-baseline gap-2">
        <span className="text-3xl font-semibold leading-none tracking-tight">{formatNumber(m.value)}</span>
        <span className="text-xs text-muted-foreground">{m.unit}</span>
      </p>
      <p className="mt-1 flex items-center gap-2 text-xs">
        <span>{m.period_label}</span>
        <StatusBadge status={m.status} />
      </p>
      <div className="mt-2 space-y-0.5">
        <Delta change={m.change_year_ago} unit={m.unit} />
        <Delta change={m.change_prior} unit={m.unit} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Published {formatAklDate(kpi.published_at)} ·{" "}
        {kpi.source_url ? (
          <a className="underline underline-offset-2" href={kpi.source_url} target="_blank" rel="noreferrer">
            Source
          </a>
        ) : (
          "Source n/a"
        )}
      </p>
    </article>
  );
}
```

`frontend/src/components/InsightList.tsx`:

```tsx
import type { Insight } from "@/api/types";
import { Badge } from "@/components/ui/badge";

export function InsightList({ insights }: { insights: Insight[] }) {
  return (
    <ol className="space-y-3">
      {insights.map((i) => (
        <li key={i.id} className="text-sm leading-relaxed">
          <p>
            {i.kind === "inference" && (
              <Badge variant="outline" className="mr-2 align-middle">Inference</Badge>
            )}
            {i.text}
          </p>
          {i.caveat && <p className="mt-0.5 text-xs text-muted-foreground">{i.caveat}</p>}
          <details className="mt-0.5 text-xs text-muted-foreground">
            <summary className="cursor-pointer">Evidence ({i.evidence.length})</summary>
            <ul className="mt-1 list-disc pl-5">
              {i.evidence.map((e, n) => (
                <li key={n}>{e.series_key} · {e.period} · {e.value.toLocaleString("en-NZ")} · {e.release_key}</li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ol>
  );
}
```

`frontend/src/components/ReleaseRow.tsx`:

```tsx
import { Link } from "react-router-dom";
import type { ReleaseSummary } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";
import { StatusBadge } from "./StatusBadge";

export function ReleaseRow({ release }: { release: ReleaseSummary }) {
  const title = release.has_analysis ? (
    <Link className="font-medium underline-offset-2 hover:underline" to={`/releases/${release.id}`}>{release.title}</Link>
  ) : release.page_url ? (
    <a className="font-medium underline-offset-2 hover:underline" href={release.page_url} target="_blank" rel="noreferrer">{release.title}</a>
  ) : (
    <span className="font-medium">{release.title}</span>
  );
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        {title}
        <StatusBadge status={release.status} />
      </div>
      <p className="text-xs text-muted-foreground">
        {formatAklDateTime(release.published_at)} · {release.category}
      </p>
      {release.headline && <p className="mt-0.5 text-sm">{release.headline}</p>}
    </li>
  );
}
```

`frontend/src/components/Freshness.tsx`:

```tsx
import type { SourceHealth } from "@/api/types";
import { formatAklDateTime } from "@/lib/format";

const NAMES: Record<string, string> = {
  calendar_ics: "Release calendar (ICS)",
  calendar_month: "Release listings (monthly)",
  "release:international-migration": "International migration releases",
};

export function Freshness({ sources }: { sources: SourceHealth[] }) {
  if (sources.length === 0) return <p className="text-sm text-muted-foreground">No source has been checked yet.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {sources.map((s) => (
        <li key={s.source}>
          <span className="flex items-center gap-2">
            <span aria-hidden className={`size-2 rounded-full ${s.state === "ok" ? "bg-emerald-600" : "bg-amber-600"}`} />
            <span className="font-medium">{NAMES[s.source] ?? s.source}</span>
            <span className="text-xs text-muted-foreground">{s.state === "ok" ? "OK" : "Degraded"}</span>
          </span>
          <span className="block pl-4 text-xs text-muted-foreground">
            Checked {s.last_checked_at ? formatAklDateTime(s.last_checked_at) : "never"}
            {s.last_success_at ? ` · last success ${formatAklDateTime(s.last_success_at)}` : ""}
            {s.state !== "ok" && s.detail ? ` · ${s.detail}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Implement the Migration charts**

`frontend/src/pages/migration/charts.tsx` — one small component per view. Common helpers at the top:

```tsx
import { useMemo, useState } from "react";
import type { PointOut, SeriesData } from "@/api/types";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ChartCard } from "@/charts/ChartCard";
import {
  divergingBarOption, lineOption, rankedBarOption, revisionBarOption, sliceYears,
  stackedPanelsOption, type ChartPoint,
} from "@/charts/options";
import { useChartTheme } from "@/charts/theme";
import { useCountries, useRevisions, useSeries } from "@/api/hooks";
import { formatNet, formatNumber, monthLabel, periodLabel } from "@/lib/format";

export type Range = 5 | 10 | null;

const toPoints = (d: SeriesData): ChartPoint[] =>
  d.points.map((p: PointOut) => ({ period: p.period, value: p.value, status: p.status }));
const csv = (d: SeriesData, points: ChartPoint[]) =>
  points.map((p) => ({ series: d.series.key, period: p.period, value: p.value, status: p.status, unit: d.series.unit }));
const source = (d: SeriesData) => ({ label: `Stats NZ, ${d.vintage.title}`, url: d.source_url, updated: d.vintage.published_at });
const latest = (pts: ChartPoint[]) => pts[pts.length - 1];

function Frequency({ value, onChange, label }: { value: "monthly" | "rolling_annual"; onChange: (v: "monthly" | "rolling_annual") => void; label: string }) {
  return (
    <ToggleGroup type="single" variant="outline" size="sm" value={value} aria-label={label}
      onValueChange={(v) => v && onChange(v as "monthly" | "rolling_annual")}>
      <ToggleGroupItem value="monthly" aria-label="Monthly">Monthly</ToggleGroupItem>
      <ToggleGroupItem value="rolling_annual" aria-label="Year ended">Year ended</ToggleGroupItem>
    </ToggleGroup>
  );
}
```

Components (each wrapped in `QueryBoundary`; loading is shared per chart):

```tsx
export function NetTrendChart({ range }: { range: Range }) {
  const [freq, setFreq] = useState<"monthly" | "rolling_annual">("rolling_annual");
  const q = useSeries(freq === "monthly" ? "mig.m.net" : "mig.ry.net");
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q}>
      {(d) => {
        const pts = sliceYears(toPoints(d), range);
        const last = latest(pts);
        const what = freq === "monthly" ? "Monthly net migration" : "Year-ended net migration";
        const title = last
          ? `${what}: ${formatNet(last.value)} (${periodLabel(last.period, freq).toLowerCase()})`
          : what;
        const option =
          freq === "monthly"
            ? divergingBarOption({ name: what, points: pts, unit: d.series.unit, frequency: "monthly" }, theme)
            : lineOption({ series: [{ name: what, points: pts, color: theme.series[0] }], unit: d.series.unit, frequency: "rolling_annual" }, theme);
        return (
          <ChartCard
            title={title}
            question="Is net migration a gain or a loss, and how has it moved over time?"
            unit={d.series.unit} source={source(d)} caveat={d.caveat}
            option={option} ariaLabel={`${what} chart`}
            csvFilename={`${d.series.key}.csv`} csvRows={csv(d, pts)}
            controls={<Frequency value={freq} onChange={setFreq} label="Net migration frequency" />}
          />
        );
      }}
    </QueryBoundary>
  );
}

export function ArrivalsDeparturesChart({ range }: { range: Range }) {
  const [freq, setFreq] = useState<"monthly" | "rolling_annual">("rolling_annual");
  const prefix = freq === "monthly" ? "mig.m" : "mig.ry";
  const arr = useSeries(`${prefix}.arrivals`);
  const dep = useSeries(`${prefix}.departures`);
  const theme = useChartTheme();
  if (!arr.data || !dep.data) return <QueryBoundary query={arr.isError ? arr : dep}>{() => null}</QueryBoundary>;
  const a = sliceYears(toPoints(arr.data), range);
  const d = sliceYears(toPoints(dep.data), range);
  const la = latest(a);
  const ld = latest(d);
  return (
    <ChartCard
      title={`Arrivals and departures, ${periodLabel(la.period, freq).toLowerCase()}: ${formatNumber(la.value)} in, ${formatNumber(ld.value)} out`}
      question="Is the net result driven by more people arriving or fewer leaving?"
      unit="people" source={source(arr.data)} caveat={arr.data.caveat}
      option={lineOption({ series: [
        { name: "Migrant arrivals", points: a, color: theme.series[0] },
        { name: "Migrant departures", points: d, color: theme.series[1] },
      ], unit: "people", frequency: freq }, theme)}
      ariaLabel="Arrivals and departures chart"
      csvFilename={`arrivals-departures-${freq}.csv`}
      csvRows={a.map((p) => ({ period: p.period, arrivals: p.value, departures: d.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
      controls={<Frequency value={freq} onChange={setFreq} label="Arrivals and departures frequency" />}
    />
  );
}

export function MonthlyVsAnnualChart({ range }: { range: Range }) {
  const m = useSeries("mig.m.net");
  const y = useSeries("mig.ry.net");
  const theme = useChartTheme();
  if (!m.data || !y.data) return <QueryBoundary query={m.isError ? m : y}>{() => null}</QueryBoundary>;
  const monthly = sliceYears(toPoints(m.data), range);
  const yearEnded = sliceYears(toPoints(y.data), range);
  return (
    <ChartCard
      title="Monthly estimate versus year ended total of net migration, on separate scales"
      question="How do single-month swings relate to the rolling twelve-month total?"
      unit="people" source={source(m.data)}
      caveat="Monthly estimates and year-ended totals are different series: each panel has its own axis and they must not be compared directly."
      option={stackedPanelsOption({ monthly, yearEnded, unit: "people" }, theme)}
      ariaLabel="Monthly estimate and year-ended net migration chart" height={460}
      csvFilename="net-migration-monthly-and-year-ended.csv"
      csvRows={monthly.map((p) => ({ period: p.period, monthly_net: p.value, year_ended_net: yearEnded.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
    />
  );
}
```

```tsx
const MEASURES = [
  { id: "net", label: "Net migration" },
  { id: "arrivals", label: "Arrivals" },
  { id: "departures", label: "Departures" },
] as const;

export function CitizenshipChart({ range }: { range: Range }) {
  const [measure, setMeasure] = useState<(typeof MEASURES)[number]["id"]>("net");
  const nz = useSeries(`mig.ry.${measure}.nz`);
  const nonnz = useSeries(`mig.ry.${measure}.nonnz`);
  const theme = useChartTheme();
  if (!nz.data || !nonnz.data) return <QueryBoundary query={nz.isError ? nz : nonnz}>{() => null}</QueryBoundary>;
  const a = sliceYears(toPoints(nonnz.data), range);
  const b = sliceYears(toPoints(nz.data), range);
  const label = MEASURES.find((m) => m.id === measure)!.label.toLowerCase();
  return (
    <ChartCard
      title={`Year-ended ${label} by citizenship: non-NZ citizens ${formatNumber(latest(a).value)}, NZ citizens ${formatNumber(latest(b).value)}`}
      question="Which citizens account for the year-ended result?"
      unit="people" source={source(nz.data)} caveat={nz.data.caveat}
      option={lineOption({ series: [
        { name: "Non-NZ citizens", points: a, color: theme.series[0] },
        { name: "NZ citizens", points: b, color: theme.series[1] },
      ], unit: "people", frequency: "rolling_annual" }, theme)}
      ariaLabel={`Year-ended ${label} by citizenship chart`}
      csvFilename={`citizenship-${measure}-year-ended.csv`}
      csvRows={a.map((p) => ({ period: p.period, non_nz_citizens: p.value, nz_citizens: b.find((x) => x.period === p.period)?.value ?? null, status: p.status }))}
      controls={
        <ToggleGroup type="single" variant="outline" size="sm" value={measure} aria-label="Citizenship measure" onValueChange={(v) => v && setMeasure(v as typeof measure)}>
          {MEASURES.map((m) => <ToggleGroupItem key={m.id} value={m.id}>{m.label}</ToggleGroupItem>)}
        </ToggleGroup>
      }
    />
  );
}
```

```tsx
export function CountryChart() {
  const q = useCountries(12, 15);
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q} isEmpty={(d) => !d.available} empty={<p className="text-sm text-muted-foreground">No country data has been ingested yet.</p>}>
      {(d) => (
        <>
          <ChartCard
            title={`Migrant arrivals by country of last permanent residence, ${monthLabel(d.period_start!)} to ${monthLabel(d.period_end!)}`}
            question="Which countries do arriving migrants come from?"
            unit="people (sum of 12 monthly estimates)"
            source={{ label: "Stats NZ, International migration (derived)", url: null, updated: null }}
            caveat={`${d.note} Lighter bars include provisional months. Regions are shown separately below.`}
            option={rankedBarOption({ items: d.countries.map((c) => ({ name: c.name, value: c.value, provisional: c.provisional })), unit: "people" }, theme)}
            ariaLabel="Arrivals by country of last permanent residence chart" height={420}
            csvFilename="arrivals-by-country.csv"
            csvRows={d.countries.map((c) => ({ country: c.name, arrivals_12m: c.value, share_percent: c.share_percent, prior_12m: c.prior_value, includes_provisional: c.provisional ? "yes" : "no" }))}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Derived total. Regions: {d.regions.map((r) => `${r.name} ${formatNumber(r.value)}`).join(" · ")}
            {d.unallocated ? ` · ${d.unallocated.name} ${formatNumber(d.unallocated.value)}` : ""}.
          </p>
        </>
      )}
    </QueryBoundary>
  );
}
```

```tsx
export function RevisionChart() {
  const q = useRevisions("mig.m.net");
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q}>
      {(d) => (
        <div className="space-y-2">
          {d.rows.length > 0 && d.base && d.compare ? (
            <ChartCard
              title={`Revisions to monthly net migration between the ${d.base.title} and ${d.compare.title} releases`}
              question="How much were earlier estimates revised?"
              unit="people (revised minus original)"
              source={{ label: `Stats NZ, ${d.compare.title}`, url: null, updated: d.compare.published_at }}
              caveat={d.coverage.note}
              option={revisionBarOption({ rows: d.rows.map((r) => ({ period: r.period, absolute: r.absolute })), unit: "people" }, theme)}
              ariaLabel="Revisions to monthly net migration chart"
              csvFilename="net-migration-revisions.csv"
              csvRows={d.rows.map((r) => ({ period: r.period, original: r.original, revised: r.revised, absolute: r.absolute, percent: r.percent, original_status: r.original_status, revised_status: r.revised_status }))}
            />
          ) : (
            <div className="rounded-md border p-4 text-sm">
              <h3 className="font-semibold">Revisions to monthly net migration</h3>
              <p className="mt-1 text-muted-foreground">{d.coverage.note}</p>
            </div>
          )}
        </div>
      )}
    </QueryBoundary>
  );
}
```

- [ ] **Step 5: Implement the Migration and Overview pages**

`frontend/src/pages/Migration.tsx`:

```tsx
import { useState } from "react";
import { useRelease, useReleases } from "@/api/hooks";
import { InsightList } from "@/components/InsightList";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ArrivalsDeparturesChart, CitizenshipChart, CountryChart, MonthlyVsAnnualChart, NetTrendChart,
  RevisionChart, type Range,
} from "./migration/charts";

function KeyFindings() {
  const list = useReleases({ category: "Migration", limit: 20 });
  const latest = list.data?.find((r) => r.has_analysis);
  const detail = useRelease(latest?.id ?? NaN);
  return (
    <section aria-labelledby="findings" className="rounded-md border p-4">
      <h2 id="findings" className="text-lg font-semibold">Key statistical findings</h2>
      <QueryBoundary query={detail.data ? detail : list} isEmpty={() => !latest} empty={<p className="text-sm text-muted-foreground">No migration release has been analysed yet.</p>}>
        {() =>
          detail.data?.analysis ? (
            <>
              <p className="mb-2 text-xs text-muted-foreground">From {detail.data.release.title}. Observations are computed from published values; inferences are labelled.</p>
              <InsightList insights={[...detail.data.analysis.executive_summary, ...detail.data.analysis.context]} />
            </>
          ) : null
        }
      </QueryBoundary>
    </section>
  );
}

export default function Migration() {
  const [range, setRange] = useState<Range>(10);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">International migration</h1>
          <p className="text-sm text-muted-foreground">
            Outcomes-based estimates of long-term migrant arrivals and departures. Monthly and year-ended figures are separate series.
          </p>
        </div>
        <ToggleGroup type="single" variant="outline" size="sm" value={String(range ?? "all")} aria-label="Date range"
          onValueChange={(v) => v && setRange(v === "all" ? null : (Number(v) as 5 | 10))}>
          <ToggleGroupItem value="5">5 years</ToggleGroupItem>
          <ToggleGroupItem value="10">10 years</ToggleGroupItem>
          <ToggleGroupItem value="all">Since 2001</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <KeyFindings />
      <div className="grid gap-5 xl:grid-cols-2">
        <NetTrendChart range={range} />
        <ArrivalsDeparturesChart range={range} />
      </div>
      <MonthlyVsAnnualChart range={range} />
      <div className="grid gap-5 xl:grid-cols-2">
        <CitizenshipChart range={range} />
        <CountryChart />
      </div>
      <RevisionChart />
    </div>
  );
}
```

`frontend/src/pages/Overview.tsx`:

```tsx
import { Link } from "react-router-dom";
import { useOverview, useSeries } from "@/api/hooks";
import { ChartCard } from "@/charts/ChartCard";
import { lineOption, sliceYears } from "@/charts/options";
import { useChartTheme } from "@/charts/theme";
import { Freshness } from "@/components/Freshness";
import { KpiCard } from "@/components/KpiCard";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { formatAklDateTime, formatNet } from "@/lib/format";

function TrendOverview() {
  const q = useSeries("mig.ry.net");
  const theme = useChartTheme();
  return (
    <QueryBoundary query={q}>
      {(d) => {
        const pts = sliceYears(d.points.map((p) => ({ period: p.period, value: p.value, status: p.status })), 10);
        const last = pts[pts.length - 1];
        return (
          <ChartCard
            title={last ? `Year-ended net migration: ${formatNet(last.value)}` : "Year-ended net migration"}
            question="Where is annual net migration relative to the last ten years?"
            unit={d.series.unit} source={{ label: `Stats NZ, ${d.vintage.title}`, url: d.source_url, updated: d.vintage.published_at }}
            caveat={d.caveat} height={260}
            option={lineOption({ series: [{ name: "Year-ended net migration", points: pts, color: theme.series[0] }], unit: d.series.unit, frequency: "rolling_annual" }, theme)}
            ariaLabel="Year-ended net migration, last ten years"
            csvFilename="net-migration-year-ended.csv"
            csvRows={pts.map((p) => ({ period: p.period, value: p.value, status: p.status }))}
          />
        );
      }}
    </QueryBoundary>
  );
}

export default function Overview() {
  const q = useOverview();
  return (
    <QueryBoundary
      query={q}
      isEmpty={(d) => d.kpis.length === 0 && d.latest_releases.length === 0 && d.upcoming.length === 0}
      empty={<EmptyState title="No data has been ingested yet" body="Run `nzstats discover` then `nzstats backfill`, or wait for the next scheduled check. The Data health page shows what has been attempted." />}
    >
      {(d) => (
        <div className="space-y-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Economic overview</h1>
            <p className="text-sm text-muted-foreground">Latest official Stats NZ statistics. Updated {formatAklDateTime(d.generated_at)}.</p>
          </div>
          {d.kpis.length > 0 && (
            <section aria-label="Key indicators" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {d.kpis.slice(0, 8).map((k) => <KpiCard key={k.metric.series_key} kpi={k} />)}
            </section>
          )}
          <div className="grid gap-5 xl:grid-cols-12">
            <div className="space-y-5 xl:col-span-8">
              {d.featured && (
                <section aria-label="Featured release" className="rounded-md border p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Featured release</p>
                  <h2 className="mt-1 text-lg font-semibold">{d.featured.release.title}</h2>
                  {d.featured.first_insight && <p className="mt-1 text-sm">{d.featured.first_insight}</p>}
                  <Link className="mt-2 inline-block text-sm underline underline-offset-2" to={`/releases/${d.featured.release.id}`}>
                    Read the full release analysis
                  </Link>
                </section>
              )}
              <TrendOverview />
            </div>
            <div className="space-y-5 xl:col-span-4">
              <section aria-label="Latest releases" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Latest releases</h2>
                <ul className="mt-1 divide-y">{d.latest_releases.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
              </section>
              <section aria-label="Upcoming releases" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Upcoming releases</h2>
                <ul className="mt-1 divide-y">{d.upcoming.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
                <Link className="mt-2 inline-block text-sm underline underline-offset-2" to="/calendar">Full release calendar</Link>
              </section>
              <section aria-label="Data freshness" className="rounded-md border p-4">
                <h2 className="text-base font-semibold">Data freshness</h2>
                <div className="mt-2"><Freshness sources={d.freshness} /></div>
              </section>
            </div>
          </div>
          {d.inactive_categories.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Not yet active (no verified source wired in): {d.inactive_categories.map((c) => c.name).join(", ")}.
            </p>
          )}
        </div>
      )}
    </QueryBoundary>
  );
}
```

The Overview test checks `/not yet active/i` — the sentence above begins "Not yet active" ✓.

- [ ] **Step 6: Run to verify pass; typecheck; build**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: PASS. If a page test fails because a heading/label differs from the test's regex, change the **component text** to satisfy the documented chart-title rules (informative title, analytical question), not the other way round, unless the test expectation contradicts the spec.

- [ ] **Step 7: Visual and chart-quality review (evidence required)**

Seed a demo DB from real fixtures, serve the built app and look at it:

```bash
cd backend && . .venv/bin/activate && python ../scripts/seed_e2e_db.py /tmp/nzstats-demo
cd ../frontend && npm run build
cd ../backend && NZSTATS_DATA_DIR=/tmp/nzstats-demo NZSTATS_STATIC_DIR=../frontend/dist nzstats serve --port 8765 --no-scheduler
```

(The `--no-scheduler` flag is added in Task 17 Step 1; until then run `python -c "from nzstats.api.app import create_app; ..."` with `uvicorn` directly: `NZSTATS_DATA_DIR=/tmp/nzstats-demo NZSTATS_STATIC_DIR=../frontend/dist uvicorn --factory nzstats.api.app:create_app --port 8765`.) Then use the `ecc:e2e-testing` / Playwright tooling (or `webapp` browser skills) to open `http://127.0.0.1:8765/` and `/migration` at 1440×900 and 390×844 and take screenshots. For each chart apply the checklist in spec §6 (question, encoding, title, unit, honest axis, reference period marked, tooltip, source and update date, provisional distinct, latest highlighted, caveat) and the taste skill's §14 pre-flight. Record pass/fail per chart and fix defects in the component, not by weakening the checklist. Keep the screenshots in `docs/screenshots/` only if Kevin wants them committed; otherwise leave them in scratch.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add migration page, overview page and shared dashboard components

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Release Analysis, Release Calendar and Data Health pages

**Files:**
- Replace: `frontend/src/pages/{ReleaseAnalysis.tsx,Calendar.tsx,Health.tsx}`
- Modify: `frontend/src/index.css` (print styles)
- Test: `frontend/src/pages/ReleaseAnalysis.test.tsx`, `Calendar.test.tsx`, `Health.test.tsx`

**Interfaces:**
- Consumes: hooks from Task 13; components from Task 15; fixtures `release_detail.json`, `release_scheduled.json`, `calendar.json`, `health.json`.
- Produces: default-exported pages `ReleaseAnalysis` (route `/releases/:id`), `Calendar` (`/calendar`; filters persisted in the URL query: `?category=&importance=&status=&view=list|month&month=YYYY-MM`), `Health` (`/health`).

Release Analysis answers the seven questions in the spec in this order: what was published (header + headline), most important numbers (headline metrics table), what changed since the previous comparable period (previous-release comparison with revision vs new-period split), historical context, revisions, what is statistically noteworthy, reasonable implications (interpretation, observation vs inference labelled), then source and methodology. It prints cleanly.

- [ ] **Step 1: Write the failing tests**

`frontend/src/pages/ReleaseAnalysis.test.tsx`:

```tsx
import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";
import detail from "@/test/fixtures/release_detail.json";
import scheduled from "@/test/fixtures/release_scheduled.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import ReleaseAnalysis from "./ReleaseAnalysis";

const ui = (
  <Routes>
    <Route path="/releases/:id" element={<ReleaseAnalysis />} />
  </Routes>
);

describe("ReleaseAnalysis", () => {
  beforeEach(() => {
    mockApi({
      [`/api/releases/${detail.release.id}`]: detail,
      [`/api/releases/${scheduled.release.id}`]: scheduled,
    });
  });

  it("answers the questions in order with source and methodology", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    expect(await screen.findByRole("heading", { level: 1, name: new RegExp(detail.release.title) })).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Executive summary", "Headline metrics", "Since the previous release",
      "Historical context", "Revision analysis", "Interpretation", "Source and methodology",
    ]);
    expect(screen.getByRole("link", { name: /view the original stats nz publication/i })).toHaveAttribute("href", expect.stringContaining("stats.govt.nz"));
  });

  it("separates revisions from the new reference period", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    const section = (await screen.findByRole("heading", { name: "Since the previous release" })).closest("section")!;
    expect(within(section).getAllByText(/revision of/i).length).toBeGreaterThan(0);
    expect(within(section).getAllByText(/new reference period/i).length).toBeGreaterThan(0);
  });

  it("labels inference apart from observation", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    const section = (await screen.findByRole("heading", { name: "Interpretation" })).closest("section")!;
    const inferences = detail.analysis!.interpretation.filter((i) => i.kind === "inference");
    expect(within(section).queryAllByText("Inference")).toHaveLength(inferences.length);
  });

  it("explains why there is no analysis for a scheduled release", async () => {
    renderWithProviders(ui, { route: `/releases/${scheduled.release.id}` });
    expect(await screen.findByText(new RegExp(scheduled.unavailable_reason!.slice(0, 20)))).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Executive summary" })).not.toBeInTheDocument();
  });

  it("handles an unknown release", async () => {
    renderWithProviders(ui, { route: "/releases/987654" });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("offers printing", async () => {
    renderWithProviders(ui, { route: `/releases/${detail.release.id}` });
    expect(await screen.findByRole("button", { name: /print/i })).toBeInTheDocument();
  });
});
```

`frontend/src/pages/Calendar.test.tsx`:

```tsx
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import calendar from "@/test/fixtures/calendar.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Calendar from "./Calendar";

describe("Calendar", () => {
  beforeEach(() => {
    mockApi({ "/api/calendar": calendar });
  });

  it("lists releases with date, time, status and the last successful check", async () => {
    renderWithProviders(<Calendar />);
    expect(await screen.findByRole("heading", { level: 1, name: /release calendar/i })).toBeInTheDocument();
    expect(screen.getByText(/last successful check/i)).toBeInTheDocument();
    const first = calendar.items[0];
    expect(screen.getAllByText(first.title).length).toBeGreaterThan(0);
  });

  it("filters by category and importance", async () => {
    renderWithProviders(<Calendar />);
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("combobox", { name: /category/i }));
    await userEvent.click(await screen.findByRole("option", { name: "Migration" }));
    const list = screen.getByRole("list", { name: /releases/i });
    for (const li of within(list).getAllByRole("listitem")) {
      expect(li).toHaveTextContent(/Migration/);
    }
  });

  it("switches to a month grid view", async () => {
    renderWithProviders(<Calendar />);
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("radio", { name: /month/i }));
    expect(screen.getByRole("grid", { name: /release calendar month/i })).toBeInTheDocument();
  });

  it("explains an empty calendar", async () => {
    mockApi({ "/api/calendar": { items: [], last_checked_at: null, last_success_at: null } });
    renderWithProviders(<Calendar />);
    expect(await screen.findByText(/no releases in this period/i)).toBeInTheDocument();
  });
});
```

`frontend/src/pages/Health.test.tsx`:

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import health from "@/test/fixtures/health.json";
import { mockApi, renderWithProviders } from "@/test/mockApi";
import Health from "./Health";

describe("Health", () => {
  it("shows each source's state, recent ingestion runs and counts", async () => {
    mockApi({ "/api/health": health });
    renderWithProviders(<Health />);
    expect(await screen.findByRole("heading", { level: 1, name: /data health/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /sources/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /recent ingestion runs/i })).toBeInTheDocument();
    expect(screen.getByText(/series/i)).toBeInTheDocument();
  });

  it("makes failures understandable", async () => {
    mockApi({
      "/api/health": {
        ...health,
        sources: [{ source: "release:international-migration", state: "degraded", last_checked_at: "2026-10-14T10:50:00+13:00", last_success_at: null, detail: "validation_failed: [continuity] missing months" }],
        recent_runs: [{ release_key: "x", started_at: "2026-10-14T10:50:00+13:00", outcome: "failed", error_class: "validation_failed", detail: "[continuity] missing months" }],
      },
    });
    renderWithProviders(<Health />);
    expect(await screen.findAllByText(/validation_failed/)).not.toHaveLength(0);
    expect(screen.getByText(/last known good data is still being shown/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npm test -- src/pages`
Expected: FAIL — pages are stubs.

- [ ] **Step 3: Implement the Release Analysis page**

`frontend/src/pages/ReleaseAnalysis.tsx`:

```tsx
import { Link, useParams } from "react-router-dom";
import { useRelease } from "@/api/hooks";
import type { ReleaseAnalysis as Analysis } from "@/api/types";
import { InsightList } from "@/components/InsightList";
import { KpiCard } from "@/components/KpiCard";
import { EmptyState, QueryBoundary } from "@/components/QueryBoundary";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { formatAklDateTime, formatNumber, formatPercent, monthLabel } from "@/lib/format";

function MetricsTable({ analysis }: { analysis: Analysis }) {
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Headline metrics</caption>
      <thead>
        <tr className="border-b text-xs text-muted-foreground">
          <th scope="col" className="py-1 pr-3 font-medium">Measure</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Value (people)</th>
          <th scope="col" className="py-1 pr-3 font-medium">Period</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Change vs prior period</th>
          <th scope="col" className="py-1 pr-3 text-right font-medium">Change vs year earlier</th>
          <th scope="col" className="py-1 font-medium">Status</th>
        </tr>
      </thead>
      <tbody>
        {analysis.headline_metrics.map((m) => (
          <tr key={m.series_key} className="border-b last:border-0">
            <th scope="row" className="py-1.5 pr-3 font-normal">{m.label}</th>
            <td className="py-1.5 pr-3 text-right font-medium">{formatNumber(m.value)}{m.std_error ? <span className="text-xs text-muted-foreground"> ±{formatNumber(m.std_error)}</span> : null}</td>
            <td className="py-1.5 pr-3">{m.period_label}</td>
            <td className="py-1.5 pr-3 text-right">{m.change_prior ? `${formatNumber(m.change_prior.absolute, { signed: true })} (${formatPercent(m.change_prior.percent)})` : "n/a"}</td>
            <td className="py-1.5 pr-3 text-right">{m.change_year_ago ? `${formatNumber(m.change_year_ago.absolute, { signed: true })} (${formatPercent(m.change_year_ago.percent)})` : "n/a"}</td>
            <td className="py-1.5"><StatusBadge status={m.status} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Analysis({ analysis }: { analysis: Analysis }) {
  const rel = analysis.release;
  const cmp = analysis.previous_comparison;
  const rev = analysis.revisions;
  return (
    <article className="space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Release analysis</p>
        <h1 className="text-xl font-semibold tracking-tight">{rel.title}</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          Published {formatAklDateTime(rel.published_at)} <StatusBadge status={rel.status} />
        </p>
        {rel.headline && <p className="mt-2 text-sm">{rel.headline}</p>}
        <div className="mt-2 flex gap-2 print:hidden">
          <Button variant="outline" size="sm" onClick={() => window.print()}>Print or save as PDF</Button>
        </div>
      </header>

      <section aria-labelledby="exec"><h2 id="exec" className="text-lg font-semibold">Executive summary</h2><div className="mt-2"><InsightList insights={analysis.executive_summary} /></div></section>

      <section aria-labelledby="metrics">
        <h2 id="metrics" className="text-lg font-semibold">Headline metrics</h2>
        <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4 print:hidden">
          {analysis.headline_metrics.slice(0, 4).map((m) => (
            <KpiCard key={m.series_key} kpi={{ metric: m, release_id: rel.id, published_at: rel.published_at, source_url: rel.page_url }} />
          ))}
        </div>
        <div className="mt-3 overflow-x-auto"><MetricsTable analysis={analysis} /></div>
      </section>

      <section aria-labelledby="prev">
        <h2 id="prev" className="text-lg font-semibold">Since the previous release</h2>
        <p className="mt-1 text-sm text-muted-foreground">{cmp.note}</p>
        {cmp.available && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Change since the previous release, split into revision and new period</caption>
              <thead><tr className="border-b text-xs text-muted-foreground">
                <th scope="col" className="py-1 pr-3 font-medium">Measure</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">As published before</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">Revision of the previous period</th>
                <th scope="col" className="py-1 pr-3 text-right font-medium">Movement to new reference period</th>
                <th scope="col" className="py-1 text-right font-medium">Now</th>
              </tr></thead>
              <tbody>
                {cmp.decompositions.map((d) => (
                  <tr key={d.series_key} className="border-b last:border-0">
                    <th scope="row" className="py-1.5 pr-3 font-normal">{d.label}<span className="block text-xs text-muted-foreground">{monthLabel(d.previous_period)} → {monthLabel(d.new_period)}</span></th>
                    <td className="py-1.5 pr-3 text-right">{formatNumber(d.previous_published_value)}</td>
                    <td className="py-1.5 pr-3 text-right">{formatNumber(d.revision_component, { signed: true })} <span className="text-xs text-muted-foreground">(revision of {monthLabel(d.previous_period)})</span></td>
                    <td className="py-1.5 pr-3 text-right">{formatNumber(d.new_period_component, { signed: true })} <span className="text-xs text-muted-foreground">(new reference period {monthLabel(d.new_period)})</span></td>
                    <td className="py-1.5 text-right font-medium">{formatNumber(d.new_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="ctx"><h2 id="ctx" className="text-lg font-semibold">Historical context</h2><div className="mt-2"><InsightList insights={analysis.context} /></div></section>

      <section aria-labelledby="rev">
        <h2 id="rev" className="text-lg font-semibold">Revision analysis</h2>
        <p className="mt-1 text-sm text-muted-foreground">{rev.note}</p>
        {rev.available && (
          <>
            <p className="mt-1 text-sm">{rev.n_revised} of {rev.n_common} overlapping months were revised{rev.mean_abs !== null ? `; mean absolute revision ${formatNumber(rev.mean_abs, { decimals: 1 })} people` : ""}.</p>
            {rev.largest.length > 0 && (
              <table className="mt-2 w-full text-left text-sm">
                <caption className="sr-only">Largest revisions to monthly net migration</caption>
                <thead><tr className="border-b text-xs text-muted-foreground">
                  <th scope="col" className="py-1 pr-3 font-medium">Month</th><th scope="col" className="py-1 pr-3 text-right font-medium">Original</th>
                  <th scope="col" className="py-1 pr-3 text-right font-medium">Revised</th><th scope="col" className="py-1 pr-3 text-right font-medium">Revision</th>
                  <th scope="col" className="py-1 font-medium">Status change</th>
                </tr></thead>
                <tbody>
                  {rev.largest.map((r) => (
                    <tr key={r.period} className="border-b last:border-0">
                      <th scope="row" className="py-1.5 pr-3 font-normal">{monthLabel(r.period)}</th>
                      <td className="py-1.5 pr-3 text-right">{formatNumber(r.original)}</td>
                      <td className="py-1.5 pr-3 text-right">{formatNumber(r.revised)}</td>
                      <td className="py-1.5 pr-3 text-right">{formatNumber(r.absolute, { signed: true })} ({formatPercent(r.percent)})</td>
                      <td className="py-1.5">{r.original_status} → {r.revised_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </section>

      <section aria-labelledby="interp">
        <h2 id="interp" className="text-lg font-semibold">Interpretation</h2>
        <p className="mt-1 text-xs text-muted-foreground">Observations are arithmetic on published values. Inferences are labelled and never identify causes.</p>
        <div className="mt-2"><InsightList insights={analysis.interpretation} /></div>
      </section>

      <section aria-labelledby="src">
        <h2 id="src" className="text-lg font-semibold">Source and methodology</h2>
        {analysis.methodology.source_url && (
          <p className="mt-1 text-sm"><a className="underline underline-offset-2" href={analysis.methodology.source_url} target="_blank" rel="noreferrer">View the original Stats NZ publication</a></p>
        )}
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          {[...analysis.methodology.definitions, ...analysis.methodology.notes].map((t, i) => <li key={i}>{t}</li>)}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">Analysis generated {formatAklDateTime(analysis.vintage_captured_at)} from this release's official data files. Source: Stats NZ (CC BY 4.0).</p>
      </section>
    </article>
  );
}

export default function ReleaseAnalysis() {
  const id = Number(useParams().id);
  const q = useRelease(id);
  return (
    <QueryBoundary query={q}>
      {(d) =>
        d.analysis ? (
          <Analysis analysis={d.analysis} />
        ) : (
          <div className="space-y-3">
            <h1 className="text-xl font-semibold tracking-tight">{d.release.title}</h1>
            <p className="text-sm text-muted-foreground">Published or scheduled {formatAklDateTime(d.release.published_at)}</p>
            <EmptyState title="No analysis is available for this release yet" body={d.unavailable_reason ?? "Unknown reason."} />
            {d.release.page_url && <a className="text-sm underline underline-offset-2" href={d.release.page_url} target="_blank" rel="noreferrer">Open the Stats NZ page</a>}
            <p><Link className="text-sm underline underline-offset-2" to="/calendar">Back to the release calendar</Link></p>
          </div>
        )
      }
    </QueryBoundary>
  );
}
```

Add print styles to `index.css`:

```css
@media print {
  header[role="banner"], nav, .print\:hidden { display: none !important; }
  body { background: #fff; color: #000; font-size: 11pt; }
  details > * { display: block; }
  details { break-inside: avoid; }
  section, figure, table { break-inside: avoid; }
  a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 8pt; word-break: break-all; }
  main { max-width: none; padding: 0; }
}
```

- [ ] **Step 4: Implement the Calendar page**

`frontend/src/pages/Calendar.tsx` (filters live in the URL so a view can be shared):

```tsx
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useCalendar } from "@/api/hooks";
import type { ReleaseSummary } from "@/api/types";
import { QueryBoundary } from "@/components/QueryBoundary";
import { ReleaseRow } from "@/components/ReleaseRow";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { formatAklDate, formatAklDateTime } from "@/lib/format";

const ALL = "all";
const dayKey = (iso: string) => iso.slice(0, 10);

function MonthGrid({ items, month }: { items: ReleaseSummary[]; month: string }) {
  const [y, m] = month.split("-").map(Number);
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7; // Monday-first
  const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const byDay = new Map<string, ReleaseSummary[]>();
  for (const r of items) byDay.set(dayKey(r.published_at), [...(byDay.get(dayKey(r.published_at)) ?? []), r]);
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const weeks = Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
  return (
    <table role="grid" aria-label={`Release calendar month ${month}`} className="w-full table-fixed border-collapse text-xs">
      <thead>
        <tr>{["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <th key={d} scope="col" className="border bg-muted p-1 font-medium">{d}</th>)}</tr>
      </thead>
      <tbody>
        {weeks.map((week, w) => (
          <tr key={w}>
            {week.map((day, i) => {
              const rels = day ? byDay.get(`${month}-${String(day).padStart(2, "0")}`) ?? [] : [];
              return (
                <td key={i} className="h-20 border p-1 align-top">
                  {day && <span className="text-muted-foreground">{day}</span>}
                  <ul className="mt-0.5 space-y-0.5">
                    {rels.map((r) => (
                      <li key={r.id} className="truncate" title={r.title}>
                        {r.has_analysis ? <Link className="underline-offset-2 hover:underline" to={`/releases/${r.id}`}>{r.title}</Link> : r.title}
                      </li>
                    ))}
                  </ul>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Calendar() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") ?? ALL;
  const importance = params.get("importance") ?? ALL;
  const status = params.get("status") ?? ALL;
  const view = params.get("view") ?? "list";
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v === ALL || v === "list") next.delete(k);
    else next.set(k, v);
    setParams(next, { replace: true });
  };
  const q = useCalendar();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Release calendar</h1>
        <p className="text-sm text-muted-foreground">Scheduled and recently published Stats NZ releases (Pacific/Auckland time).</p>
      </div>
      <QueryBoundary query={q}>
        {(d) => {
          const categories = [...new Set(d.items.map((i) => i.category))].sort();
          const items = d.items.filter((i) =>
            (category === ALL || i.category === category) &&
            (importance === ALL || i.importance === importance) &&
            (status === ALL || i.status === status));
          const month = (items[0] ?? d.items[0])?.published_at.slice(0, 7) ?? new Date().toISOString().slice(0, 7);
          const grouped = new Map<string, ReleaseSummary[]>();
          for (const r of items) grouped.set(dayKey(r.published_at), [...(grouped.get(dayKey(r.published_at)) ?? []), r]);
          return (
            <>
              <p className="text-xs text-muted-foreground">
                Last successful check: {d.last_success_at ? formatAklDateTime(d.last_success_at) : "never"}
                {d.last_checked_at && d.last_checked_at !== d.last_success_at ? ` · last attempt ${formatAklDateTime(d.last_checked_at)}` : ""}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Select value={category} onValueChange={(v) => set("category", v)}>
                  <SelectTrigger aria-label="Category" className="w-56"><SelectValue placeholder="Category" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL}>All categories</SelectItem>
                    {categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
                <ToggleGroup type="single" variant="outline" size="sm" value={importance} aria-label="Importance" onValueChange={(v) => v && set("importance", v)}>
                  <ToggleGroupItem value={ALL}>Any importance</ToggleGroupItem>
                  <ToggleGroupItem value="high">High</ToggleGroupItem>
                  <ToggleGroupItem value="medium">Medium</ToggleGroupItem>
                </ToggleGroup>
                <ToggleGroup type="single" variant="outline" size="sm" value={status} aria-label="Status" onValueChange={(v) => v && set("status", v)}>
                  <ToggleGroupItem value={ALL}>Any status</ToggleGroupItem>
                  <ToggleGroupItem value="scheduled">Scheduled</ToggleGroupItem>
                  <ToggleGroupItem value="published">Published</ToggleGroupItem>
                </ToggleGroup>
                <ToggleGroup type="single" variant="outline" size="sm" value={view} aria-label="View" onValueChange={(v) => v && set("view", v)}>
                  <ToggleGroupItem value="list" aria-label="List">List</ToggleGroupItem>
                  <ToggleGroupItem value="month" aria-label="Month">Month</ToggleGroupItem>
                </ToggleGroup>
              </div>
              {items.length === 0 ? (
                <p className="rounded-md border border-dashed p-6 text-sm">No releases in this period match the filters.</p>
              ) : view === "month" ? (
                <MonthGrid items={items} month={month} />
              ) : (
                <ul aria-label="Releases" className="space-y-4">
                  {[...grouped].map(([day, rels]) => (
                    <li key={day}>
                      <h2 className="text-sm font-semibold">{formatAklDate(rels[0].published_at)}</h2>
                      <ul className="divide-y rounded-md border px-3">{rels.map((r) => <ReleaseRow key={r.id} release={r} />)}</ul>
                    </li>
                  ))}
                </ul>
              )}
            </>
          );
        }}
      </QueryBoundary>
    </div>
  );
}
```

The calendar test expects `getByRole("list", { name: /releases/i })` whose `listitem` children all contain "Migration" after filtering — the outer list items are *day groups* that contain `ReleaseRow`s; each row shows its category. Because the outer `li` text includes each contained row's category text and the date heading, and all rows are Migration after filtering, `toHaveTextContent(/Migration/)` holds. If the empty message must match `/no releases in this period/i`, the sentence above does ("No releases in this period match the filters.").

- [ ] **Step 5: Implement the Health page**

`frontend/src/pages/Health.tsx`:

```tsx
import { useHealth } from "@/api/hooks";
import { QueryBoundary } from "@/components/QueryBoundary";
import { formatAklDateTime } from "@/lib/format";

export default function Health() {
  const q = useHealth();
  return (
    <QueryBoundary query={q}>
      {(d) => {
        const degraded = d.sources.filter((s) => s.state !== "ok");
        return (
          <div className="space-y-5">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Data health</h1>
              <p className="text-sm text-muted-foreground">
                What the monitor has checked, and whether it worked. {d.series_count} series, {d.vintage_count} stored vintages. Database {d.database_ok ? "OK" : "unavailable"}.
              </p>
            </div>
            {degraded.length > 0 && (
              <p role="status" className="rounded-md border border-amber-600/50 p-3 text-sm">
                {degraded.length} source{degraded.length > 1 ? "s are" : " is"} degraded. The last known good data is still being shown; nothing has been overwritten by a failed update.
              </p>
            )}
            <section aria-labelledby="sources">
              <h2 id="sources" className="text-lg font-semibold">Sources</h2>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-left text-sm">
                  <caption className="sr-only">Sources</caption>
                  <thead><tr className="border-b text-xs text-muted-foreground">
                    <th scope="col" className="py-1 pr-3 font-medium">Source</th><th scope="col" className="py-1 pr-3 font-medium">State</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Last checked</th><th scope="col" className="py-1 pr-3 font-medium">Last success</th>
                    <th scope="col" className="py-1 font-medium">Detail</th>
                  </tr></thead>
                  <tbody>
                    {d.sources.map((s) => (
                      <tr key={s.source} className="border-b last:border-0">
                        <th scope="row" className="py-1.5 pr-3 font-normal">{s.source}</th>
                        <td className="py-1.5 pr-3">{s.state === "ok" ? "OK" : "Degraded"}</td>
                        <td className="py-1.5 pr-3">{s.last_checked_at ? formatAklDateTime(s.last_checked_at) : "never"}</td>
                        <td className="py-1.5 pr-3">{s.last_success_at ? formatAklDateTime(s.last_success_at) : "never"}</td>
                        <td className="py-1.5">{s.detail ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section aria-labelledby="runs">
              <h2 id="runs" className="text-lg font-semibold">Recent ingestion runs</h2>
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-left text-sm">
                  <caption className="sr-only">Recent ingestion runs</caption>
                  <thead><tr className="border-b text-xs text-muted-foreground">
                    <th scope="col" className="py-1 pr-3 font-medium">When</th><th scope="col" className="py-1 pr-3 font-medium">Release</th>
                    <th scope="col" className="py-1 pr-3 font-medium">Outcome</th><th scope="col" className="py-1 font-medium">Error class and detail</th>
                  </tr></thead>
                  <tbody>
                    {d.recent_runs.map((r, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-1.5 pr-3">{formatAklDateTime(r.started_at)}</td>
                        <td className="py-1.5 pr-3">{r.release_key}</td>
                        <td className="py-1.5 pr-3">{r.outcome}</td>
                        <td className="py-1.5">{r.error_class ? `${r.error_class}: ${r.detail ?? ""}` : (r.detail ?? "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <p className="text-xs text-muted-foreground">
              Release counts: {Object.entries(d.release_counts).map(([k, v]) => `${k} ${v}`).join(" · ") || "none"}. Error classes: network, blocked, not_found (not yet published), layout_changed, validation_failed, unexpected. See docs/troubleshooting.md.
            </p>
          </div>
        );
      }}
    </QueryBoundary>
  );
}
```

- [ ] **Step 6: Run to verify pass; typecheck; build; §14 pre-flight**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: PASS. Then repeat Task 15 Step 7 for `/releases/<id>`, `/calendar` (list and month, filtered) and `/health` at 1440×900 and 390×844; additionally open `/releases/<id>` and print-preview it (Playwright `page.pdf()` or the browser's print preview) and check that navigation is hidden, sections do not split mid-table and links print their URLs. Run the taste skill's §14 checklist and the accessibility checks: keyboard-only traversal of every control, visible focus, landmark structure, and colour contrast of text and chart colours in light and dark.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: add release analysis, release calendar and data health pages

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Docker, CI, documentation and Phase 1 verification

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/backup.sh`
- Create: `frontend/playwright.config.ts`, `frontend/e2e/smoke.spec.ts`
- Create: `README.md`, `CLAUDE.md`, `docs/{architecture.md,data-sources.md,data-dictionary.md,troubleshooting.md,progress.md}`
- Modify: `backend/src/nzstats/cli.py` (`serve --no-scheduler`), `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: a reproducible container build, CI, accurate operator documentation, and verification evidence in `docs/progress.md`.

- [ ] **Step 1: `serve --no-scheduler` with a test**

In `cli.py` add to the `serve` subparser: `p_serve.add_argument("--no-scheduler", action="store_true", help="serve the API and UI without background jobs")` and call `create_app(settings, start_scheduler=not args.no_scheduler)`. Test in `tests/test_cli.py`:

```python
def test_serve_accepts_no_scheduler_flag(tmp_path, monkeypatch) -> None:
    import nzstats.api.app as app_module

    captured = {}
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(app_module, "create_app",
                        lambda settings, start_scheduler: captured.setdefault("s", start_scheduler))
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    assert main(["serve", "--no-scheduler", "--port", "9"]) == 0
    assert captured["s"] is False
```

Run: `cd backend && pytest tests/test_cli.py -v` — expected PASS.

- [ ] **Step 2: Dockerfile, ignore file, Compose**

`Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Pacific/Auckland \
    NZSTATS_DATA_DIR=/data NZSTATS_STATIC_DIR=/app/static \
    NZSTATS_SOURCES_FILE=/app/config/sources.toml
WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
RUN pip install ./backend
COPY config /app/config
COPY --from=web /web/dist /app/static
RUN useradd --system --uid 10001 nzstats && mkdir /data && chown nzstats /data
USER nzstats
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["nzstats", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`:

```
.git
.worktrees
**/node_modules
**/.venv
**/__pycache__
data
.env
frontend/dist
frontend/playwright-report
docs
```

`docker-compose.yml`:

```yaml
services:
  nzstats:
    build: .
    image: nzstats:local
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      TZ: Pacific/Auckland
      NZSTATS_CONTACT: ${NZSTATS_CONTACT:-}
      NZSTATS_MIN_INTERVAL_SECONDS: ${NZSTATS_MIN_INTERVAL_SECONDS:-10}
    env_file:
      - path: .env
        required: false
    volumes:
      - ./data:/data
    # On a Synology NAS set NZSTATS_UID/NZSTATS_GID in .env to the owner of ./data (see `id`).
    user: "${NZSTATS_UID:-10001}:${NZSTATS_GID:-10001}"
```

`scripts/backup.sh`:

```bash
#!/usr/bin/env sh
# Consistent online backup of the SQLite database into ./data/backups/. Raw artifacts are
# content-addressed and re-fetchable; copy ./data/raw too if you want a full archive.
set -eu
dest="data/backups/nzstats-$(date +%F-%H%M).db"
mkdir -p data/backups
docker compose exec -T nzstats nzstats backup "/data/backups/$(basename "$dest")"
echo "backup written to $dest"
```

Make it executable: `chmod +x scripts/backup.sh`.

- [ ] **Step 3: GitHub Actions**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -e '.[dev]'
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest

  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: pip install -e '../backend[dev]'
      - run: npm ci
      - name: API types are up to date
        run: npm run gen:api && git diff --exit-code -- src/api/schema.d.ts openapi.json
      - run: npm run typecheck
      - run: npm test
      - run: npm run build

  docker:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t nzstats:ci .
      - name: Container starts and reports healthy
        run: |
          docker run -d --name nzstats -p 8000:8000 -e NZSTATS_DATA_DIR=/tmp/data nzstats:ci \
            nzstats serve --no-scheduler --host 0.0.0.0 --port 8000
          for i in $(seq 1 30); do curl -fsS localhost:8000/api/health && exit 0; sleep 2; done
          docker logs nzstats; exit 1
```

- [ ] **Step 4: Playwright smoke test (desktop and mobile)**

`frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

const dataDir = process.env.E2E_DATA_DIR ?? "/tmp/nzstats-e2e";

export default defineConfig({
  testDir: "./e2e",
  webServer: {
    command:
      `python ../scripts/seed_e2e_db.py ${dataDir} && ` +
      `NZSTATS_DATA_DIR=${dataDir} NZSTATS_STATIC_DIR=dist nzstats serve --no-scheduler --port 8765`,
    url: "http://127.0.0.1:8765/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
  use: { baseURL: "http://127.0.0.1:8765", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
```

`frontend/e2e/smoke.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("overview shows KPIs, panels and no console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Economic overview" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Key indicators" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Upcoming releases" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("migration page renders charts on canvas and exports data", async ({ page }) => {
  await page.goto("/migration");
  await expect(page.getByRole("heading", { name: "International migration", level: 1 })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /download data/i }).first().click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
});

test("client-side routes survive a reload and the API 404s as JSON", async ({ page, request }) => {
  await page.goto("/calendar");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Release calendar" })).toBeVisible();
  const res = await request.get("/api/nope");
  expect(res.status()).toBe(404);
  expect(res.headers()["content-type"]).toContain("application/json");
});

test("release analysis page and print layout", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /read the full release analysis/i }).click();
  await expect(page.getByRole("heading", { name: "Executive summary" })).toBeVisible();
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
});

test("no horizontal scroll on the overview", async ({ page }) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
```

Run: `cd frontend && npm run build && npx playwright install chromium && npx playwright test`
Expected: all tests pass on both projects.

- [ ] **Step 5: Documentation**

Write, in the repo root and `docs/`, accurate documents (each section below must reflect the code as built, not this plan):

- `README.md`: what/why; screenshot-free quickstart; `cp .env.example .env`; `docker compose up -d --build`; first-run `docker compose exec nzstats nzstats discover` then `nzstats backfill` (explain the ~10 s/request pace and expected duration); start/stop/update (`git pull && docker compose up -d --build`); backup (`scripts/backup.sh`) and restore (stop, replace `data/nzstats.db`, start); Synology notes (Container Manager, `NZSTATS_UID/GID`, volume permissions, reverse proxy/HTTPS recommendation, keep the instance private unless the Stats NZ terms were reviewed); local development (venv, `pytest`, `npm run dev`); test commands; known limitations (Phase 1 covers International migration only; vintage depth from the spike; undocumented month endpoint); licence/attribution (Stats NZ CC BY 4.0).
- `CLAUDE.md` (project-specific, concise): stack and layout; commands (`pytest`, `ruff`, `npm test`, `npm run gen:api`, `scripts/dump_frontend_fixtures.py`); rules (10 s crawl delay is a hard constraint, no synthetic production data, fixtures are real excerpts, store timestamps in UTC, never mix monthly and year-ended series, regions are not countries, last-known-good must survive failures, never loosen validation thresholds without evidence); where the spec, plan and progress file live; the taste-skill usage note from spec §9.
- `docs/architecture.md`: component diagram in text, data flow, data model, scheduling, failure handling (mirror spec §4–§7 with the as-built differences).
- `docs/data-sources.md`: the data-source registry: for each source its URL/path, mechanism, auth (none; ADE needs a key), format, cadence, fragility (undocumented month endpoint), robots/crawl-delay, licence, verified-on dates and what was observed (copy the verified facts from spec §2 and from the vintage-depth report).
- `docs/data-dictionary.md`: every series key with name, unit, frequency, adjustment, definition, source file/column, status semantics (provisional = latest 16 months per Stats NZ labelling in the file), standard-error semantics (zero on final), period semantics for year-ended series, derived country ranking rules, category and importance catalogue.
- `docs/troubleshooting.md`: one entry per error class (`network`, `blocked`, `not_found`, `layout_changed`, `validation_failed`, `unexpected`) with symptom, where to look (Data health page, `ingest_run` table, container logs), likely cause and fix; plus: calendar stale, release not appearing at 10:45, database locked, wrong timezone, permission denied on `/data`, how to re-run a release (`nzstats ingest --release-key "international-migration:august 2026"`), how to reprocess from stored artifacts.
- `docs/progress.md`: concise record: phase status, what is verified (with command output summaries and dates), remaining work, and the exact resume steps for Phase 2.

- [ ] **Step 6: Full verification (evidence before any "done" claim)**

Invoke `superpowers:verification-before-completion`, then run and record the output of each (paste short summaries into `docs/progress.md`):

```bash
cd backend && . .venv/bin/activate && ruff check . && ruff format --check . && pytest
cd ../frontend && npm run typecheck && npm test && npm run build && npx playwright test
cd .. && docker compose build && docker compose up -d && sleep 15 && curl -fsS localhost:8000/api/health && curl -fsS localhost:8000/ | head -c 200 && docker compose ps && docker compose down
```

Then the **real-site integration check** (throttled; the only step that reaches stats.govt.nz). Use a scratch data directory, not the project's `data/`:

```bash
cd backend && NZSTATS_DATA_DIR=/tmp/nzstats-real NZSTATS_CONTACT=kevin.ct.chang@gmail.com \
  nzstats discover && NZSTATS_DATA_DIR=/tmp/nzstats-real NZSTATS_CONTACT=kevin.ct.chang@gmail.com \
  nzstats backfill
```

Run in the background (expect roughly 15–25 minutes: one month request plus three requests per release at 10 s each). Expected: every release from `backfill_since` onward prints `ingested`; `nzstats health` shows `release:international-migration` OK. Then verify real values against the official site: open the latest release page and confirm the dashboard's year-ended net, monthly net and arrivals/departures equal the published numbers; confirm revision rows exist between consecutive real vintages; confirm provisional/final flags match the source's `status` column. If any release prints `failed`, diagnose with `superpowers:systematic-debugging` (read the `ingest_run` detail, fetch the file, find the root cause); fix the code or, only with evidence from the real file, the threshold; add a regression test; re-run. Record outcomes and any failures in `docs/progress.md`.

Finally the **scheduler check**: if today's date is on or after 2026-10-14, start `nzstats serve` against the scratch data directory before 10:45 NZDT and confirm the International migration: August 2026 release is ingested within the polling window (watch `nzstats health` / the Data health page); otherwise record in `docs/progress.md` that the live scheduler check is pending for that release.

- [ ] **Step 7: Phase 1 completion review**

Check each completion standard from the brief and mark it with evidence in `docs/progress.md`: required Phase 1 features work; app builds; relevant tests pass; official data validated (real ingestion); important charts visually inspected (Task 15/16 checklists, desktop and mobile); no known critical issues; deployment instructions tested (`docker compose up` from a clean checkout on this machine). Anything not done is listed as remaining work, not claimed. Run `superpowers:requesting-code-review` over the whole branch (spec compliance first, then quality), resolve confirmed findings, re-run Step 6's commands.

- [ ] **Step 8: Wrap-up**

Update `~/vault/AI_Context/Memory/Durable_Facts/Kevin/current-projects.md` (status, current focus, last-updated date; use the heading its "Repo → entry headings" table gives, or add an entry for this repo) per the global session wrap-up rule, then invoke `superpowers:finishing-a-development-branch` to decide how to integrate `feat/phase-1`. Do not push or open a PR without Kevin's approval.

```bash
git add -A && git commit -m "chore: add Docker, CI, end-to-end tests, documentation and Phase 1 verification record

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-review (spec coverage)

| Spec requirement | Task |
|---|---|
| Release discovery (ICS + month endpoint), release-aware scheduling, catch-up | 5, 9, 10 |
| Official files as data, vintages, revisions, idempotency, duplicates, corrected releases | 3, 7, 9, 12 |
| Validation; success only after validate + atomic commit; last-known-good | 8, 9 |
| Throttling, UA, retries, block detection, raw artifact preservation | 4 |
| Source health and freshness; data health view | 3, 9, 12, 16 |
| Statistics utilities (changes, rolling, percentile, compat, revisions) | 2 |
| Deterministic, traceable release analysis; observation vs inference; no causal claims | 11 |
| Migration dashboard (7 views), revisions, country breakdown, citizenship | 7, 12, 15 |
| Overview (KPIs, latest, upcoming, trends, freshness, featured) | 12, 15 |
| Release calendar (list + month, filters, statuses, last check) | 10, 12, 16 |
| Export (CSV, PNG, print) | 12, 14, 16 |
| Docker, CI, docs, backup/restore, Synology notes | 17 |
| Taste skill + dataviz skill usage with documented scope conflict | 13, 15, 16 |
| Inflation, labour, GDP, housing, Data Explorer, Revision Explorer UI, preferences | Phase 2/3 (out of scope here; categories shown as inactive) |

Placeholders: none intended; values that depend on live data (vintage depth, `backfill_since`) are produced by the Task 1 spike and the Task 17 integration check, each with an explicit rule for turning the output into configuration.
