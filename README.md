# RavenStack Growth Analytics — Preprocessing Layer

RavenStack is a fictional B2B SaaS company. This repository contains the
preprocessing layer of an end-to-end Power BI portfolio project: it takes
five raw CSV exports and produces a clean, analytics-ready data layer that
Power BI can connect to directly.

> Scope of this stage: **raw CSVs → clean processed CSVs**. SQL,
> orchestration and the Power BI report itself come later.

## Project structure

```
ravenstack-growth-analytics/
├── data/
│   ├── raw/                       # source CSVs (versioned)
│   └── processed/                 # generated CSVs (regenerated from raw)
├── notebooks/                     # exploratory analysis (Jupyter)
├── powerbi/                       # .pbix file(s) and Power BI artifacts
├── assets/                        # screenshots, diagrams, GIFs for README
├── scripts/
│   └── build_processed_data.py    # single entry point
├── src/
│   └── ravenstack/
│       ├── __init__.py
│       ├── config.py              # paths and file names
│       ├── cleaning.py            # parse / standardize transforms
│       ├── validation.py          # PK / FK / date checks, duplicate repair, reporting
│       ├── base_tables.py         # dim/fact builders
│       └── summaries.py           # summary table builders
├── requirements.txt
├── .gitignore
└── README.md
```

## Raw inputs (`data/raw/`)

| File                              | Grain                              | Rows  |
| --------------------------------- | ---------------------------------- | ----- |
| `ravenstack_accounts.csv`         | one row per customer account       | 500   |
| `ravenstack_subscriptions.csv`    | one row per subscription           | 5,000 |
| `ravenstack_feature_usage.csv`    | one row per feature usage event    | 25,000|
| `ravenstack_support_tickets.csv`  | one row per support ticket         | 2,000 |
| `ravenstack_churn_events.csv`     | one row per churn / cancel event   | 600   |

## Processed outputs (`data/processed/`)

Base tables (one-to-one with the raw inputs, just cleaned):

- `dim_accounts.csv`
- `fact_subscriptions.csv`
- `fact_feature_usage.csv`
- `fact_support_tickets.csv`
- `fact_churn_events.csv`

Summary tables (denormalized aggregates for Power BI):

- `account_health_summary.csv` — one row per account with revenue, usage,
  support and churn KPIs, plus a simple 0–100 health score.
- `monthly_revenue_summary.csv` — monthly active MRR / ARR, new MRR,
  churned MRR and net new MRR.
- `feature_adoption_summary.csv` — usage volume and reach per feature.
- `support_summary_by_account.csv` — support volume, response time and
  satisfaction per account.
- `cohort_retention_table.csv` — signup-month cohort retention based on
  active subscriptions.

## Cleaning rules applied

Cleaning (`src/ravenstack/cleaning.py`):

- **Dates / datetimes** are parsed with `pd.to_datetime` and missing
  values are kept as `NaT`. Date-only columns are normalized to midnight.
- **Booleans** are coerced to nullable booleans, accepting common string
  variants (`"true"`, `"yes"`, `"1"`, etc.).
- **Text / category** columns are trimmed and case-normalized
  (`industry` → Title Case, `country` → UPPER, `plan_tier` → Title Case,
  everything else → lower case).

Validation (`src/ravenstack/validation.py`):

- **Duplicate primary keys** are detected per table.
- **Missing foreign keys** are detected for every `_id` that points at
  another table.
- **Invalid date ordering** is detected where it makes sense
  (`end_date >= start_date`, `closed_at >= submitted_at`).
- **`usage_id` duplicates** in `fact_feature_usage` are repaired
  deterministically: fully identical rows are collapsed; conflicting
  rows get a stable `{usage_id}-rs-NNN` suffix.

The data-quality report is printed to stdout each run.

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/build_processed_data.py
```

After the run, `data/processed/` will contain ten CSVs ready to be
imported into Power BI (Get Data → Folder, or one-by-one via Get Data →
Text/CSV).
