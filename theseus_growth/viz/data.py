"""Chart-ready financial DataFrames. No plotting dependency is needed here."""

from __future__ import annotations

from numbers import Integral
from typing import TYPE_CHECKING, Any, Iterable

import numpy as np
import pandas as pd

from ..exceptions import SchemaError, TimeAxisError

if TYPE_CHECKING:
    from ..engine import ForecastResult


def select_cohorts(result: ForecastResult, cohorts: Iterable[Any] | None = None) -> pd.DataFrame:
    if cohorts is None:
        selected = result.cohorts.copy(deep=True)
    else:
        ids = [cohorts] if isinstance(cohorts, (str, bytes)) or not isinstance(cohorts, Iterable) else list(cohorts)
        unknown = set(ids) - set(result.cohorts["cohort_id"])
        if unknown:
            raise SchemaError(f"Unknown cohort ids: {sorted(unknown, key=str)!r}.")
        selected = result.cohorts.loc[result.cohorts["cohort_id"].isin(ids)].copy()
    if selected.empty:
        raise SchemaError("Select at least one cohort to visualize.")
    return selected.sort_values("acquisition_period", kind="stable").reset_index(drop=True)


def cohort_spend_data(result: ForecastResult, *, spend: pd.DataFrame | None = None) -> pd.DataFrame:
    """Resolve each cohort's fixed acquisition denominator.

    ``spend`` explicitly supplies cohort_id/amount rows. Otherwise source spend
    uses cohort_id when supplied, or acquisition_period only if that maps to one
    cohort. Ambiguous/unattributed spend raises instead of guessing an allocation.
    Missing or zero denominators produce NaN ROAS, never infinity or invented ROI.
    """
    source = result.acquisition_spend if spend is None else spend
    if not isinstance(source, pd.DataFrame) or "amount" not in source:
        raise SchemaError("Spend must be a DataFrame with an amount column.")
    if spend is not None and "cohort_id" not in source:
        raise SchemaError("Explicit cohort spend requires cohort_id and amount columns.")
    rows = source.copy(deep=True)
    try:
        rows["amount"] = pd.to_numeric(rows["amount"], errors="raise").astype(float)
    except (ValueError, TypeError) as exc:
        raise SchemaError("Cohort spend amounts must be numeric.") from exc
    if not np.isfinite(rows["amount"]).all() or rows["amount"].lt(0).any():
        raise SchemaError("Cohort spend amounts must be finite and non-negative.")
    ids = set(result.cohorts["cohort_id"])
    assignments = []
    for _, row in rows.iterrows():
        cohort_id = row.get("cohort_id", pd.NA)
        if pd.isna(cohort_id):
            if spend is not None:
                raise SchemaError("Explicit cohort spend cannot have missing cohort_id values.")
            matches = result.cohorts.loc[
                result.cohorts["acquisition_period"].eq(row["period"]), "cohort_id"
            ]
            if len(matches) != 1:
                raise SchemaError(
                    f"Spend at {row['period']!r} maps to {len(matches)} cohorts. "
                    "Supply cohort_id on acquisition_spend, or an explicit "
                    "spend DataFrame with cohort_id/amount allocations."
                )
            cohort_id = matches.iloc[0]
        if cohort_id not in ids:
            raise SchemaError(f"Spend references unknown cohort {cohort_id!r}.")
        assignments.append(cohort_id)
    rows["cohort_id"] = assignments
    totals = rows.groupby("cohort_id", sort=False)["amount"].sum()
    output = result.cohorts[["cohort_id"]].copy()
    output["acquisition_spend"] = output["cohort_id"].map(totals).astype(float)
    return output


def cohort_daily_data(
    result: ForecastResult,
    *,
    cohorts: Iterable[Any] | None = None,
    basis: str = "resolved",
    components: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Revenue by cohort age with explicit completeness and provenance.

    Values beyond known curve/observation support remain missing. In observed
    mode, a day is complete only if every selected revenue component has an
    observation. A missing day poisons subsequent cumulative values; it is never
    converted into zero. The end of age zero is elapsed day one.
    """
    if basis not in {"resolved", "observed", "projected"}:
        raise SchemaError("basis must be 'resolved', 'observed', or 'projected'.")
    selected = select_cohorts(result, cohorts)
    ledger = result.projections.copy(deep=True) if basis == "projected" else result.contributions
    ledger = ledger.loc[ledger["category"].eq("revenue")].copy()
    if components is not None:
        names = [components] if isinstance(components, str) else list(components)
        if not names:
            raise SchemaError("components cannot be empty.")
        unknown = set(names) - set(ledger["component"])
        if unknown:
            raise SchemaError(f"Unknown revenue components: {sorted(unknown, key=str)!r}.")
        ledger = ledger.loc[ledger["component"].isin(names)]
    pieces = []
    for _, cohort in selected.iterrows():
        acquisition = cohort["acquisition_period"]
        if acquisition < result.start:
            raise SchemaError(
                f"Cohort {cohort['cohort_id']!r} begins before forecast start. "
                "Cumulative age charts need its full history from age zero."
            )
        last = min(result.cursor, result.forecast_end) if basis == "observed" else result.forecast_end
        if acquisition > last:
            continue
        rows = ledger.loc[ledger["cohort_id"].eq(cohort["cohort_id"])]
        component_names = sorted(rows["component"].unique(), key=str)
        if not component_names:
            raise SchemaError(f"No revenue components for cohort {cohort['cohort_id']!r}.")
        periods = result.axis.range(acquisition, last)
        amounts = rows.pivot(index="period", columns="component", values="amount").reindex(
            index=periods, columns=component_names
        )
        statuses = rows.pivot(index="period", columns="component", values="basis").reindex(
            index=periods, columns=component_names
        )
        complete = amounts.notna().all(axis=1)
        observed = complete & statuses.eq("observed").all(axis=1)
        if basis == "observed":
            complete &= observed
        daily = amounts.sum(axis=1, min_count=len(component_names)).where(complete)
        cumulative = daily.cumsum(skipna=False)
        cumulative_observed = observed.cummin() & cumulative.notna()
        part = pd.DataFrame({
            "cohort_id": cohort["cohort_id"],
            "acquisition_period": acquisition,
            "period": periods,
            "age": np.arange(len(periods)),
            "elapsed_days": np.arange(1, len(periods) + 1),
            "revenue": daily.to_numpy(dtype=float),
            "cumulative_revenue": cumulative.to_numpy(dtype=float),
            "population": float(cohort["population"]),
            "complete": complete.to_numpy(),
            "value_status": np.where(~complete, "missing", np.where(observed, "observed", "projected")),
            "cumulative_status": np.where(
                cumulative.isna(), "missing", np.where(cumulative_observed, "observed", "projected")
            ),
        })
        population = float(cohort["population"])
        part["revenue_per_user"] = part["revenue"] / population if population else np.nan
        part["cumulative_revenue_per_user"] = part["cumulative_revenue"] / population if population else np.nan
        pieces.append(part)
    if not pieces:
        raise SchemaError("No acquired cohorts are available for this basis and cursor.")
    return pd.concat(pieces, ignore_index=True)


def interval_spec(interval: str | int) -> tuple[str, int, str]:
    """Return kind, size and label for acquisition-relative interval boundaries."""
    if isinstance(interval, Integral) and not isinstance(interval, bool) and interval > 0:
        return "days", int(interval), f"{int(interval)}-period intervals"
    aliases = {
        "d": ("days", 1, "Days"), "daily": ("days", 1, "Days"), "day": ("days", 1, "Days"),
        "w": ("days", 7, "Weeks"), "weekly": ("days", 7, "Weeks"), "week": ("days", 7, "Weeks"),
        "m": ("months", 1, "Months"), "monthly": ("months", 1, "Months"), "month": ("months", 1, "Months"),
        "q": ("months", 3, "Quarters"), "quarterly": ("months", 3, "Quarters"),
        "quarter": ("months", 3, "Quarters"),
        "y": ("months", 12, "Years"), "yearly": ("months", 12, "Years"), "annual": ("months", 12, "Years"),
        "year": ("months", 12, "Years"),
    }
    if isinstance(interval, str) and interval.lower() in aliases:
        return aliases[interval.lower()]
    raise SchemaError("interval must be daily, weekly, monthly, quarterly, yearly, or a positive integer.")


def cohort_progression_data(
    result: ForecastResult,
    *,
    interval: str | int = "daily",
    cohorts: Iterable[Any] | None = None,
    basis: str = "resolved",
    spend: pd.DataFrame | None = None,
    components: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Origin-aligned cumulative ROAS at completed age-interval boundaries.

    Point zero is pre-revenue (0, 0). Daily point one includes age zero; weekly
    point one includes ages 0..6. Monthly boundaries are acquisition + n months
    (direct offsets, avoiding month-end drift). Immature intervals are omitted.
    """
    kind, size, label = interval_spec(interval)
    if kind == "months" and result.axis.kind != "calendar":
        raise TimeAxisError("Calendar-month intervals require datetime periods; use interval=30 for 30 abstract periods.")
    daily = cohort_daily_data(result, cohorts=cohorts, basis=basis, components=components)
    spend_by_id = cohort_spend_data(result, spend=spend).set_index("cohort_id")["acquisition_spend"]
    output = []
    for cohort_id, group in daily.groupby("cohort_id", sort=False):
        group = group.sort_values("age").reset_index(drop=True)
        acquisition = group.iloc[0]["acquisition_period"]
        denominator = float(spend_by_id.loc[cohort_id])
        valid_spend = np.isfinite(denominator) and denominator > 0
        output.append({
            "cohort_id": cohort_id, "interval": label, "interval_index": 0,
            "elapsed_days": 0, "period": acquisition, "cumulative_revenue": 0.0,
            "acquisition_spend": denominator, "roas": 0.0 if valid_spend else np.nan,
            "value_status": "origin", "is_origin": True,
        })
        count = 1
        while True:
            boundary = (
                result.axis.add(acquisition, count * size)
                if kind == "days" else acquisition + pd.DateOffset(months=count * size)
            )
            elapsed = (boundary.date() - acquisition.date()).days if kind == "months" else count * size
            if elapsed > len(group):
                break
            endpoint = group.iloc[elapsed - 1]
            cumulative = float(endpoint["cumulative_revenue"])
            output.append({
                "cohort_id": cohort_id, "interval": label, "interval_index": count,
                "elapsed_days": elapsed, "period": endpoint["period"],
                "cumulative_revenue": cumulative, "acquisition_spend": denominator,
                "roas": cumulative / denominator if valid_spend else np.nan,
                "value_status": endpoint["cumulative_status"], "is_origin": False,
            })
            count += 1
    return pd.DataFrame(output)


def cohort_summary_data(result: ForecastResult, *, cohorts=None, spend=None) -> pd.DataFrame:
    """Recorded, estimated-to-date and future revenue by cohort at the cursor."""
    selected = select_cohorts(result, cohorts)
    ledger = result.contributions
    revenue = ledger.loc[ledger["category"].eq("revenue")]
    cost = cohort_spend_data(result, spend=spend).set_index("cohort_id")["acquisition_spend"]
    summaries = []
    for _, cohort in selected.iterrows():
        rows = revenue.loc[revenue["cohort_id"].eq(cohort["cohort_id"])]
        elapsed = rows["period"].le(result.cursor)
        acquired = cohort["acquisition_period"] <= result.cursor
        recorded = float(rows.loc[elapsed & rows["basis"].eq("observed"), "amount"].sum())
        estimated = float(rows.loc[elapsed & rows["basis"].eq("projected"), "amount"].sum())
        future = float(rows.loc[~elapsed, "amount"].sum())
        summaries.append({
            "cohort_id": cohort["cohort_id"], "acquisition_period": cohort["acquisition_period"],
            "population": float(cohort["population"]), "is_acquired": acquired,
            "recorded_revenue": recorded, "estimated_to_date": estimated,
            "projected_receivable": future if acquired else 0.0,
            "planned_revenue": future if not acquired else 0.0,
            "expected_revenue": recorded + estimated + future,
            "acquisition_spend": float(cost.loc[cohort["cohort_id"]]),
        })
    output = pd.DataFrame(summaries)
    denominator = output["population"].where(output["population"].gt(0))
    output["cpi"] = output["acquisition_spend"] / denominator
    for column in ["recorded_revenue", "estimated_to_date", "projected_receivable", "expected_revenue"]:
        output[f"{column}_per_user"] = output[column] / denominator
    output["expected_roas"] = output["expected_revenue"] / output["acquisition_spend"].where(output["acquisition_spend"].gt(0))
    return output


def portfolio_timeline_data(result: ForecastResult) -> pd.DataFrame:
    """Portfolio P&L and revenue/cost balances, using the engine's daily ledger."""
    timeline = result.timeline().copy(deep=True)
    timeline = timeline.rename(columns={"is_actual_period": "is_elapsed_period"})
    timeline["cumulative_revenue"] = timeline["revenue"].cumsum()
    timeline["cumulative_spend"] = timeline["acquisition_spend"].cumsum()
    timeline["cumulative_contribution"] = timeline["contribution_before_acquisition"].cumsum()
    timeline["capital_at_risk"] = (-timeline["cumulative_marketing_pnl"]).clip(lower=0)
    # Calendar position alone does not imply that historical revenue is observed.
    timeline["revenue_status"] = "projected"
    rows = result.contributions
    revenue = rows.loc[rows["category"].eq("revenue")]
    observed = revenue.assign(observed=revenue["basis"].eq("observed")).groupby("period")["observed"].all()
    timeline.loc[timeline["period"].map(observed).eq(True), "revenue_status"] = "observed"
    return timeline


def break_even_data(result: ForecastResult) -> pd.DataFrame:
    """First daily/cumulative nonnegative P&L after acquisition spending starts."""
    data = portfolio_timeline_data(result)
    active = data["cumulative_spend"].gt(0)
    events = []
    for metric, name in [("marketing_pnl", "daily_break_even"), ("cumulative_marketing_pnl", "cumulative_break_even")]:
        matches = data.loc[active & data[metric].ge(-1e-9)]
        events.append({"event": name, "period": matches.iloc[0]["period"] if not matches.empty else None})
    trough = data.loc[data["cumulative_marketing_pnl"].idxmin()]
    events.append({"event": "maximum_capital_at_risk", "period": trough["period"]})
    return pd.DataFrame(events)


def receivables_data(result: ForecastResult) -> pd.DataFrame:
    """Remaining modeled revenue from already-acquired cohorts at each period.

    The horizon stays fixed at forecast_end. Planned, not-yet-acquired cohorts do
    not enter this balance. This is a model snapshot, not a historical forecast-vintage replay.
    """
    revenue = result.contributions
    revenue = revenue.loc[revenue["category"].eq("revenue")]
    periods = result.axis.range(result.start, result.forecast_end)
    remaining = np.zeros(len(periods), dtype=float)
    recorded = np.zeros(len(periods), dtype=float)
    estimated = np.zeros(len(periods), dtype=float)
    for _, cohort in result.cohorts.iterrows():
        rows = revenue.loc[revenue["cohort_id"].eq(cohort["cohort_id"])]
        projected = rows.loc[rows["basis"].eq("projected")].groupby("period")["amount"].sum().reindex(periods, fill_value=0).to_numpy(dtype=float)
        actual = rows.loc[rows["basis"].eq("observed")].groupby("period")["amount"].sum().reindex(periods, fill_value=0).to_numpy(dtype=float)
        acquired = np.asarray([period >= cohort["acquisition_period"] for period in periods])
        total = projected + actual
        remaining += np.where(acquired, total.sum() - total.cumsum(), 0.0)
        recorded += actual.cumsum()
        estimated += projected.cumsum()
    return pd.DataFrame({
        "period": periods, "recorded_revenue": recorded,
        "modeled_revenue_to_date": estimated, "projected_receivable": remaining,
    })
