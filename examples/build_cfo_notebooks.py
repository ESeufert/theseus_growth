"""Build the two executed-source CFO scenario notebooks.

The generated notebooks are committed artifacts. Run this file only when their
source cells need to be regenerated; execute them separately to refresh outputs.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "examples" / "notebooks"


def notebook(cells: list, filename: str) -> None:
    document = nbf.v4.new_notebook()
    document["cells"] = cells
    document["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
    }
    DESTINATION.mkdir(parents=True, exist_ok=True)
    nbf.write(document, DESTINATION / filename)


def game_notebook() -> None:
    md = nbf.v4.new_markdown_cell
    code = nbf.v4.new_code_cell
    cells = [
        md(
            """# Game CFO lab: growth, liquidity, and a $1MM cash target

This notebook treats user acquisition as a capital-allocation problem for a synthetic IAP and ad-supported game. The CFO starts with **$400k**, protects a **$300k minimum bank balance**, and makes weekly channel decisions over 26 weeks.

Two constrained plans are solved:

1. Maximize active-player growth at day 181 while the bank balance never breaches the floor and the company ends the 365-day horizon above its starting cash.
2. Find the minimum acquisition spend needed to reach **$1MM in the bank by day 365**.

Theseus supplies the cohort cash-flow response for every channel. SciPy's linear optimizer selects the spend schedule. All inputs are deterministic synthetic assumptions, not market benchmarks.

### Start here and related reading

- [Theseus API introduction and walkthrough](../../Theseus_Walkthrough.ipynb)
- [Building a marketing P&L using LTV and ROAS](https://mobiledevmemo.com/ltv-roas-marketing-p-and-l/)
- [Optimization models in digital advertising](https://mobiledevmemo.com/optimization-models-in-digital-advertising/)"""
        ),
        code(
            """from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import display
from matplotlib.figure import Figure
from scipy.optimize import linprog

import theseus_growth as tg

%matplotlib inline
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda value: f"{value:,.2f}")

ROOT = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / "pyproject.toml").exists())
DATA = ROOT / "examples" / "data" / "game"

channels = pd.read_csv(DATA / "channel_assumptions.csv").set_index("channel")
curves = pd.read_csv(DATA / "curves.csv")
baseline_cohorts = pd.read_csv(DATA / "cohorts.csv")
baseline_spend = pd.read_csv(DATA / "acquisition_spend.csv")
assumptions = pd.read_csv(DATA / "cash_assumptions.csv").set_index("assumption")["value"]

STARTING_CASH = float(assumptions["starting_cash"])
MINIMUM_CASH = float(assumptions["minimum_cash"])
TARGET_CASH = float(assumptions["target_cash"])
DAILY_OPERATING_CASH_FLOW = float(assumptions["daily_non_marketing_cash_flow"])
PLANNING_WEEKS = int(assumptions["planning_weeks"])
FORECAST_END = int(assumptions["forecast_days"] - 1)
GROWTH_DAY = 181

display(channels)
display(pd.DataFrame({
    "starting_cash": [STARTING_CASH],
    "cash_floor": [MINIMUM_CASH],
    "cash_target": [TARGET_CASH],
    "daily_non_marketing_cash_flow": [DAILY_OPERATING_CASH_FLOW],
}))"""
        ),
        md(
            """## Turn Theseus curves into optimizer coefficients

The model is linear at a fixed CPI and curve: a $10,000 cohort has exactly 10,000 times the cash-flow response of a $1 cohort. We therefore ask Theseus to forecast one **$1 acquisition unit** per channel, then shift those daily responses to each possible acquisition week.

This retains the full cohort timing. The optimizer sees the upfront spend, delayed IAP and ad receipts, live-ops costs, retention, and channel capacity—not just a single LTV/CAC ratio."""
        ),
        code(
            """unit_cohorts, unit_spend = [], []
for channel, spec in channels.iterrows():
    unit_cohorts.append({
        "cohort_id": channel,
        "acquisition_period": 0,
        "population": 1 / spec["cpi"],
        "curve_id": spec["curve_id"],
        "channel": channel,
    })
    unit_spend.append({"period": 0, "cohort_id": channel, "amount": 1.0})

unit_result = tg.forecast(
    pd.DataFrame(unit_cohorts), curves,
    acquisition_spend=pd.DataFrame(unit_spend),
    as_of=0, forecast_end=FORECAST_END, start=0,
)

decision_rows, cumulative_columns, active_coefficients = [], [], []
for week, acquisition_day in enumerate(range(0, PLANNING_WEEKS * 7, 7)):
    for channel, spec in channels.iterrows():
        unit_rows = unit_result.contributions.query(
            "cohort_id == @channel and category != 'activity'"
        )
        daily_response = (
            unit_rows.groupby("age")["pnl_amount"].sum()
            .reindex(range(FORECAST_END + 1), fill_value=0).to_numpy(copy=True)
        )
        daily_response[0] -= 1.0  # acquisition spend at age zero
        shifted = np.zeros(FORECAST_END + 1)
        shifted[acquisition_day:] = daily_response[: FORECAST_END + 1 - acquisition_day]
        cumulative_columns.append(np.cumsum(shifted))

        active = unit_result.contributions.query(
            "cohort_id == @channel and component == 'retention'"
        ).set_index("age")["amount"]
        active_coefficients.append(float(active.get(GROWTH_DAY - acquisition_day, 0)))
        decision_rows.append({
            "channel": channel,
            "week": week,
            "period": acquisition_day,
            "max_spend": float(spec["max_weekly_spend"]),
        })

decisions = pd.DataFrame(decision_rows)
cumulative_response = np.column_stack(cumulative_columns)
active_coefficients = np.asarray(active_coefficients)
base_cash = STARTING_CASH + np.cumsum(
    np.repeat(DAILY_OPERATING_CASH_FLOW, FORECAST_END + 1)
)
bounds = list(zip(np.zeros(len(decisions)), decisions["max_spend"]))

unit_economics = []
for channel, spec in channels.iterrows():
    rows = unit_result.contributions.query("cohort_id == @channel")
    revenue = rows.loc[rows["category"].eq("revenue"), "amount"].sum()
    contribution = rows.loc[rows["category"].ne("activity"), "pnl_amount"].sum()
    unit_economics.append({
        "channel": channel,
        "CPI": spec["cpi"],
        "365d revenue / spend": revenue,
        "365d contribution / spend": contribution,
        "365d marketing profit / spend": contribution - 1,
    })
display(pd.DataFrame(unit_economics).set_index("channel"))"""
        ),
        md(
            """## Decision 1: maximize growth without risking the company

The objective is active players on day 181. There are two sets of constraints:

- Bank cash must stay at or above the floor on **every day**, not merely at quarter-end.
- Ending cash after fixed operating outflows must be at least the initial $400k, so growth is profitable within the modeled horizon.

Weekly channel limits stand in for inventory, audience size, and operational pacing."""
        ),
        code(
            """growth_A = np.vstack([-cumulative_response, -cumulative_response[-1]])
growth_b = np.r_[
    base_cash - MINIMUM_CASH,
    base_cash[-1] - STARTING_CASH,
]
growth_solution = linprog(
    c=-active_coefficients,
    A_ub=growth_A,
    b_ub=growth_b,
    bounds=bounds,
    method="highs",
)
assert growth_solution.success, growth_solution.message

growth_plan = decisions.copy()
growth_plan["spend"] = growth_solution.x
growth_cash_lp = base_cash + cumulative_response @ growth_solution.x

assert growth_cash_lp.min() >= MINIMUM_CASH - 0.01
assert growth_cash_lp[-1] >= STARTING_CASH - 0.01
display(growth_plan.pivot(index="week", columns="channel", values="spend").head(10))
print(f"Total acquisition spend: ${growth_plan['spend'].sum():,.0f}")
print(f"Active players on day {GROWTH_DAY}: {active_coefficients @ growth_solution.x:,.0f}")
print(f"Minimum bank balance: ${growth_cash_lp.min():,.0f}")
print(f"Ending bank balance: ${growth_cash_lp[-1]:,.0f}")"""
        ),
        code(
            """def forecast_plan(plan):
    cohort_rows, spend_rows = [], []
    for row in plan.loc[plan["spend"].gt(0.01)].itertuples(index=False):
        spec = channels.loc[row.channel]
        cohort_id = f"{row.channel}-w{int(row.week):02d}"
        cohort_rows.append({
            "cohort_id": cohort_id,
            "acquisition_period": int(row.period),
            "population": row.spend / spec["cpi"],
            "curve_id": spec["curve_id"],
            "channel": row.channel,
            "week": int(row.week),
        })
        spend_rows.append({
            "period": int(row.period), "cohort_id": cohort_id,
            "amount": row.spend, "channel": row.channel,
        })
    return tg.forecast(
        pd.DataFrame(cohort_rows), curves,
        acquisition_spend=pd.DataFrame(spend_rows),
        as_of=0, forecast_end=FORECAST_END, start=0,
    )


def bank_cash(result):
    timeline = result.timeline()
    operating = np.cumsum(np.repeat(DAILY_OPERATING_CASH_FLOW, len(timeline)))
    return STARTING_CASH + operating + timeline["cumulative_marketing_pnl"].to_numpy()


growth_result = forecast_plan(growth_plan)
growth_cash = bank_cash(growth_result)
np.testing.assert_allclose(growth_cash, growth_cash_lp, atol=0.01)

growth_figure = Figure(figsize=(14, 5), layout="constrained")
spend_ax, cash_ax = growth_figure.subplots(1, 2)
growth_plan.pivot(index="week", columns="channel", values="spend").plot(
    kind="bar", stacked=True, ax=spend_ax, title="Growth-maximizing weekly spend"
)
spend_ax.set(xlabel="Acquisition week", ylabel="Spend ($)")
cash_ax.plot(growth_cash, color="#2867B2", label="Bank balance")
cash_ax.axhline(MINIMUM_CASH, color="#B24A3B", linestyle="--", label="Cash floor")
cash_ax.set(title="Daily liquidity check", xlabel="Day", ylabel="Cash ($)")
cash_ax.legend()
cash_ax.grid(alpha=0.2)
display(growth_figure)"""
        ),
        md(
            """## Decision 2: reach $1MM with the least acquisition capital

Now the terminal cash target becomes a constraint and total acquisition spend becomes the objective to minimize. This is a useful goal-seek formulation: it answers how much capital—and which cohorts—are required to get from $400k to $1MM by day 365 without violating the same liquidity floor."""
        ),
        code(
            """target_A = np.vstack([-cumulative_response, -cumulative_response[-1]])
target_b = np.r_[
    base_cash - MINIMUM_CASH,
    base_cash[-1] - TARGET_CASH,
]
target_solution = linprog(
    c=np.ones(len(decisions)),
    A_ub=target_A,
    b_ub=target_b,
    bounds=bounds,
    method="highs",
)
assert target_solution.success, target_solution.message

target_plan = decisions.copy()
target_plan["spend"] = target_solution.x
target_result = forecast_plan(target_plan)
target_cash = bank_cash(target_result)

assert target_cash.min() >= MINIMUM_CASH - 0.01
assert target_cash[-1] >= TARGET_CASH - 0.01
print(f"Minimum acquisition spend required: ${target_plan['spend'].sum():,.0f}")
print(f"Minimum bank balance: ${target_cash.min():,.0f}")
print(f"Ending bank balance: ${target_cash[-1]:,.0f}")
display(
    target_plan.groupby("channel")["spend"].sum()
    .sort_values(ascending=False).rename("total_spend").to_frame()
)"""
        ),
        code(
            """baseline_result = tg.forecast(
    baseline_cohorts, curves, acquisition_spend=baseline_spend,
    as_of=0, forecast_end=FORECAST_END, start=0,
)


def scenario_row(name, result):
    cash = bank_cash(result)
    active = result.contributions.query(
        "component == 'retention' and period == @GROWTH_DAY"
    )["amount"].sum()
    return {
        "scenario": name,
        "acquisition_spend": result.acquisition_spend["amount"].sum(),
        "players_acquired": result.cohorts["population"].sum(),
        f"active_players_day_{GROWTH_DAY}": active,
        "minimum_cash": cash.min(),
        "ending_cash": cash[-1],
        "marketing_pnl": result.timeline()["marketing_pnl"].sum(),
    }


summary = pd.DataFrame([
    scenario_row("Current synthetic plan", baseline_result),
    scenario_row("Maximum growth", growth_result),
    scenario_row("$1MM target / minimum spend", target_result),
]).set_index("scenario")
display(summary)

comparison = tg.viz.scenario_comparison({
    "Current plan": baseline_result,
    "Maximum growth": growth_result,
    "$1MM target": target_result,
})
display(comparison.figure)"""
        ),
        md(
            """## CFO interpretation

- The growth solution spends up to channel capacity where the delayed cohort cash flows still preserve the daily liquidity covenant.
- The $1MM goal-seek favors the highest incremental cash return available within the deadline; a high LTV channel can dominate even when its CPI is higher.
- These are underwriting outputs, not causal estimates. Real use should refresh curves from observed cohorts and add diminishing returns, payment timing, taxes, payroll, platform settlement delays, and uncertainty bands.
- The constraints are explicit and inspectable. Change the floor, deadline, channel caps, or target and rerun the optimizer—no chart-specific logic needs to change."""
        ),
    ]
    notebook(cells, "Game_CFO_Cash_Flow_Optimization.ipynb")


def subscription_notebook() -> None:
    md = nbf.v4.new_markdown_cell
    code = nbf.v4.new_code_cell
    cells = [
        md(
            """# Subscription CFO lab: channel experiments, scaling, and the CTV halo

This synthetic subscription scenario begins with paid search and affiliate acquisition, then tests three unproven channels:

- **Podcast** performs materially better than its underwriting curve and can be scaled.
- **Display** retains poorly and destroys value, so it is stopped.
- **CTV** looks unattractive under direct attribution, but coincides with better retention and monetization across existing cohorts—a portfolio halo that direct ROAS misses.

The CFO uses Theseus to reconcile observations with the prior forecast, re-underwrite every cohort, optimize a fixed future acquisition budget, and compare direct-attribution and incrementality-aware cash plans.

### Start here and related reading

- [Theseus API introduction and walkthrough](../../Theseus_Walkthrough.ipynb)
- [Building a marketing P&L using LTV and ROAS](https://mobiledevmemo.com/ltv-roas-marketing-p-and-l/)
- [Optimization models in digital advertising](https://mobiledevmemo.com/optimization-models-in-digital-advertising/)
- [How to manage marketing spend during a recession](https://mobiledevmemo.com/how-to-manage-marketing-spend-during-a-recession/)
- [The power of cohort compounding](https://mobiledevmemo.com/podcast-the-power-of-cohort-compounding-with-nilay-patel/)"""
        ),
        code(
            """from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import display
from matplotlib.figure import Figure
from scipy.optimize import linprog

import theseus_growth as tg

%matplotlib inline
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda value: f"{value:,.2f}")

ROOT = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / "pyproject.toml").exists())
DATA = ROOT / "examples" / "data" / "subscription"

cohorts = pd.read_csv(DATA / "cohorts.csv")
curves = pd.read_csv(DATA / "curves.csv")
observations = pd.read_csv(DATA / "observations.csv")
acquisition_spend = pd.read_csv(DATA / "acquisition_spend.csv")
curve_assumptions = pd.read_csv(DATA / "curve_assumptions.csv")
channel_assumptions = pd.read_csv(DATA / "channel_assumptions.csv").set_index("channel")
scenario_assumptions = pd.read_csv(DATA / "scenario_assumptions.csv").set_index("assumption")["value"]

AS_OF = int(scenario_assumptions["as_of"])
FORECAST_END = int(scenario_assumptions["forecast_end"])
CTV_LAUNCH_DAY = int(scenario_assumptions["ctv_launch_day"])
STARTING_CASH = float(scenario_assumptions["starting_cash"])
DAILY_OPERATING_CASH_FLOW = float(scenario_assumptions["daily_non_marketing_cash_flow"])
FUTURE_BUDGET = float(scenario_assumptions["future_new_channel_budget"])
FUTURE_WEEKS = int(scenario_assumptions["future_planning_weeks"])

prior_result = tg.forecast(
    cohorts, curves, observations=observations,
    acquisition_spend=acquisition_spend,
    as_of=AS_OF, forecast_end=FORECAST_END, start=0,
)
display(channel_assumptions)
display(prior_result.metrics().T.rename(columns={0: "value"}))"""
        ),
        md(
            """## What did the experiments reveal?

Raw observed ROAS is maturity-biased: older cohorts have had more time to bill. For a fair underwriting comparison, the table below broadcasts one subscriber through each prior and actual curve for the same 365-day window and subtracts CAC.

The actual curves are the synthetic ground truth used to create the observation feed. In a real deployment they would be fitted or selected from measured cohort data."""
        ),
        code(
            """metric_cohorts, metric_spend = [], []
for row in curve_assumptions.itertuples(index=False):
    metric_cohorts.append({
        "cohort_id": row.curve_id,
        "acquisition_period": 0,
        "population": 1.0,
        "curve_id": row.curve_id,
        "channel": row.channel,
        "curve_role": row.curve_role,
    })
    metric_spend.append({"period": 0, "cohort_id": row.curve_id, "amount": row.cac})

metric_result = tg.forecast(
    pd.DataFrame(metric_cohorts), curves,
    acquisition_spend=pd.DataFrame(metric_spend),
    as_of=0, forecast_end=FORECAST_END, start=0,
)

curve_readout = []
for row in curve_assumptions.itertuples(index=False):
    ledger = metric_result.contributions.query("cohort_id == @row.curve_id")
    revenue = ledger.loc[ledger["category"].eq("revenue"), "amount"].sum()
    contribution = ledger.loc[ledger["category"].ne("activity"), "pnl_amount"].sum()
    curve_readout.append({
        "channel": row.channel,
        "curve_role": row.curve_role,
        "CAC": row.cac,
        "365d_revenue": revenue,
        "365d_ROAS": revenue / row.cac,
        "365d_marketing_profit_per_subscriber": contribution - row.cac,
    })
curve_readout = pd.DataFrame(curve_readout)
display(curve_readout.query("curve_role in ['prior', 'actual']").set_index(["channel", "curve_role"]))

assert curve_readout.query("channel == 'podcast' and curve_role == 'actual'")["365d_marketing_profit_per_subscriber"].iloc[0] > 0
assert curve_readout.query("channel == 'display' and curve_role == 'actual'")["365d_marketing_profit_per_subscriber"].iloc[0] < 0
assert curve_readout.query("channel == 'ctv' and curve_role == 'actual'")["365d_marketing_profit_per_subscriber"].iloc[0] < 0"""
        ),
        code(
            """experiment_ids = cohorts.loc[cohorts["stage"].eq("experiment"), "cohort_id"]
cohort_channels = cohorts.set_index("cohort_id")["channel"]

planned_revenue = (
    prior_result.projections.query(
        "cohort_id in @experiment_ids and period <= @AS_OF and category == 'revenue'"
    )
    .assign(channel=lambda frame: frame["cohort_id"].map(cohort_channels))
    .groupby("channel")["amount"].sum()
)
observed_revenue = (
    observations.query(
        "cohort_id in @experiment_ids and component == 'subscription_revenue'"
    )
    .assign(channel=lambda frame: frame["cohort_id"].map(cohort_channels))
    .groupby("channel")["amount"].sum()
)
test_variance = pd.concat([
    planned_revenue.rename("prior_revenue_to_date"),
    observed_revenue.rename("observed_revenue_to_date"),
], axis=1)
test_variance["variance"] = test_variance["observed_revenue_to_date"] / test_variance["prior_revenue_to_date"] - 1
display(test_variance)

variance_figure = Figure(figsize=(9, 4), layout="constrained")
variance_ax = variance_figure.subplots()
test_variance[["prior_revenue_to_date", "observed_revenue_to_date"]].plot(
    kind="bar", ax=variance_ax, title="Experiment revenue: prior vs observed"
)
variance_ax.set(ylabel="Revenue through current day", xlabel="Channel")
display(variance_figure)"""
        ),
        md(
            """## Optimize the next 20 weeks of new-channel spend

The CFO has a fixed **$650k** new-channel budget. Podcast capacity ramps from $15k per week as inventory and creative operations scale. Display is capped at zero after the failed test.

We solve two models:

1. **Direct attribution:** allocate strictly on each channel's own cohort economics.
2. **Incrementality-aware:** enumerate a CTV-on strategy with a $14k weekly test commitment, apply the measured halo to eligible cohorts, then allocate the remaining budget optimally.

The second formulation keeps CTV's direct cohort return separate from its portfolio effect."""
        ),
        code(
            """curve_spec = curve_assumptions.set_index("curve_id")
response_curve_ids = {
    "podcast_direct": "sub_podcast_actual",
    "podcast_halo": "sub_podcast_halo",
    "display": "sub_display_actual",
    "ctv": "sub_ctv_actual",
}

response_cohorts, response_spend = [], []
for label, curve_id in response_curve_ids.items():
    response_cohorts.append({
        "cohort_id": label, "acquisition_period": 0,
        "population": 1 / curve_spec.loc[curve_id, "cac"],
        "curve_id": curve_id,
    })
    response_spend.append({"period": 0, "cohort_id": label, "amount": 1.0})
response_result = tg.forecast(
    pd.DataFrame(response_cohorts), curves,
    acquisition_spend=pd.DataFrame(response_spend),
    as_of=0, forecast_end=FORECAST_END, start=0,
)

unit_cumulative_profit = {}
for label in response_curve_ids:
    daily = (
        response_result.contributions.query(
            "cohort_id == @label and category != 'activity'"
        )
        .groupby("age")["pnl_amount"].sum()
        .reindex(range(FORECAST_END + 1), fill_value=0).to_numpy(copy=True)
    )
    daily[0] -= 1.0
    unit_cumulative_profit[label] = np.cumsum(daily)


def solve_new_channel_plan(*, halo):
    rows = []
    for week in range(FUTURE_WEEKS):
        day = AS_OF + 1 + 7 * week
        for channel in ["podcast", "display", "ctv"]:
            response_label = "podcast_halo" if halo and channel == "podcast" else (
                "podcast_direct" if channel == "podcast" else channel
            )
            maximum = {
                "podcast": min(15000 + 2500 * week, 50000),
                "display": 0,
                "ctv": 18000,
            }[channel]
            minimum = 14000 if halo and channel == "ctv" else 0
            rows.append({
                "channel": channel, "week": week, "period": day,
                "minimum": minimum, "maximum": maximum,
                "terminal_profit_per_dollar": unit_cumulative_profit[response_label][FORECAST_END - day],
            })
    plan = pd.DataFrame(rows)
    solution = linprog(
        c=-plan["terminal_profit_per_dollar"],
        A_eq=np.ones((1, len(plan))), b_eq=[FUTURE_BUDGET],
        bounds=list(zip(plan["minimum"], plan["maximum"])),
        method="highs",
    )
    assert solution.success, solution.message
    plan["spend"] = solution.x
    return plan


direct_plan = solve_new_channel_plan(halo=False)
halo_plan = solve_new_channel_plan(halo=True)
allocation = pd.concat([
    direct_plan.groupby("channel")["spend"].sum().rename("direct_attribution"),
    halo_plan.groupby("channel")["spend"].sum().rename("halo_aware"),
], axis=1)
display(allocation)

assert direct_plan.groupby("channel")["spend"].sum()["podcast"] == FUTURE_BUDGET
assert direct_plan.groupby("channel")["spend"].sum()[["display", "ctv"]].sum() < 0.01
assert halo_plan.groupby("channel")["spend"].sum()["ctv"] >= 14000 * FUTURE_WEEKS - 0.01"""
        ),
        code(
            """def scoped_overrides(*, halo):
    actual_curve = {
        "podcast": "sub_podcast_actual",
        "display": "sub_display_actual",
        "ctv": "sub_ctv_actual",
    }
    pieces = []
    for cohort in cohorts.itertuples(index=False):
        source_curve = actual_curve.get(cohort.channel)
        if halo and cohort.channel in {"paid_search", "affiliate"}:
            source_curve = f"sub_{cohort.channel}_halo"
        if source_curve is None:
            continue
        patch = curves.loc[curves["curve_id"].eq(source_curve)].copy()
        patch["curve_id"] = cohort.curve_id
        patch["cohort_id"] = cohort.cohort_id
        patch["curve_version"] = 2
        pieces.append(patch)
    return pd.concat(pieces, ignore_index=True)


def build_scenario(plan, *, halo):
    future_cohorts, future_spend = [], []
    fixed = {"paid_search": 15000, "affiliate": 9000}
    curve_map = {
        "paid_search": "sub_paid_search_halo" if halo else "sub_paid_search",
        "affiliate": "sub_affiliate_halo" if halo else "sub_affiliate",
        "podcast": "sub_podcast_halo" if halo else "sub_podcast_actual",
        "display": "sub_display_actual",
        "ctv": "sub_ctv_actual",
    }
    for week in range(FUTURE_WEEKS):
        day = AS_OF + 1 + 7 * week
        amounts = fixed | plan.loc[plan["week"].eq(week)].set_index("channel")["spend"].to_dict()
        for channel, amount in amounts.items():
            if amount <= 0.01:
                continue
            curve_id = curve_map[channel]
            cohort_id = f"future-{channel}-w{week:02d}"
            future_cohorts.append({
                "cohort_id": cohort_id,
                "acquisition_period": day,
                "population": amount / curve_spec.loc[curve_id, "cac"],
                "curve_id": curve_id,
                "channel": channel,
                "week": 16 + week,
                "stage": "future",
            })
            future_spend.append({
                "period": day, "cohort_id": cohort_id,
                "amount": amount, "channel": channel,
            })

    scenario_curves = pd.concat([curves, scoped_overrides(halo=halo)], ignore_index=True)
    return tg.forecast(
        pd.concat([cohorts, pd.DataFrame(future_cohorts)], ignore_index=True),
        scenario_curves,
        observations=observations,
        acquisition_spend=pd.concat(
            [acquisition_spend, pd.DataFrame(future_spend)], ignore_index=True
        ),
        as_of=AS_OF, forecast_end=FORECAST_END, start=0,
    )


empty_plan = direct_plan.assign(spend=0.0)
control_result = build_scenario(empty_plan, halo=False)
direct_result = build_scenario(direct_plan, halo=False)
halo_attribution_only_result = build_scenario(halo_plan, halo=False)
halo_result = build_scenario(halo_plan, halo=True)"""
        ),
        md(
            """## Compare company cash, not merely channel ROAS

Every scenario retains the same established-channel plan and non-marketing cash outflow. The two optimized expansion plans spend the same $650k, so their ending-cash difference is an incremental portfolio comparison.

The “CTV allocation, attribution only” case deliberately values the halo plan without the halo. The gap to the halo-aware result quantifies what direct attribution omits."""
        ),
        code(
            """def cash_path(result):
    timeline = result.timeline()
    operating = np.cumsum(np.repeat(DAILY_OPERATING_CASH_FLOW, len(timeline)))
    return STARTING_CASH + operating + timeline["cumulative_marketing_pnl"].to_numpy()


scenarios = {
    "No new-channel expansion": control_result,
    "Direct optimizer: scale podcast": direct_result,
    "CTV allocation, attribution only": halo_attribution_only_result,
    "Incrementality-aware: podcast + CTV": halo_result,
}
summary_rows = []
for name, result in scenarios.items():
    cash = cash_path(result)
    summary_rows.append({
        "scenario": name,
        "total_acquisition_spend": result.acquisition_spend["amount"].sum(),
        "minimum_cash": cash.min(),
        "ending_cash": cash[-1],
        "marketing_pnl": result.timeline()["marketing_pnl"].sum(),
        "portfolio_roas": result.metrics().iloc[0]["roas"],
    })
scenario_summary = pd.DataFrame(summary_rows).set_index("scenario")
display(scenario_summary)

halo_increment = (
    cash_path(halo_result)[-1] - cash_path(halo_attribution_only_result)[-1]
)
future_ctv_ids = halo_result.cohorts.loc[
    halo_result.cohorts["cohort_id"].astype(str).str.startswith("future-ctv"), "cohort_id"
]
ctv_direct_contribution = halo_result.contributions.loc[
    halo_result.contributions["cohort_id"].isin(future_ctv_ids)
    & halo_result.contributions["category"].ne("activity"),
    "pnl_amount",
].sum()
ctv_direct_spend = halo_result.acquisition_spend.loc[
    halo_result.acquisition_spend["cohort_id"].isin(future_ctv_ids), "amount"
].sum()
print(f"CTV directly attributed marketing P&L: ${ctv_direct_contribution - ctv_direct_spend:,.0f}")
print(f"Modeled portfolio halo omitted by direct attribution: ${halo_increment:,.0f}")"""
        ),
        code(
            """comparison_figure = Figure(figsize=(14, 5), layout="constrained")
allocation_ax, cash_ax = comparison_figure.subplots(1, 2)

weekly_allocations = pd.DataFrame({
    "Podcast — direct plan": direct_plan.query("channel == 'podcast'").set_index("week")["spend"],
    "Podcast — halo-aware": halo_plan.query("channel == 'podcast'").set_index("week")["spend"],
    "CTV — halo-aware": halo_plan.query("channel == 'ctv'").set_index("week")["spend"],
})
weekly_allocations.plot(ax=allocation_ax, marker="o", title="New-channel allocation over time")
allocation_ax.set(xlabel="Future acquisition week", ylabel="Spend ($)")
allocation_ax.grid(alpha=0.2)

for name, result in scenarios.items():
    cash_ax.plot(cash_path(result), label=name)
cash_ax.axvline(AS_OF, color="#667085", linestyle=":", label="As of")
cash_ax.set(title="Company cash forecast", xlabel="Day", ylabel="Cash ($)")
cash_ax.legend(fontsize=8)
cash_ax.grid(alpha=0.2)
display(comparison_figure)

scenario_chart = tg.viz.scenario_comparison({
    "No expansion": control_result,
    "Podcast only": direct_result,
    "Podcast + CTV halo": halo_result,
})
display(scenario_chart.figure)"""
        ),
        md(
            """## CFO interpretation and measurement discipline

- Podcast is a conventional winner: its own cohorts beat the prior and the optimizer scales it as capacity expands.
- Display is a conventional loser: its updated 365-day contribution is negative, so post-test spend is zero.
- CTV is the important edge case. Its directly attributed cohorts lose money, but the scenario can still create portfolio value if the retention and monetization lift across other cohorts is causal.
- That last “if” is the decision risk. In production, estimate the halo with geo holdouts, lift tests, or another causal design; carry a low/base/high halo range; and avoid counting the same conversions in both direct attribution and incrementality.
- Theseus keeps the mechanics auditable: observations remain authoritative, revised curves affect future contributions, and the CFO can compare resulting cash paths under one canonical ledger."""
        ),
    ]
    notebook(cells, "Subscription_CFO_Channel_Experiments.ipynb")


def subscription_cmo_notebook() -> None:
    md = nbf.v4.new_markdown_cell
    code = nbf.v4.new_code_cell
    cells = [
        md(
            """# Subscription CMO lab: Waterfall and Distributed campaign budgeting

This notebook applies the two frameworks in [Optimization models in digital advertising](https://mobiledevmemo.com/optimization-models-in-digital-advertising/) to the synthetic subscription cohorts:

1. **Waterfall budgeting — primary ROAS constraint:** maximize scalable channel spend until the **next marginal dollar** reaches the ROAS threshold.
2. **Distributed budgeting — primary budget constraint:** allocate a fixed budget for maximum portfolio ROAS while every active channel meets the channel-level ROAS threshold.

The CMO uses 180-day cohort revenue, not same-day conversion value. Theseus turns retention and monetization curves into revenue by cohort; empirical spend–revenue response curves then represent diminishing returns as campaign scale expands.

All values are deterministic synthetic assumptions. The notebook demonstrates the decision mechanics, not expected market performance.

### Start here and related reading

- [Theseus API introduction and walkthrough](../../Theseus_Walkthrough.ipynb)
- [Optimization models in digital advertising](https://mobiledevmemo.com/optimization-models-in-digital-advertising/)
- [Building a marketing P&L using LTV and ROAS](https://mobiledevmemo.com/ltv-roas-marketing-p-and-l/)"""
        ),
        code(
            """from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import display
from matplotlib.figure import Figure
from scipy.interpolate import PchipInterpolator
from scipy.optimize import minimize

import theseus_growth as tg

%matplotlib inline
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda value: f"{value:,.3f}")

ROOT = next(path for path in [Path.cwd(), *Path.cwd().parents] if (path / "pyproject.toml").exists())
DATA = ROOT / "examples" / "data" / "subscription"

curves = pd.read_csv(DATA / "curves.csv")
curve_assumptions = pd.read_csv(DATA / "curve_assumptions.csv").set_index("curve_id")
response_assumptions = pd.read_csv(
    DATA / "campaign_response_assumptions.csv"
).set_index("channel")
response_assumptions["cac"] = response_assumptions["curve_id"].map(
    curve_assumptions["cac"]
)

REVENUE_WINDOW = 180
ROAS_TARGET = 1.20
DISTRIBUTED_BUDGET = 60000.0
HISTORICAL_POINTS = 21

display(response_assumptions)
print(f"Optimization window: {REVENUE_WINDOW} days")
print(f"Channel ROAS threshold: {ROAS_TARGET:.2f}×")
print(f"Distributed weekly budget: ${DISTRIBUTED_BUDGET:,.0f}")"""
        ),
        md(
            """## Construct historical spend–revenue curves from cohorts

At low spend, acquired subscribers scale almost linearly. As spend expands, inventory is exhausted and the next dollar reaches lower-propensity audiences. The synthetic response assumption is:

`effective subscribers = capacity × (1 − exp(−spend / (CAC × capacity)))`

We sample that relationship at 21 historical spend levels per channel. Each sample becomes a canonical Theseus cohort using the channel's measured retention and monetization curve. The optimizer will use only the resulting spend–revenue points—not the generating equation.

This separates two questions:

- **Cohort value:** how much does an acquired subscriber generate over 180 days?
- **Campaign scalability:** how many incremental subscribers can the next dollar acquire at this spend level?"""
        ),
        code(
            """history_cohorts, history_spend = [], []
for channel, spec in response_assumptions.iterrows():
    spend_levels = np.linspace(0, spec["max_weekly_spend"], HISTORICAL_POINTS)
    for point, spend in enumerate(spend_levels):
        effective_subscribers = spec["saturation_subscribers"] * (
            1 - np.exp(
                -spend / (spec["cac"] * spec["saturation_subscribers"])
            )
        )
        cohort_id = f"{channel}-response-{point:02d}"
        history_cohorts.append({
            "cohort_id": cohort_id,
            "acquisition_period": 0,
            "population": effective_subscribers,
            "curve_id": spec["curve_id"],
            "channel": channel,
            "weekly_spend": spend,
        })
        history_spend.append({
            "period": 0,
            "cohort_id": cohort_id,
            "amount": spend,
        })

history_cohorts = pd.DataFrame(history_cohorts)
history_spend = pd.DataFrame(history_spend)
history_result = tg.forecast(
    history_cohorts,
    curves,
    acquisition_spend=history_spend,
    as_of=0,
    forecast_end=REVENUE_WINDOW - 1,
    start=0,
)

cohort_revenue = (
    history_result.contributions.loc[
        history_result.contributions["category"].eq("revenue")
    ]
    .groupby("cohort_id")["amount"].sum()
)
response_points = (
    history_cohorts[["cohort_id", "channel", "weekly_spend"]]
    .assign(revenue_180d=lambda frame: frame["cohort_id"].map(cohort_revenue))
)
response_points["average_roas"] = np.divide(
    response_points["revenue_180d"],
    response_points["weekly_spend"],
    out=np.full(len(response_points), np.nan),
    where=response_points["weekly_spend"].ne(0),
)
display(response_points.groupby("channel").head(4))

response_figure = Figure(figsize=(10, 6), layout="constrained")
response_ax = response_figure.subplots()
for channel, points in response_points.groupby("channel", sort=False):
    response_ax.plot(
        points["weekly_spend"], points["revenue_180d"],
        marker="o", markersize=3, label=channel.replace("_", " ").title(),
    )
response_ax.set(
    title="Historical 180-day cohort revenue by weekly campaign spend",
    xlabel="Weekly spend ($)", ylabel="180-day cohort revenue ($)",
)
response_ax.legend()
response_ax.grid(alpha=0.2)
display(response_figure)"""
        ),
        md(
            """## Fit empirical response curves

A shape-preserving interpolator connects each channel's historical points. Its first derivative is **marginal ROAS**: the revenue expected from the next dollar at a given spend level.

Average ROAS answers whether the dollars already spent were productive. Marginal ROAS answers whether spending the *next* dollar is productive. The Waterfall model uses the latter."""
        ),
        code(
            """response_models = {}
for channel, points in response_points.groupby("channel", sort=False):
    ordered = points.sort_values("weekly_spend")
    revenue_model = PchipInterpolator(
        ordered["weekly_spend"], ordered["revenue_180d"], extrapolate=False
    )
    response_models[channel] = {
        "revenue": revenue_model,
        "marginal_roas": revenue_model.derivative(),
    }


def revenue(channel, spend):
    return float(response_models[channel]["revenue"](spend))


def marginal_roas(channel, spend):
    return float(response_models[channel]["marginal_roas"](spend))


def allocation_table(spend_by_channel):
    rows = []
    for channel, spend in spend_by_channel.items():
        channel_revenue = revenue(channel, spend)
        rows.append({
            "channel": channel,
            "spend": spend,
            "revenue_180d": channel_revenue,
            "average_roas": channel_revenue / spend if spend else np.nan,
            "marginal_roas": marginal_roas(channel, spend),
        })
    return pd.DataFrame(rows).set_index("channel")"""
        ),
        md(
            """## Model 1: Waterfall budgeting

There is no primary portfolio budget. For each channel, spend expands to the highest observed level where marginal ROAS remains at least 1.20×. A channel whose first scalable dollar cannot meet the threshold receives zero.

Notice that average ROAS at the solution is higher than the threshold. Stopping when *average* ROAS reaches 1.20× would overspend because the marginal dollars would already be below the hurdle."""
        ),
        code(
            """waterfall_spend = {}
for channel, spec in response_assumptions.iterrows():
    grid = np.linspace(0, spec["max_weekly_spend"], 10001)
    marginal = response_models[channel]["marginal_roas"](grid)
    eligible = grid[marginal >= ROAS_TARGET]
    selected = float(eligible[-1]) if len(eligible) else 0.0
    if selected < spec["min_active_spend"]:
        selected = 0.0
    waterfall_spend[channel] = selected

waterfall_allocation = allocation_table(waterfall_spend)
assert waterfall_allocation.loc[
    waterfall_allocation["spend"].gt(0), "marginal_roas"
].min() >= ROAS_TARGET - 0.002
display(waterfall_allocation)
print(f"Emergent weekly portfolio budget: ${waterfall_allocation['spend'].sum():,.0f}")
print(
    "Portfolio 180-day ROAS: "
    f"{waterfall_allocation['revenue_180d'].sum() / waterfall_allocation['spend'].sum():.3f}×"
)

waterfall_figure = Figure(figsize=(10, 6), layout="constrained")
waterfall_ax = waterfall_figure.subplots()
for channel, spec in response_assumptions.iterrows():
    grid = np.linspace(0, spec["max_weekly_spend"], 400)
    waterfall_ax.plot(
        grid, response_models[channel]["marginal_roas"](grid),
        label=channel.replace("_", " ").title(),
    )
    if waterfall_spend[channel] > 0:
        waterfall_ax.scatter(
            waterfall_spend[channel], marginal_roas(channel, waterfall_spend[channel]),
            s=45,
        )
waterfall_ax.axhline(ROAS_TARGET, color="#B24A3B", linestyle="--", label="ROAS target")
waterfall_ax.set(
    title="Waterfall stopping points use marginal ROAS",
    xlabel="Weekly channel spend ($)", ylabel="Marginal 180-day ROAS",
    ylim=(0, 1.8),
)
waterfall_ax.legend()
waterfall_ax.grid(alpha=0.2)
display(waterfall_figure)"""
        ),
        md(
            """## Model 2: Distributed budgeting

The CMO must deploy exactly $60k per week. With a fixed denominator, maximizing portfolio ROAS is equivalent to maximizing total 180-day revenue.

Active channels must:

- receive at least their minimum testable spend,
- stay within their observed historical range, and
- maintain average channel ROAS of at least 1.20×.

Because spend may also be exactly zero, the optimization enumerates possible active-channel sets and solves each continuous allocation with SLSQP. This avoids pretending that a tiny, operationally meaningless allocation is a valid campaign."""
        ),
        code(
            """def solve_distributed_budget(budget):
    channels = response_assumptions.index.tolist()
    best = None
    for active_count in range(1, len(channels) + 1):
        for active in combinations(channels, active_count):
            lower = response_assumptions.loc[list(active), "min_active_spend"].to_numpy(float)
            upper = response_assumptions.loc[list(active), "max_weekly_spend"].to_numpy(float)
            if lower.sum() > budget or upper.sum() < budget:
                continue
            capacity = upper - lower
            initial = lower + (budget - lower.sum()) * capacity / capacity.sum()

            def objective(values):
                return -sum(revenue(channel, value) for channel, value in zip(active, values))

            constraints = [{"type": "eq", "fun": lambda values: values.sum() - budget}]
            for position, channel in enumerate(active):
                constraints.append({
                    "type": "ineq",
                    "fun": lambda values, position=position, channel=channel: (
                        revenue(channel, values[position])
                        - ROAS_TARGET * values[position]
                    ),
                })
            solution = minimize(
                objective,
                initial,
                method="SLSQP",
                bounds=list(zip(lower, upper)),
                constraints=constraints,
                options={"ftol": 1e-9, "maxiter": 1000},
            )
            if not solution.success:
                continue
            candidate_revenue = -solution.fun
            if best is None or candidate_revenue > best["revenue"]:
                best = {
                    "revenue": candidate_revenue,
                    "active": active,
                    "spend": solution.x,
                    "message": solution.message,
                }
    if best is None:
        raise RuntimeError("No feasible channel allocation satisfies the budget and ROAS constraints.")
    allocation = pd.Series(0.0, index=channels)
    allocation.loc[list(best["active"])] = best["spend"]
    return allocation


distributed_spend = solve_distributed_budget(DISTRIBUTED_BUDGET)
distributed_allocation = allocation_table(distributed_spend)
assert abs(distributed_allocation["spend"].sum() - DISTRIBUTED_BUDGET) < 0.01
assert distributed_allocation.loc[
    distributed_allocation["spend"].gt(0), "average_roas"
].min() >= ROAS_TARGET - 0.001
display(distributed_allocation)
print(
    "Optimized portfolio 180-day ROAS: "
    f"{distributed_allocation['revenue_180d'].sum() / DISTRIBUTED_BUDGET:.3f}×"
)"""
        ),
        md(
            """## Benchmark the optimized allocation

An equal split is simple but ignores both cohort quality and saturation. Here it also directs money to Display and CTV even though their direct-attribution cohorts cannot clear the 1.20× hurdle.

This is an intentionally strict direct-response view. The separate subscription CFO notebook shows how an incrementality-tested CTV halo can justify a different portfolio decision."""
        ),
        code(
            """equal_spend = pd.Series(
    DISTRIBUTED_BUDGET / len(response_assumptions),
    index=response_assumptions.index,
)
equal_allocation = allocation_table(equal_spend)

qualified_channels = ["paid_search", "affiliate", "podcast"]
qualified_equal_spend = pd.Series(0.0, index=response_assumptions.index)
qualified_equal_spend.loc[qualified_channels] = DISTRIBUTED_BUDGET / len(qualified_channels)
qualified_equal_allocation = allocation_table(qualified_equal_spend)

allocation_comparison = pd.DataFrame({
    "Distributed optimizer": distributed_allocation["spend"],
    "Equal split — all channels": equal_allocation["spend"],
    "Equal split — qualified channels": qualified_equal_allocation["spend"],
})
display(allocation_comparison)

benchmark = pd.DataFrame([
    {
        "plan": "Distributed optimizer",
        "revenue_180d": distributed_allocation["revenue_180d"].sum(),
        "portfolio_roas": distributed_allocation["revenue_180d"].sum() / DISTRIBUTED_BUDGET,
        "channels_below_target": 0,
    },
    {
        "plan": "Equal split — all channels",
        "revenue_180d": equal_allocation["revenue_180d"].sum(),
        "portfolio_roas": equal_allocation["revenue_180d"].sum() / DISTRIBUTED_BUDGET,
        "channels_below_target": int((equal_allocation["average_roas"] < ROAS_TARGET).sum()),
    },
    {
        "plan": "Equal split — qualified channels",
        "revenue_180d": qualified_equal_allocation["revenue_180d"].sum(),
        "portfolio_roas": qualified_equal_allocation["revenue_180d"].sum() / DISTRIBUTED_BUDGET,
        "channels_below_target": int(
            (qualified_equal_allocation.loc[qualified_channels, "average_roas"] < ROAS_TARGET).sum()
        ),
    },
]).set_index("plan")
display(benchmark)

allocation_figure = Figure(figsize=(10, 5), layout="constrained")
allocation_ax = allocation_figure.subplots()
allocation_comparison.plot(kind="bar", ax=allocation_ax)
allocation_ax.set(title="Weekly campaign allocation", xlabel="Channel", ylabel="Spend ($)")
allocation_ax.tick_params(axis="x", rotation=0)
display(allocation_figure)"""
        ),
        md(
            """## Push the chosen plans back through Theseus

The response optimizer decides spend. Theseus remains the financial source of truth: each allocation is converted into channel cohorts, broadcast over 180 days, and compared at common maturity checkpoints."""
        ),
        code(
            """def forecast_allocation(spend_by_channel):
    cohort_rows, spend_rows = [], []
    for channel, spend in spend_by_channel.items():
        if spend <= 0.01:
            continue
        spec = response_assumptions.loc[channel]
        population = spec["saturation_subscribers"] * (
            1 - np.exp(-spend / (spec["cac"] * spec["saturation_subscribers"]))
        )
        cohort_rows.append({
            "cohort_id": channel,
            "acquisition_period": 0,
            "population": population,
            "curve_id": spec["curve_id"],
            "channel": channel,
        })
        spend_rows.append({"period": 0, "cohort_id": channel, "amount": spend})
    return tg.forecast(
        pd.DataFrame(cohort_rows), curves,
        acquisition_spend=pd.DataFrame(spend_rows),
        as_of=0, forecast_end=REVENUE_WINDOW - 1, start=0,
    )


waterfall_result = forecast_allocation(pd.Series(waterfall_spend))
distributed_result = forecast_allocation(distributed_spend)
equal_result = forecast_allocation(equal_spend)
qualified_equal_result = forecast_allocation(qualified_equal_spend)


def maturity_row(name, result):
    timeline = result.timeline()
    spend = timeline["acquisition_spend"].sum()
    cumulative_revenue = timeline["revenue"].cumsum()
    return {
        "plan": name,
        "spend": spend,
        "30d_roas": cumulative_revenue.iloc[29] / spend,
        "90d_roas": cumulative_revenue.iloc[89] / spend,
        "180d_roas": cumulative_revenue.iloc[179] / spend,
        "180d_revenue": cumulative_revenue.iloc[179],
        "cash_at_risk": result.metrics().iloc[0]["cash_at_risk"],
    }


maturity = pd.DataFrame([
    maturity_row("Waterfall", waterfall_result),
    maturity_row("Distributed optimizer", distributed_result),
    maturity_row("Equal split — all", equal_result),
    maturity_row("Equal split — qualified", qualified_equal_result),
]).set_index("plan")
display(maturity)

progression_figure = Figure(figsize=(14, 5), layout="constrained")
waterfall_ax, distributed_ax = progression_figure.subplots(1, 2)
waterfall_result.plot.cohort_progression(
    interval=30, ax=waterfall_ax, title="Waterfall: channel ROAS maturation"
)
distributed_result.plot.cohort_progression(
    interval=30, ax=distributed_ax, title="Distributed: channel ROAS maturation"
)
display(progression_figure)"""
        ),
        md(
            """## CMO interpretation

- **Waterfall** answers “How much can I spend while the next dollar still clears my hurdle?” Its total budget emerges from the channel response curves.
- **Distributed** answers “Given a fixed budget, where should each dollar go?” It equalizes marginal opportunity subject to the active-channel ROAS constraints and observed scale limits.
- A fixed-budget portfolio can spend beyond the Waterfall stopping point because the Distributed model constrains **average** channel ROAS, while Waterfall stops on **marginal** ROAS. Those are different operating policies, not contradictory answers.
- Cohort maturity matters. A 30-day dashboard can reject campaigns that clear the 180-day hurdle; the maturity table makes that tradeoff explicit.
- Historical response is not destiny. Before production use, add uncertainty bands, out-of-sample validation, auction and creative regime changes, incrementality estimates, and guardrails against extrapolation beyond observed spend."""
        ),
    ]
    notebook(cells, "Subscription_CMO_Campaign_Optimization.ipynb")


def main() -> None:
    game_notebook()
    subscription_notebook()
    subscription_cmo_notebook()
    print(f"Wrote scenario-planning notebooks to {DESTINATION}")


if __name__ == "__main__":
    main()
