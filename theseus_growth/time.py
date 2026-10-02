"""Daily integer and calendar time axes used by the projection engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from numbers import Integral
from typing import Any, Iterable, Protocol

import numpy as np
import pandas as pd

from .exceptions import TimeAxisError


class TimeAxis(Protocol):
    """Protocol implemented by supported daily axes."""

    kind: str

    def normalize(self, value: Any) -> Any: ...

    def add(self, value: Any, periods: int) -> Any: ...

    def age(self, acquisition_period: Any, period: Any) -> int: ...

    def range(self, start: Any, end: Any) -> list[Any]: ...


@dataclass(frozen=True)
class IntegerDayAxis:
    """A daily axis represented by abstract integer periods."""

    kind: str = "integer"

    def normalize(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TimeAxisError(f"Expected an integer period; received {value!r}.")
        return int(value)

    def add(self, value: Any, periods: int) -> int:
        return self.normalize(value) + _normalize_step(periods)

    def age(self, acquisition_period: Any, period: Any) -> int:
        return self.normalize(period) - self.normalize(acquisition_period)

    def range(self, start: Any, end: Any) -> list[int]:
        first = self.normalize(start)
        last = self.normalize(end)
        if last < first:
            raise TimeAxisError("The end period must be on or after the start period.")
        return list(range(first, last + 1))


@dataclass(frozen=True)
class CalendarDayAxis:
    """A daily axis represented by calendar dates or timestamps."""

    kind: str = "calendar"

    def normalize(self, value: Any) -> pd.Timestamp:
        if not _is_datetime_like(value):
            raise TimeAxisError(f"Expected a calendar period; received {value!r}.")
        try:
            result = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise TimeAxisError(f"Invalid calendar period {value!r}.") from exc
        if pd.isna(result):
            raise TimeAxisError("Calendar periods cannot be missing.")
        return result.normalize()

    def add(self, value: Any, periods: int) -> pd.Timestamp:
        return self.normalize(value) + pd.DateOffset(days=_normalize_step(periods))

    def age(self, acquisition_period: Any, period: Any) -> int:
        return (self.normalize(period).date() - self.normalize(acquisition_period).date()).days

    def range(self, start: Any, end: Any) -> list[pd.Timestamp]:
        first = self.normalize(start)
        last = self.normalize(end)
        if last < first:
            raise TimeAxisError("The end period must be on or after the start period.")
        return list(pd.date_range(first, last, freq="D"))


def infer_time_axis(values: Iterable[Any]) -> TimeAxis:
    """Infer one supported axis from non-null period values.

    Integer and calendar periods may not be mixed. ISO date strings are accepted as
    calendar values, primarily to make small hand-authored DataFrames convenient.
    """

    materialized = [value for value in values if not _is_missing(value)]
    if not materialized:
        raise TimeAxisError("At least one non-missing period is required.")

    integer_flags = [_is_integer(value) for value in materialized]
    calendar_flags = [_is_datetime_like(value) for value in materialized]
    if all(integer_flags):
        return IntegerDayAxis()
    if all(calendar_flags):
        return CalendarDayAxis()
    raise TimeAxisError(
        "Periods must be either all integers or all calendar dates; mixed axes are not supported."
    )


def normalize_period_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    axis: TimeAxis,
) -> pd.DataFrame:
    """Return a copy with named period columns normalized to the selected axis."""

    result = frame.copy(deep=True)
    for column in columns:
        if column in result.columns:
            if result[column].isna().any():
                raise TimeAxisError(f"{column!r} cannot contain missing periods.")
            result[column] = result[column].map(axis.normalize)
    return result


def _is_integer(value: Any) -> bool:
    return isinstance(value, Integral) and not isinstance(value, bool)


def _is_datetime_like(value: Any) -> bool:
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        return True
    if isinstance(value, str):
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError):
            return False
        return not pd.isna(parsed)
    return False


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalize_step(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TimeAxisError("A period step must be an integer.")
    return int(value)
