"""Pure data-cleaning helpers used by the table builders.

This module is intentionally focused on *transforming* values:

- parsing dates and datetimes
- coercing strings / mixed types to nullable booleans
- trimming and case-normalizing text

Data-quality checks, foreign-key validation, duplicate repair and the
report printer all live in :mod:`ravenstack.validation`.
"""

from __future__ import annotations

import pandas as pd

TRUE_TOKENS = {"true", "t", "yes", "y", "1"}
FALSE_TOKENS = {"false", "f", "no", "n", "0"}


def parse_date(series: pd.Series) -> pd.Series:
    """Parse a column of date strings into ``datetime64[ns]`` (date only)."""
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def parse_datetime(series: pd.Series) -> pd.Series:
    """Parse a column of datetime strings into ``datetime64[ns]``."""
    return pd.to_datetime(series, errors="coerce")


def standardize_bool(series: pd.Series) -> pd.Series:
    """Coerce a column to nullable boolean.

    Already-bool columns are returned as-is. Strings such as ``"True"``,
    ``"yes"`` and ``"1"`` are mapped to ``True``; the inverse to ``False``;
    anything else becomes ``pd.NA``.
    """
    if series.dtype == bool:
        return series.astype("boolean")

    def _to_bool(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        token = str(value).strip().lower()
        if token in TRUE_TOKENS:
            return True
        if token in FALSE_TOKENS:
            return False
        return pd.NA

    return series.map(_to_bool).astype("boolean")


def standardize_text(
    series: pd.Series,
    *,
    case: str | None = "lower",
    fill: str | None = None,
) -> pd.Series:
    """Trim whitespace and (optionally) normalize the case of a text column.

    ``case`` accepts ``"lower"``, ``"upper"``, ``"title"`` or ``None``.
    """
    cleaned = series.astype("string").str.strip()
    if case == "lower":
        cleaned = cleaned.str.lower()
    elif case == "upper":
        cleaned = cleaned.str.upper()
    elif case == "title":
        cleaned = cleaned.str.title()
    elif case is not None:
        raise ValueError(f"Unsupported case option: {case!r}")

    if fill is not None:
        cleaned = cleaned.fillna(fill)
    return cleaned
