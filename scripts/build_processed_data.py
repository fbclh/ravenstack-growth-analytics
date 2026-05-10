"""Build the RavenStack processed data layer.

Reads the raw CSVs in ``data/raw/`` and writes a clean set of dimension,
fact and summary tables to ``data/processed/`` that are ready to be
imported into Power BI.

Run from the project root:

    python scripts/build_processed_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ravenstack.base_tables import build_base_tables
from ravenstack.config import PROCESSED_DIR, PROCESSED_FILES, RAW_DIR
from ravenstack.summaries import build_summaries
from ravenstack.validation import print_report


def main() -> None:
    if not RAW_DIR.exists():
        raise SystemExit(f"Raw data folder not found: {RAW_DIR}")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading raw CSVs from: {RAW_DIR}")
    base_tables, reports = build_base_tables(RAW_DIR)
    print_report(reports)

    repaired = next(
        (r for r in reports if r.get("check") == "usage_id_duplicate_resolution"),
        None,
    )
    if repaired and repaired.get("n_usage_ids_affected", 0):
        print(
            "  usage_id repair summary: "
            f"{repaired['n_usage_ids_affected']} usage_id values repaired, "
            f"{repaired['n_rows_remapped_to_new_usage_id']} rows reassigned, "
            f"{repaired['n_identical_duplicate_rows_removed']} identical duplicates removed."
        )

    summary_tables = build_summaries(base_tables)

    all_tables = {**base_tables, **summary_tables}

    print(f"Writing processed CSVs to: {PROCESSED_DIR}")
    for name, df in all_tables.items():
        filename = PROCESSED_FILES[name]
        out_path = PROCESSED_DIR / filename
        df.to_csv(out_path, index=False)
        print(f"  - {filename:<36} ({len(df):>6} rows, {len(df.columns):>2} cols)")

    print("\nDone. Processed layer is ready for Power BI.")


if __name__ == "__main__":
    main()
