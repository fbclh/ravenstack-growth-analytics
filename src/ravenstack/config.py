"""Project paths and shared constants."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"

RAW_FILES: dict[str, str] = {
    "accounts": "ravenstack_accounts.csv",
    "subscriptions": "ravenstack_subscriptions.csv",
    "feature_usage": "ravenstack_feature_usage.csv",
    "support_tickets": "ravenstack_support_tickets.csv",
    "churn_events": "ravenstack_churn_events.csv",
}

PROCESSED_FILES: dict[str, str] = {
    "dim_accounts": "dim_accounts.csv",
    "fact_subscriptions": "fact_subscriptions.csv",
    "fact_feature_usage": "fact_feature_usage.csv",
    "fact_support_tickets": "fact_support_tickets.csv",
    "fact_churn_events": "fact_churn_events.csv",
    "account_health_summary": "account_health_summary.csv",
    "monthly_revenue_summary": "monthly_revenue_summary.csv",
    "feature_adoption_summary": "feature_adoption_summary.csv",
    "support_summary_by_account": "support_summary_by_account.csv",
    "cohort_retention_table": "cohort_retention_table.csv",
}
