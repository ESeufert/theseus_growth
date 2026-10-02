"""CSV adapters for canonical source DataFrames."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from ..exceptions import SchemaError
from ..frames import SourceFrames


DEFAULT_FILES = {
    "cohorts": "cohorts.csv",
    "curves": "curves.csv",
    "observations": "observations.csv",
    "acquisition_spend": "acquisition_spend.csv",
}


def read_csv(path: str | Path, **kwargs: object) -> pd.DataFrame:
    """Read one CSV file into a DataFrame without imposing storage behavior."""

    return pd.read_csv(path, **kwargs)


def read_csv_directory(
    directory: str | Path,
    *,
    file_map: Mapping[str, str] | None = None,
    **kwargs: object,
) -> SourceFrames:
    """Read a directory of canonical CSV files into :class:`SourceFrames`."""

    root = Path(directory)
    names = {**DEFAULT_FILES, **dict(file_map or {})}
    required = ("cohorts", "curves")
    missing = [name for name in required if not (root / names[name]).is_file()]
    if missing:
        raise SchemaError(
            f"CSV source is missing required files for {missing!r} in {str(root)!r}."
        )

    def optional(name: str) -> pd.DataFrame:
        path = root / names[name]
        return pd.read_csv(path, **kwargs) if path.is_file() else pd.DataFrame()

    return SourceFrames(
        cohorts=pd.read_csv(root / names["cohorts"], **kwargs),
        curves=pd.read_csv(root / names["curves"], **kwargs),
        observations=optional("observations"),
        acquisition_spend=optional("acquisition_spend"),
    )


def write_csv_directory(
    frames: SourceFrames,
    directory: str | Path,
    *,
    file_map: Mapping[str, str] | None = None,
) -> None:
    """Write source DataFrames to a directory of canonical CSV files."""

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    names = {**DEFAULT_FILES, **dict(file_map or {})}
    for name in DEFAULT_FILES:
        frame = getattr(frames, name)
        if name in {"cohorts", "curves"} or not frame.empty:
            frame.to_csv(root / names[name], index=False)
