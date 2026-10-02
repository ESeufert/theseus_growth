"""XLSX adapters for canonical source DataFrames."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from ..exceptions import SchemaError
from ..frames import (
    SourceFrames,
    normalize_cohorts,
    normalize_curves,
    normalize_observations,
    normalize_spend,
)
from ..time import infer_time_axis


DEFAULT_SHEETS = {
    "cohorts": "Cohorts",
    "curves": "Curves",
    "observations": "Observations",
    "acquisition_spend": "Acquisition Spend",
}


def read_xlsx(
    path: str | Path,
    *,
    sheet_map: Mapping[str, str] | None = None,
    schema: str = "theseus",
) -> SourceFrames:
    """Read canonical workbook sheets into source DataFrames.

    Formulas are read as values supplied by the workbook engine; Theseus does not
    evaluate spreadsheet formulas.
    """

    if schema != "theseus":
        raise SchemaError("Only the canonical 'theseus' XLSX schema is supported in V1.")
    names = {**DEFAULT_SHEETS, **dict(sheet_map or {})}
    try:
        with pd.ExcelFile(path) as workbook:
            missing = [
                names[name]
                for name in ("cohorts", "curves")
                if names[name] not in workbook.sheet_names
            ]
            if missing:
                raise SchemaError(f"Workbook is missing required sheets: {missing!r}.")

            def read(name: str, required: bool = False) -> pd.DataFrame:
                sheet = names[name]
                if sheet not in workbook.sheet_names:
                    return pd.DataFrame()
                frame = pd.read_excel(workbook, sheet_name=sheet)
                if frame.columns.duplicated().any():
                    raise SchemaError(f"Sheet {sheet!r} contains duplicate column headers.")
                if required and frame.empty:
                    raise SchemaError(f"Sheet {sheet!r} cannot be empty.")
                return frame.dropna(how="all").reset_index(drop=True)

            return SourceFrames(
                cohorts=read("cohorts", required=True),
                curves=read("curves", required=True),
                observations=read("observations"),
                acquisition_spend=read("acquisition_spend"),
            )
    except ImportError as exc:
        raise ImportError("Reading XLSX files requires the optional 'excel' dependencies.") from exc


def validate_xlsx(
    path: str | Path,
    *,
    sheet_map: Mapping[str, str] | None = None,
) -> SourceFrames:
    """Read and validate an XLSX source, returning its normalized DataFrames."""

    frames = read_xlsx(path, sheet_map=sheet_map)
    values = frames.cohorts["acquisition_period"].tolist()
    if not frames.observations.empty and "period" in frames.observations:
        values.extend(frames.observations["period"].tolist())
    if not frames.acquisition_spend.empty and "period" in frames.acquisition_spend:
        values.extend(frames.acquisition_spend["period"].tolist())
    axis = infer_time_axis(values)
    return SourceFrames(
        cohorts=normalize_cohorts(frames.cohorts, axis),
        curves=normalize_curves(frames.curves),
        observations=normalize_observations(frames.observations, axis),
        acquisition_spend=normalize_spend(frames.acquisition_spend, axis),
    )


def write_xlsx_template(path: str | Path, *, include_examples: bool = True) -> None:
    """Write a canonical input workbook template."""

    if include_examples:
        cohorts = pd.DataFrame(
            [{"cohort_id": "cohort-0", "acquisition_period": 0, "population": 100, "curve_id": "base"}]
        )
        curves = pd.DataFrame(
            [
                {"curve_id": "base", "age": 0, "component": "revenue", "category": "revenue", "value": 0.5},
                {"curve_id": "base", "age": 1, "component": "revenue", "category": "revenue", "value": 0.3},
            ]
        )
    else:
        cohorts = pd.DataFrame(columns=["cohort_id", "acquisition_period", "population", "curve_id"])
        curves = pd.DataFrame(columns=["curve_id", "age", "component", "category", "value", "curve_version"])
    observations = pd.DataFrame(columns=["cohort_id", "period", "component", "category", "amount"])
    spend = pd.DataFrame(columns=["period", "amount"])
    try:
        with pd.ExcelWriter(path) as writer:
            cohorts.to_excel(writer, sheet_name=DEFAULT_SHEETS["cohorts"], index=False)
            curves.to_excel(writer, sheet_name=DEFAULT_SHEETS["curves"], index=False)
            observations.to_excel(writer, sheet_name=DEFAULT_SHEETS["observations"], index=False)
            spend.to_excel(writer, sheet_name=DEFAULT_SHEETS["acquisition_spend"], index=False)
    except ImportError as exc:
        raise ImportError("Writing XLSX files requires the optional 'excel' dependencies.") from exc
