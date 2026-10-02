"""Generate deterministic CFO-planning datasets for the example notebooks.

Run from the repository root:
    python examples/generate_cfo_datasets.py

The data are intentionally synthetic.  Channel names describe business models,
not measured benchmarks, and every output is reproducible without a random seed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent / "data"
MAX_AGE = 365


def curve_rows(specs: pd.DataFrame, *, model: str) -> pd.DataFrame:
    """Expand compact channel assumptions into canonical Theseus curve rows."""

    rows: list[dict[str, object]] = []
    ages = np.arange(MAX_AGE + 1)
    for spec in specs.itertuples(index=False):
        if model == "game":
            retention = spec.retention_floor + (1 - spec.retention_floor) * np.exp(
                -ages / spec.retention_decay_days
            )
            components = [
                ("retention", "activity", retention, "per_original_user", ""),
                (
                    "iap_revenue",
                    "revenue",
                    np.full_like(ages, spec.iap_per_active_user_day, dtype=float),
                    "per_active_user",
                    "retention",
                ),
                (
                    "ad_revenue",
                    "revenue",
                    np.full_like(ages, spec.ads_per_active_user_day, dtype=float),
                    "per_active_user",
                    "retention",
                ),
                (
                    "liveops_cost",
                    "cost",
                    np.full_like(ages, spec.variable_cost_per_active_user_day, dtype=float),
                    "per_active_user",
                    "retention",
                ),
            ]
        else:
            retention = np.exp(-ages / spec.retention_decay_days)
            components = [
                ("retention", "activity", retention, "per_original_user", ""),
                (
                    "subscription_revenue",
                    "revenue",
                    np.full_like(ages, spec.revenue_per_active_user_day, dtype=float),
                    "per_active_user",
                    "retention",
                ),
                (
                    "payment_fees",
                    "cost",
                    np.full_like(ages, spec.payment_cost_per_active_user_day, dtype=float),
                    "per_active_user",
                    "retention",
                ),
            ]
        for component, category, values, value_basis, driver in components:
            for age, value in zip(ages, values):
                rows.append(
                    {
                        "curve_id": spec.curve_id,
                        "age": age,
                        "component": component,
                        "category": category,
                        "value": value,
                        "value_basis": value_basis,
                        "driver_component": driver,
                        "curve_version": 1,
                    }
                )
    return pd.DataFrame(rows)


def write_game_dataset() -> None:
    destination = ROOT / "game"
    destination.mkdir(parents=True, exist_ok=True)
    channels = pd.DataFrame(
        [
            {
                "channel": "paid_social",
                "curve_id": "game_paid_social",
                "cpi": 2.40,
                "max_weekly_spend": 45000,
                "retention_floor": 0.009,
                "retention_decay_days": 11,
                "iap_per_active_user_day": 0.205,
                "ads_per_active_user_day": 0.055,
                "variable_cost_per_active_user_day": 0.012,
            },
            {
                "channel": "ad_network",
                "curve_id": "game_ad_network",
                "cpi": 1.45,
                "max_weekly_spend": 30000,
                "retention_floor": 0.006,
                "retention_decay_days": 8,
                "iap_per_active_user_day": 0.125,
                "ads_per_active_user_day": 0.090,
                "variable_cost_per_active_user_day": 0.011,
            },
            {
                "channel": "search",
                "curve_id": "game_search",
                "cpi": 2.85,
                "max_weekly_spend": 25000,
                "retention_floor": 0.015,
                "retention_decay_days": 17,
                "iap_per_active_user_day": 0.255,
                "ads_per_active_user_day": 0.040,
                "variable_cost_per_active_user_day": 0.013,
            },
        ]
    )
    curves = curve_rows(channels, model="game")

    cohorts: list[dict[str, object]] = []
    spend: list[dict[str, object]] = []
    for week, day in enumerate(range(0, 26 * 7, 7)):
        for channel in channels.itertuples(index=False):
            weekly_spend = {
                "paid_social": 18000 + 500 * min(week, 12),
                "ad_network": 10000 + 250 * min(week, 8),
                "search": 8000 + 300 * min(week, 10),
            }[channel.channel]
            cohort_id = f"{channel.channel}-w{week:02d}"
            cohorts.append(
                {
                    "cohort_id": cohort_id,
                    "acquisition_period": day,
                    "population": weekly_spend / channel.cpi,
                    "curve_id": channel.curve_id,
                    "channel": channel.channel,
                    "week": week,
                }
            )
            spend.append(
                {
                    "period": day,
                    "cohort_id": cohort_id,
                    "amount": weekly_spend,
                    "channel": channel.channel,
                }
            )

    cash_assumptions = pd.DataFrame(
        [
            {"assumption": "starting_cash", "value": 400000},
            {"assumption": "minimum_cash", "value": 300000},
            {"assumption": "target_cash", "value": 1000000},
            {"assumption": "daily_non_marketing_cash_flow", "value": -350},
            {"assumption": "planning_weeks", "value": 26},
            {"assumption": "forecast_days", "value": 366},
        ]
    )

    channels.to_csv(destination / "channel_assumptions.csv", index=False)
    curves.to_csv(destination / "curves.csv", index=False)
    pd.DataFrame(cohorts).to_csv(destination / "cohorts.csv", index=False)
    pd.DataFrame(spend).to_csv(destination / "acquisition_spend.csv", index=False)
    cash_assumptions.to_csv(destination / "cash_assumptions.csv", index=False)


def subscription_specs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Established acquisition sources.
            ("paid_search", "sub_paid_search", "established", 58, 265, 0.62, 0.019),
            ("affiliate", "sub_affiliate", "established", 48, 225, 0.58, 0.018),
            # Pre-test underwriting curves.
            ("podcast", "sub_podcast_prior", "prior", 62, 240, 0.59, 0.019),
            ("display", "sub_display_prior", "prior", 46, 205, 0.56, 0.018),
            ("ctv", "sub_ctv_prior", "prior", 88, 235, 0.59, 0.019),
            # What the synthetic experiment eventually reveals.
            ("podcast", "sub_podcast_actual", "actual", 58, 345, 0.66, 0.020),
            ("display", "sub_display_actual", "actual", 52, 82, 0.48, 0.017),
            ("ctv", "sub_ctv_actual", "actual", 105, 175, 0.53, 0.018),
            # Curves used for cohorts acquired while the CTV halo is active.
            ("paid_search", "sub_paid_search_halo", "halo", 58, 318, 0.680, 0.019),
            ("affiliate", "sub_affiliate_halo", "halo", 48, 270, 0.640, 0.018),
            ("podcast", "sub_podcast_halo", "halo", 58, 414, 0.720, 0.020),
        ],
        columns=[
            "channel",
            "curve_id",
            "curve_role",
            "cac",
            "retention_decay_days",
            "revenue_per_active_user_day",
            "payment_cost_per_active_user_day",
        ],
    )


def write_subscription_dataset() -> None:
    destination = ROOT / "subscription"
    destination.mkdir(parents=True, exist_ok=True)
    specs = subscription_specs()
    curves = curve_rows(specs, model="subscription")
    ctv_launch_day = 56
    as_of = 111

    curve_lookup = specs.set_index("curve_id")
    base_curve = {
        "paid_search": "sub_paid_search",
        "affiliate": "sub_affiliate",
        "podcast": "sub_podcast_prior",
        "display": "sub_display_prior",
        "ctv": "sub_ctv_prior",
    }
    actual_curve = {
        "paid_search": "sub_paid_search",
        "affiliate": "sub_affiliate",
        "podcast": "sub_podcast_actual",
        "display": "sub_display_actual",
        "ctv": "sub_ctv_actual",
    }
    cohorts: list[dict[str, object]] = []
    spend: list[dict[str, object]] = []
    experiment_weeks = set(range(8, 12))
    weekly_spend = {"paid_search": 15000, "affiliate": 9000}

    for week, day in enumerate(range(0, 16 * 7, 7)):
        channels = ["paid_search", "affiliate"]
        if week in experiment_weeks:
            channels += ["podcast", "display", "ctv"]
        for channel in channels:
            amount = weekly_spend[channel] if channel in weekly_spend else {
                "podcast": 9000,
                "display": 9000,
                "ctv": 14000,
            }[channel]
            curve_id = base_curve[channel]
            cac = float(curve_lookup.loc[curve_id, "cac"])
            cohort_id = f"{channel}-w{week:02d}"
            cohorts.append(
                {
                    "cohort_id": cohort_id,
                    "acquisition_period": day,
                    "population": amount / cac,
                    "curve_id": curve_id,
                    "channel": channel,
                    "week": week,
                    "stage": "experiment" if channel in {"podcast", "display", "ctv"} else "established",
                }
            )
            spend.append(
                {
                    "period": day,
                    "cohort_id": cohort_id,
                    "amount": amount,
                    "channel": channel,
                }
            )

    cohort_frame = pd.DataFrame(cohorts)
    observations: list[dict[str, object]] = []
    for cohort in cohort_frame.itertuples(index=False):
        actual = curve_lookup.loc[actual_curve[cohort.channel]]
        for period in range(int(cohort.acquisition_period), as_of + 1):
            age = period - int(cohort.acquisition_period)
            retention = float(np.exp(-age / actual.retention_decay_days))
            halo_active = cohort.channel in {"paid_search", "affiliate"} and period >= ctv_launch_day
            if halo_active:
                retention *= 1.12
            retention = min(retention, 1.0)
            monetization = float(actual.revenue_per_active_user_day)
            if halo_active:
                monetization *= 1.08
            # Smooth deterministic measurement variation; no random state is involved.
            variation = 1 + 0.012 * np.sin(period * 0.31 + cohort.week * 0.7)
            active = float(cohort.population) * retention
            observations.extend(
                [
                    {
                        "cohort_id": cohort.cohort_id,
                        "period": period,
                        "component": "retention",
                        "category": "activity",
                        "amount": active,
                    },
                    {
                        "cohort_id": cohort.cohort_id,
                        "period": period,
                        "component": "subscription_revenue",
                        "category": "revenue",
                        "amount": active * monetization * variation,
                    },
                    {
                        "cohort_id": cohort.cohort_id,
                        "period": period,
                        "component": "payment_fees",
                        "category": "cost",
                        "amount": active * float(actual.payment_cost_per_active_user_day),
                    },
                ]
            )

    channel_assumptions = pd.DataFrame(
        [
            {
                "channel": "paid_search",
                "decision": "maintain",
                "prior_curve_id": "sub_paid_search",
                "actual_curve_id": "sub_paid_search",
                "max_weekly_spend": 22000,
            },
            {
                "channel": "affiliate",
                "decision": "maintain",
                "prior_curve_id": "sub_affiliate",
                "actual_curve_id": "sub_affiliate",
                "max_weekly_spend": 15000,
            },
            {
                "channel": "podcast",
                "decision": "scale_winner",
                "prior_curve_id": "sub_podcast_prior",
                "actual_curve_id": "sub_podcast_actual",
                "max_weekly_spend": 50000,
            },
            {
                "channel": "display",
                "decision": "stop_loser",
                "prior_curve_id": "sub_display_prior",
                "actual_curve_id": "sub_display_actual",
                "max_weekly_spend": 0,
            },
            {
                "channel": "ctv",
                "decision": "measure_incrementality",
                "prior_curve_id": "sub_ctv_prior",
                "actual_curve_id": "sub_ctv_actual",
                "max_weekly_spend": 18000,
            },
        ]
    )
    scenario_assumptions = pd.DataFrame(
        [
            {"assumption": "as_of", "value": as_of},
            {"assumption": "forecast_end", "value": 365},
            {"assumption": "ctv_launch_day", "value": ctv_launch_day},
            {"assumption": "starting_cash", "value": 750000},
            {"assumption": "daily_non_marketing_cash_flow", "value": -500},
            {"assumption": "future_new_channel_budget", "value": 650000},
            {"assumption": "future_planning_weeks", "value": 20},
        ]
    )
    campaign_response_assumptions = pd.DataFrame(
        [
            {
                "channel": "paid_search",
                "curve_id": "sub_paid_search",
                "max_weekly_spend": 80000,
                "min_active_spend": 5000,
                "saturation_subscribers": 1700,
            },
            {
                "channel": "affiliate",
                "curve_id": "sub_affiliate",
                "max_weekly_spend": 50000,
                "min_active_spend": 5000,
                "saturation_subscribers": 1100,
            },
            {
                "channel": "podcast",
                "curve_id": "sub_podcast_actual",
                "max_weekly_spend": 90000,
                "min_active_spend": 5000,
                "saturation_subscribers": 1500,
            },
            {
                "channel": "display",
                "curve_id": "sub_display_actual",
                "max_weekly_spend": 50000,
                "min_active_spend": 5000,
                "saturation_subscribers": 1200,
            },
            {
                "channel": "ctv",
                "curve_id": "sub_ctv_actual",
                "max_weekly_spend": 60000,
                "min_active_spend": 5000,
                "saturation_subscribers": 900,
            },
        ]
    )

    specs.to_csv(destination / "curve_assumptions.csv", index=False)
    curves.to_csv(destination / "curves.csv", index=False)
    cohort_frame.to_csv(destination / "cohorts.csv", index=False)
    pd.DataFrame(spend).to_csv(destination / "acquisition_spend.csv", index=False)
    pd.DataFrame(observations).to_csv(destination / "observations.csv", index=False)
    channel_assumptions.to_csv(destination / "channel_assumptions.csv", index=False)
    scenario_assumptions.to_csv(destination / "scenario_assumptions.csv", index=False)
    campaign_response_assumptions.to_csv(
        destination / "campaign_response_assumptions.csv", index=False
    )


def main() -> None:
    write_game_dataset()
    write_subscription_dataset()
    print(f"Wrote CFO scenario datasets to {ROOT}")


if __name__ == "__main__":
    main()
