"""Small formatting helpers shared by the report, the CLI and the alerts."""

from __future__ import annotations

import re
from datetime import datetime

from nzstats.clock import AKL

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean(text: str | None, limit: int = 160) -> str:
    """Upstream-derived text (a release title) made safe to print: no control characters, bounded length."""
    flat = " ".join(_CONTROL.sub(" ", text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def duration(seconds: float) -> str:
    s = int(abs(seconds))
    days, rest = divmod(s, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min" if minutes else f"{s} s"


def akl(dt: datetime) -> str:
    """'Wed 4 Nov 10:45 NZDT': the zone abbreviation says which side of daylight saving the time is on."""
    local = dt.astimezone(AKL)
    return f"{local:%a} {local.day} {local:%b %H:%M %Z}"
