"""The CSV contract for OCR decisions from an approved source, validated strictly. No network access.

Columns, in order: `announced_on,effective_on,ocr_percent,change_bp,decision,source_url`. Dates are ISO
(`YYYY-MM-DD`); `ocr_percent` has at most two decimal places; `change_bp` is empty only on the first row; `decision` is
`increase`, `decrease` or `unchanged` and must agree with the change; `source_url` must be an https URL on
www.rbnz.govt.nz. Files containing the word SYNTHETIC are refused unless a test passes `allow_synthetic=True`.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from nzstats.ocr.model import OcrDecision

HEADER = ["announced_on", "effective_on", "ocr_percent", "change_bp", "decision", "source_url"]
DECISIONS = {"increase": 1, "decrease": -1, "unchanged": 0}
MAX_RATE = Decimal("25")
MAX_ROWS = 2000  # about 8 decisions a year since 1999
MAX_EFFECTIVE_LAG_DAYS = 14


class OcrContractError(ValueError):
    pass


def _date(text: str, row: int) -> date:
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise OcrContractError(f"row {row}: date is not YYYY-MM-DD") from None


def _rate(text: str, row: int) -> Decimal:
    try:
        rate = Decimal(text)
    except InvalidOperation:
        raise OcrContractError(f"row {row}: rate is not a number") from None
    if (
        not rate.is_finite()
        or rate < 0
        or rate > MAX_RATE
        or rate != rate.quantize(Decimal("0.01"))
    ):
        raise OcrContractError(f"row {row}: rate must be 0 to 25 percent with at most two decimals")
    return rate


def parse_decisions(text: str, *, allow_synthetic: bool = False) -> list[OcrDecision]:
    if "SYNTHETIC" in text and not allow_synthetic:
        raise OcrContractError("file is marked SYNTHETIC and cannot be used as OCR data")
    lines = (
        [line for line in text.splitlines() if not line.startswith("#")]
        if allow_synthetic
        else text.splitlines()
    )
    rows = list(csv.reader(io.StringIO("\n".join(lines))))
    if not rows or rows[0] != HEADER:
        raise OcrContractError(f"header must be {','.join(HEADER)}")
    body = rows[1:]
    if not body:
        raise OcrContractError("file has no decisions")
    if len(body) > MAX_ROWS:
        raise OcrContractError("file has too many rows")
    out: list[OcrDecision] = []
    for n, fields in enumerate(body, start=2):
        if len(fields) != len(HEADER):
            raise OcrContractError(f"row {n}: expected {len(HEADER)} columns")
        announced, effective = _date(fields[0], n), _date(fields[1], n)
        if effective < announced or (effective - announced).days > MAX_EFFECTIVE_LAG_DAYS:
            raise OcrContractError(
                f"row {n}: effective date must be on or shortly after the announcement"
            )
        if out and (announced <= out[-1].announced_on or effective <= out[-1].effective_on):
            raise OcrContractError(f"row {n}: decisions must be in strictly increasing date order")
        rate = _rate(fields[2], n)
        decision = fields[4]
        if decision not in DECISIONS:
            raise OcrContractError(f"row {n}: decision must be increase, decrease or unchanged")
        change: int | None = None
        if out:
            expected = int((rate - out[-1].rate) * 100)
            try:
                change = int(fields[3])
            except ValueError:
                raise OcrContractError(
                    f"row {n}: change in basis points is required after the first row"
                ) from None
            if change != expected:
                raise OcrContractError(
                    f"row {n}: change in basis points does not equal the rate difference"
                )
            if (change > 0) - (change < 0) != DECISIONS[decision]:
                raise OcrContractError(f"row {n}: decision does not agree with the change")
        elif fields[3]:
            raise OcrContractError(
                f"row {n}: the first decision's change in basis points must be empty"
            )
        url = urlsplit(fields[5])
        if url.scheme != "https" or url.hostname != "www.rbnz.govt.nz":
            raise OcrContractError(f"row {n}: source must be an https URL on www.rbnz.govt.nz")
        out.append(OcrDecision(announced, effective, rate, change, decision, fields[5]))  # type: ignore[arg-type]
    return out
