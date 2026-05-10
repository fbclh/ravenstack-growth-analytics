"""Build the five cleaned dimension / fact tables from the raw CSVs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ravenstack import cleaning, validation
from ravenstack.config import RAW_FILES


def _read_raw(raw_dir: Path, key: str) -> pd.DataFrame:
    return pd.read_csv(raw_dir / RAW_FILES[key])


def build_dim_accounts(raw_dir: Path) -> tuple[pd.DataFrame, list[dict]]:
    df = _read_raw(raw_dir, "accounts").copy()

    df["account_id"] = cleaning.standardize_text(df["account_id"], case=None)
    df["account_name"] = cleaning.standardize_text(df["account_name"], case=None)
    df["industry"] = cleaning.standardize_text(df["industry"], case="title")
    df["country"] = cleaning.standardize_text(df["country"], case="upper")
    df["referral_source"] = cleaning.standardize_text(df["referral_source"], case="lower")
    df["plan_tier"] = cleaning.standardize_text(df["plan_tier"], case="title")
    df["is_trial"] = cleaning.standardize_bool(df["is_trial"])
    df["churn_flag"] = cleaning.standardize_bool(df["churn_flag"])

    df["signup_date"] = cleaning.parse_date(df["signup_date"])
    df["signup_year"] = df["signup_date"].dt.year.astype("Int64")
    df["signup_month"] = df["signup_date"].dt.to_period("M").astype("string")

    reports = [validation.check_duplicate_pks(df, "account_id", "dim_accounts")]
    df = df.drop_duplicates(subset=["account_id"]).reset_index(drop=True)
    return df, reports


def build_fact_subscriptions(
    raw_dir: Path, dim_accounts: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    df = _read_raw(raw_dir, "subscriptions").copy()

    df["subscription_id"] = cleaning.standardize_text(df["subscription_id"], case=None)
    df["account_id"] = cleaning.standardize_text(df["account_id"], case=None)
    df["plan_tier"] = cleaning.standardize_text(df["plan_tier"], case="title")
    df["billing_frequency"] = cleaning.standardize_text(df["billing_frequency"], case="lower")

    for col in ["is_trial", "upgrade_flag", "downgrade_flag", "churn_flag", "auto_renew_flag"]:
        df[col] = cleaning.standardize_bool(df[col])

    df["start_date"] = cleaning.parse_date(df["start_date"])
    df["end_date"] = cleaning.parse_date(df["end_date"])

    df["is_active"] = df["end_date"].isna()
    df["subscription_length_days"] = (df["end_date"] - df["start_date"]).dt.days.astype("Int64")

    reports = [
        validation.check_duplicate_pks(df, "subscription_id", "fact_subscriptions"),
        validation.check_missing_fks(
            df, "account_id", dim_accounts["account_id"], "fact_subscriptions"
        ),
        validation.check_date_order(df, "start_date", "end_date", "fact_subscriptions"),
    ]
    df = df.drop_duplicates(subset=["subscription_id"]).reset_index(drop=True)
    return df, reports


def build_fact_feature_usage(
    raw_dir: Path, fact_subscriptions: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    df = _read_raw(raw_dir, "feature_usage").copy()

    df["usage_id"] = cleaning.standardize_text(df["usage_id"], case=None)
    df["subscription_id"] = cleaning.standardize_text(df["subscription_id"], case=None)
    df["feature_name"] = cleaning.standardize_text(df["feature_name"], case="lower")
    df["is_beta_feature"] = cleaning.standardize_bool(df["is_beta_feature"])

    df["usage_date"] = cleaning.parse_date(df["usage_date"])

    safe_usage = df["usage_count"].where(df["usage_count"] > 0)
    df["error_rate"] = (df["error_count"] / safe_usage).round(4)

    df, resolution_report = validation.resolve_usage_id_duplicates(df, "usage_id")

    reports = [
        resolution_report,
        validation.check_duplicate_pks(df, "usage_id", "fact_feature_usage"),
        validation.check_missing_fks(
            df, "subscription_id", fact_subscriptions["subscription_id"], "fact_feature_usage"
        ),
    ]
    return df, reports


def build_fact_support_tickets(
    raw_dir: Path, dim_accounts: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    df = _read_raw(raw_dir, "support_tickets").copy()

    df["ticket_id"] = cleaning.standardize_text(df["ticket_id"], case=None)
    df["account_id"] = cleaning.standardize_text(df["account_id"], case=None)
    df["priority"] = cleaning.standardize_text(df["priority"], case="lower")
    df["escalation_flag"] = cleaning.standardize_bool(df["escalation_flag"])

    df["submitted_at"] = cleaning.parse_datetime(df["submitted_at"])
    df["closed_at"] = cleaning.parse_datetime(df["closed_at"])
    df["submitted_date"] = df["submitted_at"].dt.normalize()

    reports = [
        validation.check_duplicate_pks(df, "ticket_id", "fact_support_tickets"),
        validation.check_missing_fks(
            df, "account_id", dim_accounts["account_id"], "fact_support_tickets"
        ),
        validation.check_date_order(df, "submitted_at", "closed_at", "fact_support_tickets"),
    ]
    df = df.drop_duplicates(subset=["ticket_id"]).reset_index(drop=True)
    return df, reports


def build_fact_churn_events(
    raw_dir: Path, dim_accounts: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict]]:
    df = _read_raw(raw_dir, "churn_events").copy()

    df["churn_event_id"] = cleaning.standardize_text(df["churn_event_id"], case=None)
    df["account_id"] = cleaning.standardize_text(df["account_id"], case=None)
    df["reason_code"] = cleaning.standardize_text(df["reason_code"], case="lower")
    df["feedback_text"] = cleaning.standardize_text(df["feedback_text"], case=None, fill="")

    for col in ["preceding_upgrade_flag", "preceding_downgrade_flag", "is_reactivation"]:
        df[col] = cleaning.standardize_bool(df[col])

    df["churn_date"] = cleaning.parse_date(df["churn_date"])

    reports = [
        validation.check_duplicate_pks(df, "churn_event_id", "fact_churn_events"),
        validation.check_missing_fks(
            df, "account_id", dim_accounts["account_id"], "fact_churn_events"
        ),
    ]
    df = df.drop_duplicates(subset=["churn_event_id"]).reset_index(drop=True)
    return df, reports


def build_base_tables(raw_dir: Path) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """Build every base table and return them along with a flat list of reports."""
    reports: list[dict] = []

    dim_accounts, r = build_dim_accounts(raw_dir)
    reports.extend(r)

    fact_subscriptions, r = build_fact_subscriptions(raw_dir, dim_accounts)
    reports.extend(r)

    fact_feature_usage, r = build_fact_feature_usage(raw_dir, fact_subscriptions)
    reports.extend(r)

    fact_support_tickets, r = build_fact_support_tickets(raw_dir, dim_accounts)
    reports.extend(r)

    fact_churn_events, r = build_fact_churn_events(raw_dir, dim_accounts)
    reports.extend(r)

    tables = {
        "dim_accounts": dim_accounts,
        "fact_subscriptions": fact_subscriptions,
        "fact_feature_usage": fact_feature_usage,
        "fact_support_tickets": fact_support_tickets,
        "fact_churn_events": fact_churn_events,
    }
    return tables, reports
