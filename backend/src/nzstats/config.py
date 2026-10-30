"""Runtime settings: environment variables plus config/sources.toml."""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MIN_CRAWL_DELAY_SECONDS = 10.0


@dataclass(frozen=True)
class RefreshSettings:
    """Bounds for the on-open refresh (`nzstats.pipeline.refresh`); `[refresh]` in config/sources.toml."""

    fresh_window_minutes: int = 30  # a completed check this recent is reused, not repeated
    failure_cooldown_minutes: int = 10  # a failed check is retried no sooner than this
    manual_min_interval_seconds: int = 60  # "Check now" still waits this long after the last check
    max_releases: int = 6  # releases ingested per refresh; the rest are reported as pending
    max_requests: int = 40  # logical GETs per refresh, calendar included (10 s apart: under 7 min)


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
    backup_dir_override: Path | None = None
    refresh: RefreshSettings = RefreshSettings()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "nzstats.db"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def backup_dir(self) -> Path:
        return self.backup_dir_override or self.data_dir / "backups"

    @property
    def ops_dir(self) -> Path:
        return self.data_dir / "ops"


def _default_sources_file() -> Path:
    # <repo>/config/sources.toml, or set NZSTATS_SOURCES_FILE (the container does).
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "sources.toml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config/sources.toml not found; set NZSTATS_SOURCES_FILE")


def _refresh_settings(cfg: Mapping, env: Mapping[str, str]) -> RefreshSettings:
    values = {**RefreshSettings().__dict__, **cfg}
    window = env.get("NZSTATS_REFRESH_WINDOW_MINUTES")
    if window is not None:
        try:
            values["fresh_window_minutes"] = int(window)
        except ValueError:
            raise ValueError(
                "NZSTATS_REFRESH_WINDOW_MINUTES must be a whole number of minutes"
            ) from None
        if values["fresh_window_minutes"] < 1:
            raise ValueError("NZSTATS_REFRESH_WINDOW_MINUTES must be at least 1")
    refresh = RefreshSettings(**{k: int(v) for k, v in values.items()})
    if min(refresh.__dict__.values()) < 1 or refresh.max_requests < 12:
        raise ValueError("[refresh] limits must be positive and max_requests at least 12")
    return refresh


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    e = os.environ if env is None else env
    sources_file = Path(e.get("NZSTATS_SOURCES_FILE") or _default_sources_file())
    cfg = tomllib.loads(sources_file.read_text(encoding="utf-8"))

    interval = float(e.get("NZSTATS_MIN_INTERVAL_SECONDS", str(MIN_CRAWL_DELAY_SECONDS)))
    if not math.isfinite(interval):
        raise ValueError("NZSTATS_MIN_INTERVAL_SECONDS must be finite")
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
        backup_dir_override=Path(e["NZSTATS_BACKUP_DIR"]) if e.get("NZSTATS_BACKUP_DIR") else None,
        refresh=_refresh_settings(cfg.get("refresh", {}), e),
    )
