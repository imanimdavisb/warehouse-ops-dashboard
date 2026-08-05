"""Display formatters.

SQL aggregates return NULL when a filter matches no rows, or when NULLIF
guards a zero denominator. These turn that into an em dash instead of a
TypeError.
"""

from __future__ import annotations

EMPTY = "—"


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN is the only value unequal to itself
    except Exception:
        return False


def fmt_int(value) -> str:
    return EMPTY if _is_missing(value) else f"{int(value):,}"


def fmt_pct(value, decimals: int = 2) -> str:
    return EMPTY if _is_missing(value) else f"{float(value):.{decimals}f}%"


def fmt_rate(value, decimals: int = 1) -> str:
    return EMPTY if _is_missing(value) else f"{float(value):,.{decimals}f}"


def fmt_delta(value, suffix: str = "", decimals: int = 2) -> str | None:
    """Signed change for st.metric. Returns None so the arrow is hidden."""
    if _is_missing(value):
        return None
    return f"{float(value):+.{decimals}f}{suffix}"
