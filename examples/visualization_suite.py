"""Generate the Theseus chart gallery from reproducible synthetic cohort data.

Run from the repository root:
    python -m examples.visualization_suite --output examples/output

Inspired by https://mobiledevmemo.com/ltv-roas-marketing-p-and-l/.
These are illustrative scenarios, not recovered data from the article.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import theseus_growth as tg


def campaign(*, acquisition_days=20, horizon=180, calendar=False):
    start = pd.Timestamp("2024-01-01") if calendar else 0

    def period(day):
        return start + pd.Timedelta(days=day) if calendar else day

    # Front-loaded revenue: base cumulative monetization is $1 after 90 days.
    cumulative = np.log1p(np.arange(1, horizon + 1)) / np.log1p(90)
    daily = np.diff(np.r_[0.0, cumulative])
    multipliers = [0.85, 1.0, 1.12, 1.24]
    curves = pd.DataFrame([
        {"curve_id": f"curve-{variant}", "age": age, "component": "revenue",
         "category": "revenue", "value": value * factor}
        for variant, factor in enumerate(multipliers)
        for age, value in enumerate(daily)
    ])
    cohorts = pd.DataFrame([
        {"cohort_id": f"Cohort {day + 1:02d}", "acquisition_period": period(day),
         "population": 1000, "curve_id": f"curve-{day % 4}"}
        for day in range(acquisition_days)
    ])
    spend = pd.DataFrame([
        {"period": period(day), "cohort_id": f"Cohort {day + 1:02d}", "amount": 1000.0}
        for day in range(acquisition_days)
    ])
    cursor = 35
    observations = pd.DataFrame([
        {"cohort_id": f"Cohort {day + 1:02d}", "period": period(day + age),
         "component": "revenue", "amount": 1000 * daily[age] * multipliers[day % 4]}
        for day in range(min(acquisition_days, cursor + 1))
        for age in range(cursor - day + 1)
    ])
    return tg.forecast(cohorts, curves, observations=observations,
                       acquisition_spend=spend, as_of=period(cursor), forecast_end=period(horizon - 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("examples/output"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = campaign()
    cohorts = [f"Cohort {day:02d}" for day in range(1, 5)]
    charts = {
        "cohort_progression_weekly": result.plot.cohort_progression(cohorts=cohorts, interval="weekly"),
        "cohort_progression_monthly": campaign(calendar=True).plot.cohort_progression(cohorts=cohorts, interval="monthly"),
        "cohort_progression_observed": result.plot.cohort_progression(cohorts=cohorts, interval="weekly", basis="observed"),
        "roas_heatmap": result.plot.roas_heatmap(interval="weekly"),
        "cumulative_monetization": result.plot.cumulative_monetization(cohorts=[cohorts[1]]),
        "daily_monetization": result.plot.daily_monetization(cohorts=[cohorts[1]]),
        "recorded_vs_projected": result.plot.recorded_vs_projected(cohorts=cohorts),
        "cohort_revenue": result.plot.cohort_revenue(),
        "revenue_vs_spend": result.plot.revenue_vs_spend(),
        "cumulative_revenue_vs_spend": result.plot.cumulative_revenue_vs_spend(),
        "marketing_pnl": result.plot.marketing_pnl(),
        "cumulative_pnl": result.plot.cumulative_pnl(),
        "projected_receivables": result.plot.projected_receivables(),
        "scenario_comparison": tg.viz.scenario_comparison({
            "20 days of acquisition": result,
            "Ongoing acquisition": campaign(acquisition_days=180),
        }),
        "dashboard": result.plot.dashboard(cohorts=cohorts),
    }
    for name, chart in charts.items():
        chart.save(args.output / f"{name}.png")
        chart.save(args.output / f"{name}.svg")
        chart.data.to_csv(args.output / f"{name}.csv", index=False)
    print(f"Wrote {len(charts)} charts (PNG, SVG, CSV) to {args.output.resolve()}")


if __name__ == "__main__":
    main()
