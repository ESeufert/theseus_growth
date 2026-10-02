"""Public DataFrame containers and schema normalization for Theseus V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from .exceptions import SchemaError
from .time import TimeAxis, normalize_period_columns


COHORT_COLUMNS = ("cohort_id", "acquisition_period", "population", "curve_id")
CURVE_COLUMNS = ("curve_id", "age", "component", "category", "value")
OBSERVATION_COLUMNS = ("cohort_id", "period", "component", "amount")
SPEND_COLUMNS = ("period", "amount")
CATEGORIES = frozenset({"revenue", "cost", "contribution", "activity"})
VALUE_BASES = frozenset({"per_original_user", "per_active_user"})


@dataclass(frozen=True)
class SourceFrames:
    """The source DataFrames consumed by :func:`theseus_growth.forecast`."""

    cohorts: pd.DataFrame
    curves: pd.DataFrame
    observations: pd.DataFrame = field(default_factory=pd.DataFrame)
    acquisition_spend: pd.DataFrame = field(default_factory=pd.DataFrame)

    def copy(self) -> "SourceFrames":
        """Return an independent deep copy of every source DataFrame."""

        return SourceFrames(
            cohorts=self.cohorts.copy(deep=True),
            curves=self.curves.copy(deep=True),
            observations=self.observations.copy(deep=True),
            acquisition_spend=self.acquisition_spend.copy(deep=True),
        )


def normalize_cohorts(frame: pd.DataFrame, axis: TimeAxis) -> pd.DataFrame:
    result = _as_frame(frame, "cohorts")
    _require_columns(result, COHORT_COLUMNS, "cohorts")
    result = normalize_period_columns(result, ["acquisition_period"], axis)
    if result["cohort_id"].isna().any():
        raise SchemaError("cohorts.cohort_id cannot contain missing values.")
    if result["cohort_id"].duplicated().any():
        duplicates = result.loc[result["cohort_id"].duplicated(), "cohort_id"].tolist()
        raise SchemaError(f"cohorts.cohort_id must be unique; duplicates: {duplicates!r}.")
    result["population"] = _numeric(result["population"], "cohorts.population")
    if (result["population"] < 0).any():
        raise SchemaError("cohorts.population cannot be negative.")
    if result["curve_id"].isna().any():
        raise SchemaError("cohorts.curve_id cannot contain missing values.")
    return result.reset_index(drop=True)


def normalize_curves(frame: pd.DataFrame) -> pd.DataFrame:
    result = _as_frame(frame, "curves")
    _require_columns(result, CURVE_COLUMNS, "curves")
    if result.empty:
        raise SchemaError("curves must contain at least one row.")
    result["age"] = _numeric(result["age"], "curves.age")
    if not np.all(np.equal(result["age"], np.floor(result["age"]))):
        raise SchemaError("curves.age must contain whole-number ages.")
    result["age"] = result["age"].astype(int)
    if (result["age"] < 0).any():
        raise SchemaError("curves.age cannot be negative.")
    result["value"] = _numeric(result["value"], "curves.value")
    if result[["curve_id", "component", "category"]].isna().any().any():
        raise SchemaError("curves curve_id, component, and category cannot be missing.")
    invalid = sorted(set(result["category"].astype(str)) - CATEGORIES)
    if invalid:
        raise SchemaError(
            f"curves.category contains unsupported values {invalid!r}; expected {sorted(CATEGORIES)!r}."
        )
    result["category"] = result["category"].astype(str)
    if "value_basis" not in result:
        result["value_basis"] = "per_original_user"
    result["value_basis"] = result["value_basis"].fillna("per_original_user").astype(str)
    invalid_bases = sorted(set(result["value_basis"]) - VALUE_BASES)
    if invalid_bases:
        raise SchemaError(
            f"curves.value_basis contains unsupported values {invalid_bases!r}; "
            f"expected {sorted(VALUE_BASES)!r}."
        )
    if (
        result["category"].eq("activity")
        & result["value_basis"].eq("per_active_user")
    ).any():
        raise SchemaError("Activity components cannot use the per_active_user value basis.")
    if "driver_component" not in result:
        result["driver_component"] = pd.NA
    active_basis = result["value_basis"].eq("per_active_user")
    result.loc[active_basis & result["driver_component"].isna(), "driver_component"] = "retention"
    if result.loc[active_basis, "driver_component"].isna().any():
        raise SchemaError("per_active_user rows require a driver_component.")
    if (result.loc[result["category"].eq("cost"), "value"] < 0).any():
        raise SchemaError("Cost curve values must be non-negative.")
    if "curve_version" not in result:
        result["curve_version"] = 1
    if "cohort_id" not in result:
        result["cohort_id"] = pd.NA
    comparable = result.assign(_cohort_key=result["cohort_id"].fillna("__global__"))
    duplicate_keys = ["curve_id", "_cohort_key", "age", "component"]
    if comparable.duplicated(duplicate_keys).any():
        raise SchemaError(
            "curves must have at most one row per curve_id, cohort_id, age, and component."
        )
    return result.reset_index(drop=True)


def normalize_observations(
    frame: pd.DataFrame | None,
    axis: TimeAxis,
) -> pd.DataFrame:
    if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty and len(frame.columns) == 0):
        return pd.DataFrame(columns=list(OBSERVATION_COLUMNS) + ["category"])
    result = _as_frame(frame, "observations")
    _require_columns(result, OBSERVATION_COLUMNS, "observations")
    result = normalize_period_columns(result, ["period"], axis)
    result["amount"] = _numeric(result["amount"], "observations.amount")
    if result[["cohort_id", "component"]].isna().any().any():
        raise SchemaError("observations cohort_id and component cannot be missing.")
    if "category" in result:
        invalid = sorted(set(result["category"].dropna().astype(str)) - CATEGORIES)
        if invalid:
            raise SchemaError(f"observations.category contains unsupported values {invalid!r}.")
    else:
        result["category"] = pd.NA
    if result.duplicated(["cohort_id", "period", "component"]).any():
        raise SchemaError(
            "observations must have at most one row per cohort_id, period, and component."
        )
    return result.reset_index(drop=True)


def normalize_spend(frame: pd.DataFrame | None, axis: TimeAxis) -> pd.DataFrame:
    if frame is None or (isinstance(frame, pd.DataFrame) and frame.empty and len(frame.columns) == 0):
        return pd.DataFrame(columns=list(SPEND_COLUMNS))
    result = _as_frame(frame, "acquisition_spend")
    _require_columns(result, SPEND_COLUMNS, "acquisition_spend")
    result = normalize_period_columns(result, ["period"], axis)
    result["amount"] = _numeric(result["amount"], "acquisition_spend.amount")
    if (result["amount"] < 0).any():
        raise SchemaError("acquisition_spend.amount must be non-negative.")
    return result.reset_index(drop=True)


def select_curve(curves: pd.DataFrame, cohort: pd.Series) -> pd.DataFrame:
    """Select a cohort-scoped override when present, otherwise its global curve."""

    matching_id = curves["curve_id"].eq(cohort["curve_id"])
    scoped = curves.loc[matching_id & curves["cohort_id"].eq(cohort["cohort_id"])]
    selected = scoped if not scoped.empty else curves.loc[matching_id & curves["cohort_id"].isna()]
    if selected.empty:
        raise SchemaError(
            f"No curve {cohort['curve_id']!r} is available for cohort {cohort['cohort_id']!r}."
        )
    return selected.copy(deep=True)


def merge_rows(
    existing: pd.DataFrame,
    additions: pd.DataFrame,
    keys: Iterable[str],
    name: str,
) -> pd.DataFrame:
    """Append new unique rows, rejecting conflicting duplicates."""

    if additions.empty:
        return existing.copy(deep=True)
    combined = pd.concat([existing, additions], ignore_index=True, sort=False)
    keys = list(keys)
    if combined.duplicated(keys).any():
        duplicates = combined.loc[combined.duplicated(keys, keep=False), keys]
        raise SchemaError(f"{name} contains duplicate keys after advance:\n{duplicates.to_string(index=False)}")
    return combined


def _as_frame(value: pd.DataFrame, name: str) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise SchemaError(f"{name} must be a pandas DataFrame.")
    return value.copy(deep=True)


def _require_columns(frame: pd.DataFrame, required: Iterable[str], name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SchemaError(f"{name} is missing required columns: {missing!r}.")


def _numeric(series: pd.Series, name: str) -> pd.Series:
    try:
        result = pd.to_numeric(series, errors="raise")
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"{name} must be numeric.") from exc
    if result.isna().any() or not np.isfinite(result.astype(float)).all():
        raise SchemaError(f"{name} must contain finite, non-missing values.")
    return result
