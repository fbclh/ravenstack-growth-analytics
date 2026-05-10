"""Build the analytics-ready summary tables consumed by Power BI."""

from __future__ import annotations

import pandas as pd


def build_account_health_summary(
    dim_accounts: pd.DataFrame,
    fact_subscriptions: pd.DataFrame,
    fact_feature_usage: pd.DataFrame,
    fact_support_tickets: pd.DataFrame,
    fact_churn_events: pd.DataFrame,
) -> pd.DataFrame:
    """One row per account with a snapshot of revenue, usage and support."""
    subs_agg = (
        fact_subscriptions.groupby("account_id")
        .agg(
            subscription_count=("subscription_id", "nunique"),
            active_subscription_count=("is_active", "sum"),
            total_mrr=("mrr_amount", "sum"),
            total_arr=("arr_amount", "sum"),
            latest_plan_tier=("plan_tier", "last"),
        )
        .reset_index()
    )

    usage_by_account = (
        fact_feature_usage.merge(
            fact_subscriptions[["subscription_id", "account_id"]],
            on="subscription_id",
            how="left",
        )
        .groupby("account_id")
        .agg(
            total_usage_events=("usage_id", "nunique"),
            total_usage_count=("usage_count", "sum"),
            total_usage_duration_secs=("usage_duration_secs", "sum"),
            distinct_features_used=("feature_name", "nunique"),
            total_usage_errors=("error_count", "sum"),
        )
        .reset_index()
    )

    tickets_agg = (
        fact_support_tickets.groupby("account_id")
        .agg(
            ticket_count=("ticket_id", "nunique"),
            avg_satisfaction_score=("satisfaction_score", "mean"),
            avg_resolution_time_hours=("resolution_time_hours", "mean"),
            escalation_count=("escalation_flag", "sum"),
        )
        .reset_index()
    )

    churn_agg = (
        fact_churn_events.groupby("account_id")
        .agg(
            churn_event_count=("churn_event_id", "nunique"),
            total_refund_amount_usd=("refund_amount_usd", "sum"),
            last_churn_date=("churn_date", "max"),
        )
        .reset_index()
    )

    summary = (
        dim_accounts.merge(subs_agg, on="account_id", how="left")
        .merge(usage_by_account, on="account_id", how="left")
        .merge(tickets_agg, on="account_id", how="left")
        .merge(churn_agg, on="account_id", how="left")
    )

    count_cols = [
        "subscription_count",
        "active_subscription_count",
        "total_usage_events",
        "total_usage_count",
        "total_usage_duration_secs",
        "distinct_features_used",
        "total_usage_errors",
        "ticket_count",
        "escalation_count",
        "churn_event_count",
    ]
    for col in count_cols:
        summary[col] = summary[col].fillna(0).astype("Int64")

    money_cols = ["total_mrr", "total_arr", "total_refund_amount_usd"]
    for col in money_cols:
        summary[col] = summary[col].fillna(0).round(2)

    summary["avg_satisfaction_score"] = summary["avg_satisfaction_score"].round(2)
    summary["avg_resolution_time_hours"] = summary["avg_resolution_time_hours"].round(2)

    # Simple, transparent 0-100 health score combining activity, satisfaction
    # and churn signals. Tunable from Power BI later if needed.
    usage_score = (
        summary["distinct_features_used"].astype(float)
        / summary["distinct_features_used"].max().clip(min=1)
        * 50
    )
    satisfaction_score = summary["avg_satisfaction_score"].fillna(3.0) / 5.0 * 30
    churn_penalty = summary["churn_event_count"].astype(float) * 10
    summary["health_score"] = (usage_score + satisfaction_score - churn_penalty).clip(0, 100).round(1)

    return summary


def build_monthly_revenue_summary(fact_subscriptions: pd.DataFrame) -> pd.DataFrame:
    """Monthly MRR / ARR roll-up plus new and churned subscription counts."""
    subs = fact_subscriptions.copy()
    subs["start_month"] = subs["start_date"].dt.to_period("M")
    subs["end_month"] = subs["end_date"].dt.to_period("M")

    earliest = subs["start_month"].min()
    latest_end = subs["end_month"].max()
    latest_start = subs["start_month"].max()
    latest = max(filter(pd.notna, [latest_end, latest_start]))
    months = pd.period_range(start=earliest, end=latest, freq="M")

    rows: list[dict] = []
    for month in months:
        month_start = month.to_timestamp(how="start")
        month_end = month.to_timestamp(how="end")
        active_mask = (subs["start_date"] <= month_end) & (
            subs["end_date"].isna() | (subs["end_date"] >= month_start)
        )
        new_mask = subs["start_month"] == month
        churned_mask = subs["end_month"] == month

        active = subs.loc[active_mask]
        new_subs = subs.loc[new_mask]
        churned_subs = subs.loc[churned_mask]

        rows.append(
            {
                "year_month": str(month),
                "active_subscriptions": int(active_mask.sum()),
                "active_mrr": round(float(active["mrr_amount"].sum()), 2),
                "active_arr": round(float(active["arr_amount"].sum()), 2),
                "new_subscriptions": int(new_mask.sum()),
                "new_mrr": round(float(new_subs["mrr_amount"].sum()), 2),
                "churned_subscriptions": int(churned_mask.sum()),
                "churned_mrr": round(float(churned_subs["mrr_amount"].sum()), 2),
            }
        )

    df = pd.DataFrame(rows)
    df["net_new_mrr"] = (df["new_mrr"] - df["churned_mrr"]).round(2)
    return df


def build_feature_adoption_summary(
    fact_feature_usage: pd.DataFrame,
    fact_subscriptions: pd.DataFrame,
) -> pd.DataFrame:
    """One row per feature with usage volume and reach metrics."""
    usage = fact_feature_usage.merge(
        fact_subscriptions[["subscription_id", "account_id"]],
        on="subscription_id",
        how="left",
    )

    summary = (
        usage.groupby("feature_name")
        .agg(
            total_usage_events=("usage_id", "nunique"),
            total_usage_count=("usage_count", "sum"),
            total_duration_secs=("usage_duration_secs", "sum"),
            total_errors=("error_count", "sum"),
            unique_subscriptions=("subscription_id", "nunique"),
            unique_accounts=("account_id", "nunique"),
            is_beta_feature=("is_beta_feature", "max"),
        )
        .reset_index()
    )

    summary["avg_usage_per_event"] = (
        summary["total_usage_count"] / summary["total_usage_events"]
    ).round(2)
    summary["error_rate"] = (
        summary["total_errors"] / summary["total_usage_count"].where(summary["total_usage_count"] > 0)
    ).round(4)

    return summary.sort_values("total_usage_count", ascending=False).reset_index(drop=True)


def build_support_summary_by_account(
    fact_support_tickets: pd.DataFrame, dim_accounts: pd.DataFrame
) -> pd.DataFrame:
    """One row per account with support volume, response and quality metrics."""
    tickets = fact_support_tickets.copy()
    tickets["is_high"] = tickets["priority"].eq("high")
    tickets["is_urgent"] = tickets["priority"].eq("urgent")

    summary = (
        tickets.groupby("account_id")
        .agg(
            ticket_count=("ticket_id", "nunique"),
            avg_resolution_time_hours=("resolution_time_hours", "mean"),
            avg_first_response_time_minutes=("first_response_time_minutes", "mean"),
            avg_satisfaction_score=("satisfaction_score", "mean"),
            escalation_count=("escalation_flag", "sum"),
            high_priority_count=("is_high", "sum"),
            urgent_priority_count=("is_urgent", "sum"),
        )
        .reset_index()
    )

    summary = dim_accounts[["account_id"]].merge(summary, on="account_id", how="left")

    int_cols = [
        "ticket_count",
        "escalation_count",
        "high_priority_count",
        "urgent_priority_count",
    ]
    for col in int_cols:
        summary[col] = summary[col].fillna(0).astype("Int64")

    round_cols = [
        "avg_resolution_time_hours",
        "avg_first_response_time_minutes",
        "avg_satisfaction_score",
    ]
    for col in round_cols:
        summary[col] = summary[col].round(2)

    return summary


def build_cohort_retention_table(
    dim_accounts: pd.DataFrame, fact_subscriptions: pd.DataFrame
) -> pd.DataFrame:
    """Signup-cohort retention based on active subscriptions per calendar month.

    An account is considered "retained" in a given month if it has at least
    one subscription whose ``[start_date, end_date]`` window overlaps that
    month (``end_date`` null means still active).
    """
    accounts = dim_accounts[["account_id", "signup_date"]].copy()
    accounts["cohort_month"] = accounts["signup_date"].dt.to_period("M")

    cohort_sizes = (
        accounts.groupby("cohort_month").size().rename("cohort_size").reset_index()
    )

    subs = fact_subscriptions[["account_id", "start_date", "end_date"]].copy()
    earliest = accounts["cohort_month"].min().to_timestamp(how="start")
    latest_end = subs["end_date"].max()
    latest_start = subs["start_date"].max()
    latest_signup = accounts["signup_date"].max()
    latest = max(filter(pd.notna, [latest_end, latest_start, latest_signup]))
    months = pd.period_range(start=earliest, end=latest, freq="M")

    rows: list[dict] = []
    for month in months:
        month_start = month.to_timestamp(how="start")
        month_end = month.to_timestamp(how="end")
        active_mask = (subs["start_date"] <= month_end) & (
            subs["end_date"].isna() | (subs["end_date"] >= month_start)
        )
        active_accounts = subs.loc[active_mask, "account_id"].unique()
        for cohort_month, cohort_size in cohort_sizes.itertuples(index=False):
            if month < cohort_month:
                continue
            cohort_accounts = accounts.loc[
                accounts["cohort_month"] == cohort_month, "account_id"
            ]
            retained = cohort_accounts.isin(active_accounts).sum()
            rows.append(
                {
                    "cohort_month": str(cohort_month),
                    "activity_month": str(month),
                    "months_since_signup": (month - cohort_month).n,
                    "cohort_size": int(cohort_size),
                    "active_accounts": int(retained),
                    "retention_rate": round(retained / cohort_size, 4) if cohort_size else 0.0,
                }
            )

    return pd.DataFrame(rows)


def build_summaries(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Build every summary table from the already-cleaned base tables."""
    dim_accounts = tables["dim_accounts"]
    fact_subscriptions = tables["fact_subscriptions"]
    fact_feature_usage = tables["fact_feature_usage"]
    fact_support_tickets = tables["fact_support_tickets"]
    fact_churn_events = tables["fact_churn_events"]

    return {
        "account_health_summary": build_account_health_summary(
            dim_accounts,
            fact_subscriptions,
            fact_feature_usage,
            fact_support_tickets,
            fact_churn_events,
        ),
        "monthly_revenue_summary": build_monthly_revenue_summary(fact_subscriptions),
        "feature_adoption_summary": build_feature_adoption_summary(
            fact_feature_usage, fact_subscriptions
        ),
        "support_summary_by_account": build_support_summary_by_account(
            fact_support_tickets, dim_accounts
        ),
        "cohort_retention_table": build_cohort_retention_table(
            dim_accounts, fact_subscriptions
        ),
    }
