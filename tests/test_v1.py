from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

import theseus_growth as tg
from theseus_growth.exceptions import SchemaError, TimeAxisError


def cohort_frame(*rows):
    return pd.DataFrame(rows, columns=["cohort_id", "acquisition_period", "population", "curve_id"])


def revenue_curve(values=(0.5, 0.3, 0.2), *, version=1):
    return pd.DataFrame(
        [
            {
                "curve_id": "base",
                "age": age,
                "component": "revenue",
                "category": "revenue",
                "value": value,
                "curve_version": version,
            }
            for age, value in enumerate(values)
        ]
    )


class BroadcastTests(unittest.TestCase):
    def test_atomic_integer_broadcast(self):
        cohort = {
            "cohort_id": "c0",
            "acquisition_period": 4,
            "population": 100,
            "curve_id": "base",
        }
        result = tg.broadcast(cohort, revenue_curve(), start=5, end=6)
        self.assertEqual(result["period"].tolist(), [5, 6])
        self.assertEqual(result["age"].tolist(), [1, 2])
        self.assertEqual(result["amount"].tolist(), [30.0, 20.0])

    def test_calendar_broadcast_matches_integer_values(self):
        integer = tg.broadcast(
            {"cohort_id": "c0", "acquisition_period": 0, "population": 100, "curve_id": "base"},
            revenue_curve(),
        )
        calendar = tg.broadcast(
            {
                "cohort_id": "c0",
                "acquisition_period": pd.Timestamp("2026-01-01"),
                "population": 100,
                "curve_id": "base",
            },
            revenue_curve(),
        )
        self.assertEqual(calendar["period"].dt.day.tolist(), [1, 2, 3])
        self.assertEqual(integer["amount"].tolist(), calendar["amount"].tolist())

    def test_mixed_time_axes_are_rejected(self):
        with self.assertRaises(TimeAxisError):
            tg.broadcast(
                {
                    "cohort_id": "c0",
                    "acquisition_period": 0,
                    "population": 100,
                    "curve_id": "base",
                },
                revenue_curve(),
                end=pd.Timestamp("2026-01-03"),
            )

    def test_cumulative_curve_is_differenced(self):
        cumulative = revenue_curve((0.5, 0.8, 1.0))
        daily = tg.cumulative_to_incremental(cumulative)
        self.assertEqual(daily["value"].round(8).tolist(), [0.5, 0.3, 0.2])

    def test_retention_drives_per_active_user_financials(self):
        curve = pd.DataFrame(
            [
                {"curve_id": "base", "age": 0, "component": "retention", "category": "activity", "value": 1.0},
                {"curve_id": "base", "age": 1, "component": "retention", "category": "activity", "value": 0.5},
                {
                    "curve_id": "base",
                    "age": 0,
                    "component": "revenue",
                    "category": "revenue",
                    "value": 0.2,
                    "value_basis": "per_active_user",
                },
                {
                    "curve_id": "base",
                    "age": 1,
                    "component": "revenue",
                    "category": "revenue",
                    "value": 0.2,
                    "value_basis": "per_active_user",
                },
            ]
        )
        projected = tg.broadcast(
            {"cohort_id": "c0", "acquisition_period": 0, "population": 100, "curve_id": "base"},
            curve,
        )
        revenue = projected.loc[projected["component"].eq("revenue")]
        self.assertEqual(revenue["amount"].tolist(), [20.0, 10.0])


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.cohorts = cohort_frame(
            ("c0", 0, 100, "base"),
            ("c1", 1, 100, "base"),
        )
        self.curves = revenue_curve()
        self.spend = pd.DataFrame([{"period": 0, "amount": 100}, {"period": 1, "amount": 100}])

    def test_golden_financial_timeline(self):
        result = tg.forecast(
            self.cohorts,
            self.curves,
            acquisition_spend=self.spend,
            as_of=1,
            forecast_end=3,
        )
        timeline = result.timeline()
        self.assertEqual(timeline["revenue"].tolist(), [50.0, 80.0, 50.0, 20.0])
        self.assertEqual(timeline["cumulative_marketing_pnl"].tolist(), [-50.0, -70.0, -20.0, 0.0])
        self.assertEqual(result.metrics().iloc[0]["break_even_period"], 3)

    def test_observed_rows_override_projections(self):
        observations = pd.DataFrame(
            [
                {"cohort_id": "c0", "period": 0, "component": "revenue", "amount": 50},
                {"cohort_id": "c0", "period": 1, "component": "revenue", "amount": 30},
                {"cohort_id": "c1", "period": 1, "component": "revenue", "amount": 50},
            ]
        )
        result = tg.forecast(
            self.cohorts,
            self.curves,
            observations=observations,
            acquisition_spend=self.spend,
            as_of=1,
            forecast_end=3,
        )
        metrics = result.metrics().iloc[0]
        self.assertEqual(metrics["recorded_contribution"], 130.0)
        self.assertEqual(metrics["projected_receivable"], 70.0)
        self.assertEqual((result.contributions["basis"] == "observed").sum(), 3)

    def test_repeated_advance_matches_full_forecast(self):
        initial = tg.forecast(
            cohort_frame(("c0", 0, 100, "base")),
            self.curves,
            acquisition_spend=pd.DataFrame([{"period": 0, "amount": 100}]),
            as_of=0,
            forecast_end=0,
        )
        day_one = initial.advance(
            cohorts=cohort_frame(("c1", 1, 100, "base")),
            acquisition_spend=pd.DataFrame([{"period": 1, "amount": 100}]),
        )
        day_two = day_one.advance()
        full = tg.forecast(
            self.cohorts,
            self.curves,
            acquisition_spend=self.spend,
            as_of=2,
            forecast_end=2,
        )
        assert_frame_equal(
            day_two.contributions.reset_index(drop=True),
            full.contributions.reset_index(drop=True),
            check_dtype=False,
        )
        assert_frame_equal(day_two.timeline(), full.timeline(), check_dtype=False)

    def test_cohort_rebroadcast_matches_full_rerun(self):
        original = tg.forecast(
            self.cohorts,
            self.curves,
            acquisition_spend=self.spend,
            as_of=1,
            forecast_end=3,
        )
        corrected = revenue_curve((0.5, 0.4, 0.25), version=2)
        updated = original.broadcast(cohorts=["c0"], curves=corrected)
        override = corrected.assign(cohort_id="c0")
        expected = tg.forecast(
            self.cohorts,
            pd.concat([self.curves, override], ignore_index=True),
            acquisition_spend=self.spend,
            as_of=1,
            forecast_end=3,
        )
        assert_frame_equal(
            updated.contributions.reset_index(drop=True),
            expected.contributions.reset_index(drop=True),
            check_dtype=False,
        )

    def test_rebroadcast_does_not_replace_observations(self):
        observations = pd.DataFrame(
            [{"cohort_id": "c0", "period": 0, "component": "revenue", "amount": 77}]
        )
        original = tg.forecast(
            self.cohorts,
            self.curves,
            observations=observations,
            as_of=1,
            forecast_end=3,
        )
        updated = original.broadcast(cohorts=["c0"], curves=revenue_curve((0.9, 0.8, 0.7)))
        actual = updated.contributions.loc[
            updated.contributions["cohort_id"].eq("c0")
            & updated.contributions["period"].eq(0)
            & updated.contributions["component"].eq("revenue")
        ].iloc[0]
        self.assertEqual(actual["basis"], "observed")
        self.assertEqual(actual["amount"], 77.0)

    def test_partial_rebroadcast_only_changes_selected_slice(self):
        original = tg.forecast(self.cohorts, self.curves, as_of=1, forecast_end=3)
        updated = original.broadcast(
            cohorts="c0",
            curves=revenue_curve((0.9, 0.8, 0.7), version=2),
            start=1,
            end=1,
        )
        c0 = updated.projections.loc[updated.projections["cohort_id"].eq("c0")]
        self.assertEqual(c0["amount"].tolist(), [50.0, 80.0, 20.0])
        self.assertEqual(c0["curve_version"].tolist(), [1, 2, 1])

    def test_retention_only_rebroadcast_recalculates_contribution(self):
        curves = pd.DataFrame(
            [
                {"curve_id": "base", "age": 0, "component": "retention", "category": "activity", "value": 1.0},
                {"curve_id": "base", "age": 1, "component": "retention", "category": "activity", "value": 0.5},
                {
                    "curve_id": "base",
                    "age": 0,
                    "component": "revenue",
                    "category": "revenue",
                    "value": 0.2,
                    "value_basis": "per_active_user",
                },
                {
                    "curve_id": "base",
                    "age": 1,
                    "component": "revenue",
                    "category": "revenue",
                    "value": 0.2,
                    "value_basis": "per_active_user",
                },
            ]
        )
        original = tg.forecast(
            cohort_frame(("c0", 0, 100, "base")),
            curves,
            as_of=0,
            forecast_end=1,
        )
        retention_patch = pd.DataFrame(
            [
                {
                    "curve_id": "base",
                    "age": 1,
                    "component": "retention",
                    "category": "activity",
                    "value": 0.8,
                    "curve_version": 2,
                }
            ]
        )
        updated = original.broadcast(cohorts=["c0"], curves=retention_patch)
        revenue = updated.contributions.loc[updated.contributions["component"].eq("revenue")]
        self.assertEqual(revenue["amount"].round(8).tolist(), [20.0, 16.0])
        self.assertEqual(revenue["driver_curve_version"].tolist(), [1, 2])

    def test_advance_replaces_planned_spend_for_new_actual_period(self):
        original = tg.forecast(
            cohort_frame(("c0", 0, 100, "base")),
            self.curves,
            acquisition_spend=pd.DataFrame(
                [{"period": 0, "amount": 100}, {"period": 1, "amount": 120}]
            ),
            as_of=0,
            forecast_end=2,
        )
        updated = original.advance(
            acquisition_spend=pd.DataFrame([{"period": 1, "amount": 90}])
        )
        period_one = updated.timeline().loc[updated.timeline()["period"].eq(1)].iloc[0]
        self.assertEqual(period_one["acquisition_spend"], 90.0)

    def test_advance_without_spend_delta_keeps_plan(self):
        original = tg.forecast(
            cohort_frame(("c0", 0, 100, "base")),
            self.curves,
            acquisition_spend=pd.DataFrame(
                [{"period": 0, "amount": 100}, {"period": 1, "amount": 120}]
            ),
            as_of=0,
            forecast_end=2,
        )
        updated = original.advance()
        period_one = updated.timeline().loc[updated.timeline()["period"].eq(1)].iloc[0]
        self.assertEqual(period_one["acquisition_spend"], 120.0)

    def test_advance_rejects_non_next_period_delta(self):
        original = tg.forecast(self.cohorts, self.curves, as_of=0, forecast_end=3)
        with self.assertRaises(SchemaError):
            original.advance(
                observations=pd.DataFrame(
                    [{"cohort_id": "c0", "period": 2, "component": "revenue", "amount": 20}]
                )
            )

    def test_calendar_advance_moves_one_day(self):
        cohorts = cohort_frame(("c0", pd.Timestamp("2026-01-01"), 100, "base"))
        original = tg.forecast(
            cohorts,
            self.curves,
            as_of=pd.Timestamp("2026-01-01"),
            forecast_end=pd.Timestamp("2026-01-03"),
        )
        updated = original.advance(extend=False)
        self.assertEqual(updated.cursor, pd.Timestamp("2026-01-02"))
        self.assertEqual(updated.forecast_end, pd.Timestamp("2026-01-03"))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.frames = tg.SourceFrames(
            cohorts=cohort_frame(("c0", 0, 100, "base")),
            curves=revenue_curve(),
            acquisition_spend=pd.DataFrame([{"period": 0, "amount": 100}]),
        )

    def test_csv_directory_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            tg.io.write_csv_directory(self.frames, directory)
            loaded = tg.io.read_csv_directory(directory)
            assert_frame_equal(loaded.cohorts, self.frames.cohorts, check_dtype=False)
            assert_frame_equal(loaded.curves, self.frames.curves, check_dtype=False)

    def test_xlsx_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inputs.xlsx"
            with pd.ExcelWriter(path) as writer:
                self.frames.cohorts.to_excel(writer, sheet_name="Cohorts", index=False)
                self.frames.curves.to_excel(writer, sheet_name="Curves", index=False)
                self.frames.acquisition_spend.to_excel(
                    writer, sheet_name="Acquisition Spend", index=False
                )
            loaded = tg.io.validate_xlsx(path)
            result = tg.forecast(loaded, as_of=0, forecast_end=2)
            self.assertEqual(result.timeline()["revenue"].tolist(), [50.0, 30.0, 20.0])

    def test_database_source_materializes_frames(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        self.frames.cohorts.to_sql("cohorts", connection, index=False)
        self.frames.curves.to_sql("curves", connection, index=False)
        source = tg.io.DatabaseSource(
            connection,
            {"cohorts": "select * from cohorts", "curves": "select * from curves"},
        )
        loaded = tg.io.load_source(source)
        self.assertEqual(loaded.cohorts["cohort_id"].tolist(), ["c0"])
        self.assertEqual(len(loaded.curves), 3)


if __name__ == "__main__":
    unittest.main()
