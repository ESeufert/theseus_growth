"""Interchangeable source abstractions for materializing DataFrames."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

import pandas as pd

from ..exceptions import SchemaError
from ..frames import SourceFrames
from .csv import read_csv_directory
from .xlsx import read_xlsx


@runtime_checkable
class DataFrameSource(Protocol):
    """A minimal boundary for anything that materializes source DataFrames."""

    def load(self) -> SourceFrames: ...


@dataclass(frozen=True)
class XlsxSource:
    path: str | Path
    sheet_map: Mapping[str, str] | None = None

    def load(self) -> SourceFrames:
        return read_xlsx(self.path, sheet_map=self.sheet_map)


@dataclass(frozen=True)
class CsvSource:
    directory: str | Path
    file_map: Mapping[str, str] | None = None
    read_options: Mapping[str, Any] = field(default_factory=dict)

    def load(self) -> SourceFrames:
        return read_csv_directory(
            self.directory,
            file_map=self.file_map,
            **dict(self.read_options),
        )


@dataclass(frozen=True)
class DatabaseSource:
    """Read-only query adapter for a caller-owned DB-API or SQLAlchemy connection.

    Theseus neither opens nor owns the connection and performs no writes. Query
    strings and parameters remain entirely under caller control.
    """

    connection: Any
    queries: Mapping[str, str]
    params: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def load(self) -> SourceFrames:
        required = {"cohorts", "curves"}
        missing = sorted(required - set(self.queries))
        if missing:
            raise SchemaError(f"DatabaseSource is missing queries for {missing!r}.")

        def query(name: str) -> pd.DataFrame:
            sql = self.queries.get(name)
            if sql is None:
                return pd.DataFrame()
            return pd.read_sql_query(sql, self.connection, params=self.params.get(name))

        return SourceFrames(
            cohorts=query("cohorts"),
            curves=query("curves"),
            observations=query("observations"),
            acquisition_spend=query("acquisition_spend"),
        )


def load_source(source: DataFrameSource) -> SourceFrames:
    """Materialize and defensively copy frames from a source implementation."""

    if not isinstance(source, DataFrameSource):
        raise TypeError("source must implement load() -> SourceFrames.")
    frames = source.load()
    if not isinstance(frames, SourceFrames):
        raise TypeError("DataFrameSource.load() must return SourceFrames.")
    return frames.copy()
