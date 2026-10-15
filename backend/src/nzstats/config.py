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
    # <repo>/config/sources.toml, or set NZSTATS_SOURCES_FILE (the container does).
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
