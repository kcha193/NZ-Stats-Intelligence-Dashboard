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
