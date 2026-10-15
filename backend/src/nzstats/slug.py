from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    folded = folded.replace("'", "")  # "People's" -> "peoples", not "people-s"
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
