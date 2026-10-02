"""DataFrame-first forecast orchestration built on atomic cohort broadcasts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

from .broadcasting import CONTRIBUTION_COLUMNS, broadcast as broadcast_cohort, pnl_amount
from .exceptions import SchemaError, TimeAxisError
from .frames import (
    SourceFrames,
    merge_rows,
    normalize_cohorts,
    normalize_curves,
    normalize_observations,
    normalize_spend,
    select_curve,
)
from .time import TimeAxis, infer_time_axis


@dataclass(frozen=True)
class ForecastResult:
    """An immutable-by-convention forecast and its sufficient incremental state."""

    cohorts: pd.DataFrame
    curves: pd.DataFrame
    projections: pd.DataFrame
    observations: pd.DataFrame
    acquisition_spend: pd.DataFrame
    start: Any
    cursor: Any
    forecast_end: Any
    axis: TimeAxis

    @property
    def contributions(self) -> pd.DataFrame:
        """Resolved long-form contributions, with observations over projections."""

        return _overlay_observations(
            self.projections,
            self.observations,
            self.cohorts,
            self.curves,
            self.axis,
        )

    @property
    def state(self) -> "ForecastResult":
        """The result itself is the serializable state required by ``advance``."""

        return self

    @property
    def plot(self):
        """Composable visualizations; install theseus-growth[viz] to render charts."""
        from .viz import PlotAccessor

        return PlotAccessor(self)

    def cohort_progression(self, **kwargs) -> pd.DataFrame:
        """Return origin-aligned cumulative ROAS data without a plotting dependency."""
        from .viz import cohort_progression_data

        return cohort_progression_data(self, **kwargs)

    def timeline(self) -> pd.DataFrame:
        """Return period-level revenue, contribution, spend, and marketing P&L."""

        periods = pd.DataFrame({"period": self.axis.range(self.start, self.forecast_end)})
        contributions = self.contributions
        financial = contributions.loc[contributions["category"].ne("activity")].copy()

        def aggregate(mask: pd.Series, column: str = "pnl_amount") -> pd.Series:
            return financial.loc[mask].groupby("period", sort=False)[column].sum()

        if financial.empty:
            summarized = periods.copy()
        else:
            summarized = periods.copy()
            values = {
                "recorded_revenue": aggregate(
                    financial["category"].eq("revenue") & financial["basis"].eq("observed"),
                    "amount",
                ),
                "projected_revenue": aggregate(
                    financial["category"].eq("revenue") & financial["basis"].eq("projected"),
                    "amount",
                ),
                "cost": aggregate(financial["category"].eq("cost"), "amount"),
                "recorded_contribution": aggregate(financial["basis"].eq("observed")),
                "projected_contribution": aggregate(financial["basis"].eq("projected")),
                "contribution_before_acquisition": financial.groupby("period", sort=False)[
                    "pnl_amount"
                ].sum(),
            }
            for column, series in values.items():
                summarized[column] = summarized["period"].map(series).fillna(0.0)

        expected = [
            "recorded_revenue",
            "projected_revenue",
            "cost",
            "recorded_contribution",
            "projected_contribution",
            "contribution_before_acquisition",
        ]
        for column in expected:
            if column not in summarized:
                summarized[column] = 0.0
        summarized["revenue"] = summarized["recorded_revenue"] + summarized["projected_revenue"]
        if self.acquisition_spend.empty:
            summarized["acquisition_spend"] = 0.0
        else:
            spend = self.acquisition_spend.groupby("period", sort=False)["amount"].sum()
            summarized["acquisition_spend"] = (
                summarized["period"].map(spend).fillna(0.0).astype(float)
            )
        summarized["marketing_pnl"] = (
            summarized["contribution_before_acquisition"] - summarized["acquisition_spend"]
        )
        summarized["cumulative_marketing_pnl"] = summarized["marketing_pnl"].cumsum()
        summarized["is_actual_period"] = summarized["period"].map(
            lambda period: period <= self.cursor
        )
        return summarized[
            [
                "period",
                "is_actual_period",
                "recorded_revenue",
                "projected_revenue",
                "revenue",
                "cost",
                "recorded_contribution",
                "projected_contribution",
                "contribution_before_acquisition",
                "acquisition_spend",
                "marketing_pnl",
                "cumulative_marketing_pnl",
            ]
        ]

    def marketing_pnl(self) -> pd.DataFrame:
        """Alias for the canonical period-level financial timeline."""

        return self.timeline()

    def metrics(self) -> pd.DataFrame:
        """Return a one-row portfolio summary derived from canonical DataFrames."""

        timeline = self.timeline()
        contributions = self.contributions
        financial = contributions.loc[contributions["category"].ne("activity")]
        future = financial["period"].map(lambda period: period > self.cursor)
        projected_receivable = financial.loc[
            financial["basis"].eq("projected") & future, "pnl_amount"
        ].sum()
        spend = float(timeline["acquisition_spend"].sum())
        revenue = float(timeline["revenue"].sum())
        contribution = float(timeline["contribution_before_acquisition"].sum())
        population = float(self.cohorts["population"].sum())
        nonnegative = timeline.loc[timeline["cumulative_marketing_pnl"].ge(0)]
        break_even = nonnegative.iloc[0]["period"] if not nonnegative.empty else pd.NA
        return pd.DataFrame(
            [
                {
                    "cursor": self.cursor,
                    "forecast_end": self.forecast_end,
                    "recorded_contribution": float(
                        financial.loc[financial["basis"].eq("observed"), "pnl_amount"].sum()
                    ),
                    "projected_receivable": float(projected_receivable),
                    "lifetime_contribution": contribution,
                    "acquisition_spend": spend,
                    "marketing_pnl": float(timeline["marketing_pnl"].sum()),
                    "ltv": contribution / population if population else np.nan,
                    "roas": revenue / spend if spend else np.nan,
                    "break_even_period": break_even,
                    "cash_at_risk": max(
                        0.0, -float(timeline["cumulative_marketing_pnl"].min())
                    ),
                }
            ]
        )

    def broadcast(
        self,
        *,
        cohorts: Iterable[Any] | None = None,
        curves: pd.DataFrame | None = None,
        start: Any | None = None,
        end: Any | None = None,
    ) -> "ForecastResult":
        """Broadcast selected cohorts over an inclusive timeline slice.

        Supplying ``curves`` creates cohort-scoped curve overrides. Existing modeled
        rows in the selected slice are replaced; observed rows remain authoritative.
        """

        if cohorts is None:
            cohort_ids = self.cohorts["cohort_id"].tolist()
        elif isinstance(cohorts, (str, bytes)) or not isinstance(cohorts, Iterable):
            cohort_ids = [cohorts]
        else:
            cohort_ids = list(cohorts)
        if not cohort_ids:
            raise SchemaError("At least one cohort_id is required for a broadcast update.")
        unknown = sorted(set(cohort_ids) - set(self.cohorts["cohort_id"]), key=str)
        if unknown:
            raise SchemaError(f"Unknown cohort ids: {unknown!r}.")
        first = self.start if start is None else self.axis.normalize(start)
        last = self.forecast_end if end is None else self.axis.normalize(end)
        if first < self.start or last > self.forecast_end or last < first:
            raise TimeAxisError("Broadcast updates must stay within the forecast timeline.")

        curve_catalog = self.curves.copy(deep=True)
        if curves is not None:
            supplied = normalize_curves(curves)
            overrides: list[pd.DataFrame] = []
            for cohort_id in cohort_ids:
                cohort = self.cohorts.loc[self.cohorts["cohort_id"].eq(cohort_id)].iloc[0]
                base = select_curve(curve_catalog, cohort)
                scoped = supplied.loc[supplied["cohort_id"].eq(cohort_id)]
                patch = scoped if not scoped.empty else supplied.loc[
                    supplied["curve_id"].eq(cohort["curve_id"])
                    & supplied["cohort_id"].isna()
                ]
                if patch.empty:
                    raise SchemaError(
                        f"Updated curves do not define curve {cohort['curve_id']!r} "
                        f"for cohort {cohort_id!r}."
                    )
                patch_keys = pd.MultiIndex.from_frame(patch[["age", "component"]])
                base_keys = pd.MultiIndex.from_frame(base[["age", "component"]])
                override = pd.concat(
                    [base.loc[~base_keys.isin(patch_keys)], patch],
                    ignore_index=True,
                    sort=False,
                )
                override["cohort_id"] = cohort_id
                overrides.append(override)
            replacement = pd.concat(overrides, ignore_index=True)
            remove = curve_catalog["cohort_id"].isin(cohort_ids) & curve_catalog["curve_id"].isin(
                replacement["curve_id"].unique()
            )
            curve_catalog = pd.concat(
                [curve_catalog.loc[~remove], replacement], ignore_index=True, sort=False
            )
            curve_catalog = normalize_curves(curve_catalog)

        selected = self.cohorts.loc[self.cohorts["cohort_id"].isin(cohort_ids)]
        replacement_rows = _broadcast_many(selected, curve_catalog, first, last, self.axis)
        remove_projection = self.projections["cohort_id"].isin(cohort_ids) & self.projections[
            "period"
        ].between(first, last)
        projections = pd.concat(
            [self.projections.loc[~remove_projection], replacement_rows],
            ignore_index=True,
            sort=False,
        )
        projections = _sort_contributions(projections)
        return replace(self, curves=curve_catalog, projections=projections)

    def advance(
        self,
        *,
        observations: pd.DataFrame | None = None,
        acquisition_spend: pd.DataFrame | None = None,
        cohorts: pd.DataFrame | None = None,
        curves: pd.DataFrame | None = None,
        extend: bool = True,
    ) -> "ForecastResult":
        """Move the forecast cursor forward exactly one daily period."""

        next_cursor = self.axis.add(self.cursor, 1)
        next_end = self.axis.add(self.forecast_end, 1) if extend else self.forecast_end
        if next_cursor > next_end:
            raise TimeAxisError("Cannot advance the cursor past forecast_end.")

        new_observations = normalize_observations(observations, self.axis)
        _require_delta_period(new_observations, "period", next_cursor, "observations")
        new_spend = normalize_spend(acquisition_spend, self.axis)
        _require_delta_period(new_spend, "period", next_cursor, "acquisition_spend")

        cohort_catalog = self.cohorts.copy(deep=True)
        new_cohorts = pd.DataFrame(columns=self.cohorts.columns)
        if cohorts is not None:
            new_cohorts = normalize_cohorts(cohorts, self.axis)
            _require_delta_period(new_cohorts, "acquisition_period", next_cursor, "cohorts")
            cohort_catalog = merge_rows(
                cohort_catalog, new_cohorts, ["cohort_id"], "cohorts"
            )

        curve_catalog = self.curves.copy(deep=True)
        if curves is not None:
            new_curves = normalize_curves(curves)
            curve_keys = ["curve_id", "cohort_id", "age", "component"]
            comparable_existing = curve_catalog.assign(
                cohort_id=curve_catalog["cohort_id"].fillna("__global__")
            )
            comparable_new = new_curves.assign(cohort_id=new_curves["cohort_id"].fillna("__global__"))
            existing_keys = set(map(tuple, comparable_existing[curve_keys].to_numpy()))
            new_keys = set(map(tuple, comparable_new[curve_keys].to_numpy()))
            overlap = existing_keys & new_keys
            if overlap:
                raise SchemaError(
                    "advance only accepts new curve rows; use result.broadcast(...) to revise a curve."
                )
            curve_catalog = normalize_curves(
                pd.concat([curve_catalog, new_curves], ignore_index=True, sort=False)
            )

        added_projections: list[pd.DataFrame] = []
        old_cohorts = cohort_catalog.loc[~cohort_catalog["cohort_id"].isin(new_cohorts["cohort_id"])]
        if extend:
            added_projections.append(
                _broadcast_many(old_cohorts, curve_catalog, next_end, next_end, self.axis)
            )
        if not new_cohorts.empty:
            added_projections.append(
                _broadcast_many(new_cohorts, curve_catalog, next_cursor, next_end, self.axis)
            )
        projections = self.projections.copy(deep=True)
        nonempty_projections = [frame for frame in added_projections if not frame.empty]
        if nonempty_projections:
            projections = pd.concat(
                [projections, *nonempty_projections], ignore_index=True, sort=False
            )
            projections = _sort_contributions(projections)

        observation_catalog = merge_rows(
            self.observations,
            new_observations,
            ["cohort_id", "period", "component"],
            "observations",
        )
        if acquisition_spend is None:
            spend_catalog = self.acquisition_spend.copy(deep=True)
        else:
            spend_catalog = self.acquisition_spend.loc[
                ~self.acquisition_spend["period"].eq(next_cursor)
            ].copy(deep=True)
            if not new_spend.empty:
                spend_catalog = pd.concat(
                    [spend_catalog, new_spend], ignore_index=True, sort=False
                )
        return ForecastResult(
            cohorts=cohort_catalog,
            curves=curve_catalog,
            projections=projections,
            observations=observation_catalog,
            acquisition_spend=spend_catalog,
            start=self.start,
            cursor=next_cursor,
            forecast_end=next_end,
            axis=self.axis,
        )

    def to_xlsx(self, path: str) -> None:
        """Write canonical result DataFrames to an XLSX workbook."""

        try:
            with pd.ExcelWriter(path) as writer:
                self.contributions.to_excel(writer, sheet_name="Contributions", index=False)
                self.timeline().to_excel(writer, sheet_name="Marketing PnL", index=False)
                self.metrics().to_excel(writer, sheet_name="Metrics", index=False)
        except ImportError as exc:
            raise ImportError("Writing XLSX files requires the optional 'excel' dependencies.") from exc


def forecast(
    cohorts: pd.DataFrame | SourceFrames,
    curves: pd.DataFrame | None = None,
    *,
    observations: pd.DataFrame | None = None,
    acquisition_spend: pd.DataFrame | None = None,
    as_of: Any | None = None,
    forecast_end: Any | None = None,
    start: Any | None = None,
) -> ForecastResult:
    """Create a forecast from canonical source DataFrames."""

    if isinstance(cohorts, SourceFrames):
        if curves is not None or observations is not None or acquisition_spend is not None:
            raise SchemaError("Pass either SourceFrames or individual source DataFrames, not both.")
        source = cohorts
        cohorts = source.cohorts
        curves = source.curves
        observations = source.observations
        acquisition_spend = source.acquisition_spend
    if not isinstance(cohorts, pd.DataFrame) or curves is None:
        raise SchemaError("forecast requires cohorts and curves DataFrames.")
    if forecast_end is None:
        raise TimeAxisError("forecast_end is required.")
    if "acquisition_period" not in cohorts:
        raise SchemaError("cohorts is missing required column 'acquisition_period'.")

    period_values: list[Any] = list(cohorts["acquisition_period"])
    period_values.append(forecast_end)
    if start is not None:
        period_values.append(start)
    if as_of is not None:
        period_values.append(as_of)
    if isinstance(observations, pd.DataFrame) and "period" in observations:
        period_values.extend(observations["period"].tolist())
    if isinstance(acquisition_spend, pd.DataFrame) and "period" in acquisition_spend:
        period_values.extend(acquisition_spend["period"].tolist())
    axis = infer_time_axis(period_values)

    cohort_frame = normalize_cohorts(cohorts, axis)
    curve_frame = normalize_curves(curves)
    observation_frame = normalize_observations(observations, axis)
    spend_frame = normalize_spend(acquisition_spend, axis)
    first = (
        min(cohort_frame["acquisition_period"])
        if start is None
        else axis.normalize(start)
    )
    last = axis.normalize(forecast_end)
    cursor = first if as_of is None else axis.normalize(as_of)
    if last < first:
        raise TimeAxisError("forecast_end must be on or after start.")
    if cursor < first or cursor > last:
        raise TimeAxisError("as_of must fall within the forecast timeline.")
    if not observation_frame.empty and (observation_frame["period"] > cursor).any():
        raise SchemaError("observations cannot be later than as_of.")
    if not observation_frame.empty and (observation_frame["period"] < first).any():
        raise SchemaError("observations cannot be earlier than forecast start.")
    if not spend_frame.empty and (
        (spend_frame["period"] < first) | (spend_frame["period"] > last)
    ).any():
        raise SchemaError("acquisition_spend periods must fall within the forecast timeline.")
    if (cohort_frame["acquisition_period"] > last).any():
        raise SchemaError("cohorts cannot begin after forecast_end.")

    projections = _broadcast_many(cohort_frame, curve_frame, first, last, axis)
    result = ForecastResult(
        cohorts=cohort_frame,
        curves=curve_frame,
        projections=projections,
        observations=observation_frame,
        acquisition_spend=spend_frame,
        start=first,
        cursor=cursor,
        forecast_end=last,
        axis=axis,
    )
    # Resolve observations now so schema/category errors fail at construction time.
    _ = result.contributions
    return result


def advance(state: ForecastResult, **kwargs: Any) -> ForecastResult:
    """Functional form of :meth:`ForecastResult.advance`."""

    if not isinstance(state, ForecastResult):
        raise TypeError("advance expects a ForecastResult state.")
    return state.advance(**kwargs)


def _broadcast_many(
    cohorts: pd.DataFrame,
    curves: pd.DataFrame,
    start: Any,
    end: Any,
    axis: TimeAxis,
) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for _, cohort in cohorts.iterrows():
        pieces.append(
            broadcast_cohort(
                cohort,
                select_curve(curves, cohort),
                start=start,
                end=end,
                axis=axis,
            )
        )
    if not pieces:
        return pd.DataFrame(columns=CONTRIBUTION_COLUMNS)
    return _sort_contributions(pd.concat(pieces, ignore_index=True, sort=False))


def _overlay_observations(
    projections: pd.DataFrame,
    observations: pd.DataFrame,
    cohorts: pd.DataFrame,
    curves: pd.DataFrame,
    axis: TimeAxis,
) -> pd.DataFrame:
    if observations.empty:
        return _sort_contributions(projections.copy(deep=True))
    keys = ["cohort_id", "period", "component"]
    projection_index = projections.set_index(keys, drop=False)
    cohort_index = cohorts.set_index("cohort_id", drop=False)
    rows: list[dict[str, Any]] = []
    for _, observation in observations.iterrows():
        cohort_id = observation["cohort_id"]
        if cohort_id not in cohort_index.index:
            raise SchemaError(f"Observation references unknown cohort {cohort_id!r}.")
        cohort = cohort_index.loc[cohort_id]
        if observation["period"] < cohort["acquisition_period"]:
            raise SchemaError(
                f"Observation for cohort {cohort_id!r} cannot precede its acquisition period."
            )
        key = (cohort_id, observation["period"], observation["component"])
        projected = projection_index.loc[key] if key in projection_index.index else None
        if isinstance(projected, pd.DataFrame):
            projected = projected.iloc[0]
        category = observation.get("category", pd.NA)
        if pd.isna(category):
            if projected is None:
                raise SchemaError(
                    "An observation without a matching projection must provide category: "
                    f"{key!r}."
                )
            category = projected["category"]
        amount = float(observation["amount"])
        if category == "cost" and amount < 0:
            raise SchemaError("Observed cost amounts must be non-negative.")
        population = float(cohort["population"])
        selected_curve = select_curve(curves, cohort)
        version = (
            projected["curve_version"]
            if projected is not None
            else selected_curve["curve_version"].iloc[0]
        )
        row = {
            "cohort_id": cohort_id,
            "acquisition_period": cohort["acquisition_period"],
            "period": observation["period"],
            "age": axis.age(cohort["acquisition_period"], observation["period"]),
            "component": observation["component"],
            "category": category,
            "source_value": (
                projected["source_value"]
                if projected is not None
                else amount / population if population else np.nan
            ),
            "value_per_user": amount / population if population else np.nan,
            "value_basis": (
                projected["value_basis"] if projected is not None else "per_original_user"
            ),
            "driver_component": (
                projected["driver_component"] if projected is not None else pd.NA
            ),
            "driver_curve_version": (
                projected["driver_curve_version"] if projected is not None else pd.NA
            ),
            "amount": amount,
            "pnl_amount": pnl_amount(str(category), amount),
            "basis": "observed",
            "curve_id": cohort["curve_id"],
            "curve_version": version,
        }
        for column in cohorts.columns:
            if column not in row and column not in {"population"}:
                row[column] = cohort[column]
        rows.append(row)
    observed = pd.DataFrame(rows)
    observed_keys = pd.MultiIndex.from_frame(observed[keys])
    projected_keys = pd.MultiIndex.from_frame(projections[keys])
    unresolved = projections.loc[~projected_keys.isin(observed_keys)]
    return _sort_contributions(
        pd.concat([unresolved, observed], ignore_index=True, sort=False)
    )


def _sort_contributions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.reset_index(drop=True)
    return frame.sort_values(["period", "cohort_id", "component"], kind="stable").reset_index(
        drop=True
    )


def _require_delta_period(
    frame: pd.DataFrame,
    column: str,
    expected: Any,
    name: str,
) -> None:
    if not frame.empty and not frame[column].eq(expected).all():
        raise SchemaError(f"Every {name}.{column} passed to advance must equal {expected!r}.")
