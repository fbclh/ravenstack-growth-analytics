"""Data quality checks, duplicate repair and report printing.

This module owns everything related to *finding* problems in the data
(duplicate primary keys, missing foreign keys, invalid date order) and
*reporting* them. It also hosts the deterministic duplicate-id repair
used by :mod:`ravenstack.base_tables`.

Each ``check_*`` function returns a small dict describing what it found.
Collect them into a list and pass them to :func:`print_report` to get a
human-readable summary on stdout.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


def check_duplicate_pks(df: pd.DataFrame, pk_col: str, table_name: str) -> dict:
    """Return a report describing duplicate primary keys, if any."""
    duplicated = df[pk_col].duplicated(keep=False)
    n_dupes = int(duplicated.sum())
    report: dict = {
        "table": table_name,
        "check": "duplicate_primary_keys",
        "column": pk_col,
        "n_duplicates": n_dupes,
    }
    if n_dupes:
        report["example_ids"] = df.loc[duplicated, pk_col].drop_duplicates().head(5).tolist()
    return report


def check_missing_fks(
    df: pd.DataFrame,
    fk_col: str,
    valid_keys: Iterable[str],
    table_name: str,
) -> dict:
    """Return a report describing foreign keys that don't resolve."""
    valid = set(valid_keys)
    missing_mask = ~df[fk_col].isin(valid) & df[fk_col].notna()
    n_missing = int(missing_mask.sum())
    report: dict = {
        "table": table_name,
        "check": "missing_foreign_keys",
        "column": fk_col,
        "n_missing": n_missing,
    }
    if n_missing:
        report["example_ids"] = df.loc[missing_mask, fk_col].drop_duplicates().head(5).tolist()
    return report


def check_date_order(
    df: pd.DataFrame,
    start_col: str,
    end_col: str,
    table_name: str,
) -> dict:
    """Return a report describing rows where ``end_col`` < ``start_col``."""
    both_present = df[start_col].notna() & df[end_col].notna()
    invalid = both_present & (df[end_col] < df[start_col])
    n_invalid = int(invalid.sum())
    return {
        "table": table_name,
        "check": "invalid_date_order",
        "columns": f"{end_col} >= {start_col}",
        "n_invalid": n_invalid,
    }


def resolve_usage_id_duplicates(
    df: pd.DataFrame, pk_col: str = "usage_id"
) -> tuple[pd.DataFrame, dict]:
    """Resolve duplicate ``usage_id`` values with stable, deterministic ids.

    For each ``usage_id`` that appears more than once:

    1. Rows that are **fully identical** (every column matches) are collapsed
       to a single row.
    2. Rows that still share a ``usage_id`` but differ on any column are sorted
       deterministically (by every non-pk column, then by the original row
       index as a tiebreaker). The first row keeps the original id; each
       additional row gets a deterministic replacement id of the form
       ``{original_usage_id}-rs-{NNN}`` starting at ``001`` and zero-padded
       to at least 3 digits.
    3. Generated ids are checked against **every** id already present in the
       frame (including ones still being remapped) so collisions are avoided
       globally. If a generated id already exists, the suffix counter is
       advanced until a free slot is found.

    The result is fully reproducible across runs for the same input.
    """
    report: dict = {
        "table": "fact_feature_usage",
        "check": "usage_id_duplicate_resolution",
        "n_usage_ids_affected": 0,
        "n_identical_duplicate_rows_removed": 0,
        "n_rows_remapped_to_new_usage_id": 0,
    }

    if not df[pk_col].duplicated(keep=False).any():
        return df.reset_index(drop=True), report

    df_work = df.copy()
    sort_cols = [c for c in df_work.columns if c != pk_col]
    seen_ids: set[str] = set(df_work[pk_col].astype("string").tolist())
    rows_to_drop: list[int] = []
    remap_index: list[int] = []
    remap_values: list[str] = []
    affected_examples: list[str] = []

    for uid, group in df_work.groupby(pk_col, sort=True):
        if len(group) <= 1:
            continue

        deduped = group.drop_duplicates(keep="first")
        report["n_identical_duplicate_rows_removed"] += len(group) - len(deduped)
        rows_to_drop.extend(set(group.index) - set(deduped.index))

        if len(deduped) <= 1:
            continue

        # Deterministic order: all non-pk columns ascending, then original
        # row index as a stable tiebreaker. The first row in this order keeps
        # the original usage_id; the rest get -rs-NNN suffixes.
        ordered = (
            deduped.assign(_orig_index=deduped.index)
            .sort_values(by=sort_cols + ["_orig_index"], kind="mergesort", na_position="last")
        )
        ordered_idx = ordered.index.tolist()

        report["n_usage_ids_affected"] += 1
        if len(affected_examples) < 5:
            affected_examples.append(str(uid))

        suffix = 1
        for row_idx in ordered_idx[1:]:
            while True:
                new_id = f"{uid}-rs-{suffix:03d}"
                suffix += 1
                if new_id not in seen_ids:
                    seen_ids.add(new_id)
                    break
            remap_index.append(row_idx)
            remap_values.append(new_id)
            report["n_rows_remapped_to_new_usage_id"] += 1

    # Remap conflicting rows before dropping identical duplicates so row labels stay valid.
    if remap_index:
        df_work.loc[remap_index, pk_col] = remap_values

    if rows_to_drop:
        df_work = df_work.drop(index=sorted(set(rows_to_drop)))

    df_work = df_work.reset_index(drop=True)

    if affected_examples:
        report["example_original_usage_ids"] = affected_examples

    return df_work, report


def print_report(reports: Iterable[dict]) -> None:
    """Pretty-print a list of validation reports to stdout."""
    print("\nData quality report")
    print("-" * 60)
    for report in reports:
        problem_keys = [k for k in report if k.startswith("n_")]
        problems = sum(
            int(report[k]) for k in problem_keys if isinstance(report[k], (int, float))
        )
        status = "OK   " if problems == 0 else "WARN "
        details = ", ".join(
            f"{k}={v}" for k, v in report.items() if k not in {"table", "check"}
        )
        print(f"  [{status}] {report['table']:<20} {report['check']:<28} {details}")
    print()
