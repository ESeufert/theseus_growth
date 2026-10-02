"""Atomic cohort broadcasting."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

import pandas as pd

from .exceptions import BroadcastError, SchemaError
from .frames import normalize_curves
from .time import TimeAxis, infer_time_axis


CONTRIBUTION_COLUMNS = [
    "cohort_id",
    "acquisition_period",
    "period",
    "age",
    "component",
    "category",
    "source_value",
    "value_per_user",
    "value_basis",
    "driver_component",
    "driver_curve_version",
    "amount",
    "pnl_amount",
    "basis",
    "curve_id",
    "curve_version",
]


def broadcast(
    cohort: pd.Series | pd.DataFrame | Mapping[str, Any],
    curve: pd.DataFrame,
    *,
    start: Any | None = None,
    end: Any | None = None,
    axis: TimeAxis | None = None,
) -> pd.DataFrame:
    """Broadcast one cohort curve onto an inclusive portion of a daily timeline.

    ``curve.value`` is a per-original-user, per-period quantity. Each emitted
    ``amount`` is therefore ``cohort.population * curve.value``. Age zero aligns
    exactly to ``cohort.acquisition_period``.
    """

    cohort_row = _cohort_series(cohort)
    required = {"cohort_id", "acquisition_period", "population", "curve_id"}
    missing = sorted(required - set(cohort_row.index))
    if missing:
        raise BroadcastError(f"cohort is missing required fields: {missing!r}.")
    try:
        population = float(cohort_row["population"])
    except (TypeError, ValueError) as exc:
        raise BroadcastError("cohort.population must be numeric.") from exc
    if not isfinite(population) or population < 0:
        raise BroadcastError("cohort.population must be finite and non-negative.")
    if pd.isna(cohort_row["cohort_id"]) or pd.isna(cohort_row["curve_id"]):
        raise BroadcastError("cohort_id and curve_id cannot be missing.")

    normalized_curve = normalize_curves(curve)
    curve_ids = normalized_curve["curve_id"].drop_duplicates().tolist()
    if curve_ids != [cohort_row["curve_id"]]:
        raise BroadcastError(
            "The atomic broadcast curve must contain exactly the cohort's curve_id "
            f"{cohort_row['curve_id']!r}; received {curve_ids!r}."
        )
    scoped_ids = normalized_curve["cohort_id"].dropna().drop_duplicates().tolist()
    if scoped_ids and scoped_ids != [cohort_row["cohort_id"]]:
        raise BroadcastError(
            "A cohort-scoped curve can only be broadcast onto its matching cohort_id."
        )
    if scoped_ids:
        normalized_curve = normalized_curve.loc[
            normalized_curve["cohort_id"].eq(cohort_row["cohort_id"])
        ].copy()

    if axis is None:
        candidates = [cohort_row["acquisition_period"]]
        if start is not None:
            candidates.append(start)
        if end is not None:
            candidates.append(end)
        axis = infer_time_axis(candidates)
    acquisition_period = axis.normalize(cohort_row["acquisition_period"])
    first = acquisition_period if start is None else axis.normalize(start)
    curve_end = axis.add(acquisition_period, int(normalized_curve["age"].max()))
    last = curve_end if end is None else axis.normalize(end)
    if last < first:
        raise BroadcastError("The broadcast end must be on or after its start.")

    output = normalized_curve.copy(deep=True)
    output["period"] = output["age"].map(lambda age: axis.add(acquisition_period, int(age)))
    output = output.loc[output["period"].between(first, last)].copy()

    extra_fields = [
        column
        for column in cohort_row.index
        if column not in {"cohort_id", "acquisition_period", "population", "curve_id"}
        and column not in CONTRIBUTION_COLUMNS
        and column not in output.columns
    ]
    result = pd.DataFrame(index=output.index)
    result["cohort_id"] = cohort_row["cohort_id"]
    result["acquisition_period"] = acquisition_period
    result["period"] = output["period"]
    result["age"] = output["age"].astype(int)
    result["component"] = output["component"].values
    result["category"] = output["category"].values
    effective_values: list[float] = []
    driver_versions: list[Any] = []
    for _, curve_row in output.iterrows():
        source_value = float(curve_row["value"])
        if curve_row["value_basis"] == "per_active_user":
            driver = normalized_curve.loc[
                normalized_curve["age"].eq(curve_row["age"])
                & normalized_curve["component"].eq(curve_row["driver_component"])
                & normalized_curve["category"].eq("activity")
            ]
            if len(driver) != 1:
                raise BroadcastError(
                    f"Curve {cohort_row['curve_id']!r} needs exactly one activity driver "
                    f"{curve_row['driver_component']!r} at age {curve_row['age']}."
                )
            driver_value = float(driver.iloc[0]["value"])
            if driver_value < 0 or driver_value > 1:
                raise BroadcastError("per_active_user driver values must be between 0 and 1.")
            effective_values.append(source_value * driver_value)
            driver_versions.append(driver.iloc[0]["curve_version"])
        else:
            effective_values.append(source_value)
            driver_versions.append(pd.NA)
    result["source_value"] = output["value"].astype(float).values
    result["value_per_user"] = effective_values
    result["value_basis"] = output["value_basis"].values
    result["driver_component"] = output["driver_component"].values
    result["driver_curve_version"] = driver_versions
    result["amount"] = population * result["value_per_user"]
    result["pnl_amount"] = [
        _pnl_amount(category, amount)
        for category, amount in zip(result["category"], result["amount"])
    ]
    result["basis"] = "projected"
    result["curve_id"] = cohort_row["curve_id"]
    result["curve_version"] = output["curve_version"].values
    for column in extra_fields:
        result[column] = cohort_row[column]

    columns = CONTRIBUTION_COLUMNS + extra_fields
    if result.empty:
        return pd.DataFrame(columns=columns)
    return result.loc[:, columns].sort_values(["period", "component"]).reset_index(drop=True)


def cumulative_to_incremental(curves: pd.DataFrame) -> pd.DataFrame:
    """Convert cumulative per-user curves to incremental daily curve values.

    All columns other than ``age`` and ``value`` identify a separate curve series.
    Cumulative values must not decrease within a series.
    """

    normalized = normalize_curves(curves)
    group_columns = [column for column in normalized.columns if column not in {"age", "value"}]
    pieces: list[pd.DataFrame] = []
    grouper: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
    for _, group in normalized.groupby(grouper, dropna=False, sort=False):
        ordered = group.sort_values("age").copy()
        increments = ordered["value"].diff()
        increments.iloc[0] = ordered["value"].iloc[0]
        if (increments < -1e-12).any():
            raise SchemaError("Cumulative curve values cannot decrease with age.")
        ordered["value"] = increments.clip(lower=0).astype(float)
        pieces.append(ordered)
    return pd.concat(pieces, ignore_index=True).sort_values(group_columns + ["age"]).reset_index(drop=True)


def pnl_amount(category: str, amount: float) -> float:
    """Return the signed P&L effect for a canonical contribution category."""

    return _pnl_amount(category, amount)


def _pnl_amount(category: str, amount: float) -> float:
    if category == "cost":
        return -abs(float(amount))
    if category in {"revenue", "contribution"}:
        return float(amount)
    return 0.0


def _cohort_series(
    cohort: pd.Series | pd.DataFrame | Mapping[str, Any],
) -> pd.Series:
    if isinstance(cohort, pd.Series):
        return cohort.copy(deep=True)
    if isinstance(cohort, pd.DataFrame):
        if len(cohort) != 1:
            raise BroadcastError("An atomic broadcast requires exactly one cohort row.")
        return cohort.iloc[0].copy(deep=True)
    if isinstance(cohort, Mapping):
        return pd.Series(dict(cohort))
    raise BroadcastError("cohort must be a Series, one-row DataFrame, or mapping.")
