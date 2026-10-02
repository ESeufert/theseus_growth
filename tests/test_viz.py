"""Financial and rendering invariants for the visualization suite."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

import theseus_growth as tg


def sample(*, calendar=False, observations=True, n=21, cursor=9):
    base = pd.Timestamp("2024-01-31") if calendar else 0
    period = lambda day: base + pd.Timedelta(days=day) if calendar else day
    cohorts = pd.DataFrame([
        {"cohort_id": "A", "acquisition_period": period(0), "population": 100, "curve_id": "a"},
        {"cohort_id": "B", "acquisition_period": period(3), "population": 200, "curve_id": "b"},
    ])
    curves = pd.DataFrame([
        {"curve_id": curve_id, "age": age, "component": component,
         "category": "revenue", "value": value}
        for curve_id, value in [("a", 0.1), ("b", 0.05)]
        for age in range(n)
        for component in ["iap", "ads"]
    ])
    spend = pd.DataFrame([
        {"period": period(0), "cohort_id": "A", "amount": 100.0},
        {"period": period(3), "cohort_id": "B", "amount": 200.0},
    ])
    observed = None
    if observations:
        observed = pd.DataFrame([
            {"cohort_id": cohort_id, "period": period(day), "component": component, "amount": 10.0}
            for cohort_id, start in [("A", 0), ("B", 3)]
            for day in range(start, cursor + 1)
            for component in ["iap", "ads"]
        ])
    return tg.forecast(cohorts, curves, observations=observed, acquisition_spend=spend,
                       as_of=period(cursor), forecast_end=period(n - 1))


class ProgressionTests(unittest.TestCase):
    def test_origin_and_day_zero_revenue_are_not_conflated(self):
        data = sample().cohort_progression()
        a = data.loc[data["cohort_id"].eq("A")]
        self.assertEqual(a.iloc[0]["roas"], 0)
        self.assertEqual(a.iloc[0]["value_status"], "origin")
        self.assertEqual(a.iloc[1]["roas"], 0.2)
        self.assertEqual(a.iloc[1]["period"], 0)
        self.assertAlmostEqual(a.iloc[10]["roas"], 2.0)
        self.assertEqual(a.iloc[10]["value_status"], "observed")
        self.assertEqual(a.iloc[11]["value_status"], "projected")

    def test_weekly_samples_cumulative_sums_not_average_ratios(self):
        data = sample().cohort_progression(interval="weekly")
        a = data.loc[data["cohort_id"].eq("A")]
        b = data.loc[data["cohort_id"].eq("B")]
        np.testing.assert_allclose(a["roas"], [0, 1.4, 2.8, 4.2])
        np.testing.assert_allclose(b["roas"], [0, 0.7, 1.4])
        self.assertEqual(a["elapsed_days"].tolist(), [0, 7, 14, 21])
        self.assertEqual(b["interval_index"].max(), 2)  # no fabricated immature week 3

    def test_observed_only_never_extends_past_maturity(self):
        data = sample().cohort_progression(interval="weekly", basis="observed")
        self.assertEqual(data.groupby("cohort_id")["interval_index"].max().to_dict(), {"A": 1, "B": 1})
        self.assertEqual(set(data["value_status"]), {"origin", "observed"})

    def test_missing_actuals_do_not_turn_into_zero_or_solid_cumulative(self):
        result = sample()
        result.observations.drop(result.observations.loc[
            result.observations["cohort_id"].eq("A") & result.observations["period"].eq(2)
            & result.observations["component"].eq("ads")
        ].index, inplace=True)
        actual = result.cohort_progression(basis="observed", cohorts=["A"])
        self.assertTrue(actual.loc[actual["interval_index"].ge(3), "roas"].isna().all())
        resolved = result.cohort_progression(cohorts=["A"])
        self.assertTrue(resolved.loc[resolved["interval_index"].ge(3), "value_status"].eq("projected").all())

    def test_missing_curve_tail_is_not_extrapolated_flat(self):
        result = sample(observations=False)
        result.projections.drop(result.projections.loc[
            result.projections["cohort_id"].eq("A") & result.projections["age"].ge(14)
        ].index, inplace=True)
        data = result.cohort_progression(interval="weekly", cohorts=["A"])
        self.assertTrue(np.isnan(data.iloc[-1]["roas"]))

    def test_calendar_months_use_acquisition_anniversaries_and_no_drift(self):
        data = sample(calendar=True, n=95).cohort_progression(interval="monthly", cohorts=["A"])
        self.assertEqual(data["elapsed_days"].tolist(), [0, 29, 60, 90])
        self.assertEqual(data.iloc[1]["period"], pd.Timestamp("2024-02-28"))
        self.assertEqual(data.iloc[2]["period"], pd.Timestamp("2024-03-30"))

    def test_integer_months_rejected_but_fixed_intervals_supported(self):
        with self.assertRaises(tg.TimeAxisError):
            sample().cohort_progression(interval="monthly")
        data = sample(n=65).cohort_progression(interval=30, cohorts=["A"])
        self.assertEqual(data["elapsed_days"].tolist(), [0, 30, 60])

    def test_integer_and_calendar_progression_are_equivalent(self):
        left = sample().cohort_progression(interval="weekly").drop(columns="period")
        right = sample(calendar=True).cohort_progression(interval="weekly").drop(columns="period")
        assert_frame_equal(left, right)

    def test_calendar_days_across_daylight_saving_keep_midnight_and_age(self):
        for start in ["2024-03-08", "2024-11-01"]:
            with self.subTest(start=start):
                acquisition = pd.Timestamp(start, tz="America/New_York")
                cohorts = pd.DataFrame([{"cohort_id": "A", "acquisition_period": acquisition, "population": 100, "curve_id": "a"}])
                curves = pd.DataFrame([{"curve_id": "a", "age": age, "component": "revenue", "category": "revenue", "value": 0.1} for age in range(10)])
                result = tg.forecast(cohorts, curves,
                    acquisition_spend=pd.DataFrame([{"cohort_id": "A", "period": acquisition, "amount": 100}]),
                    as_of=acquisition, forecast_end=acquisition + pd.DateOffset(days=8))
                data = result.cohort_progression()
                np.testing.assert_allclose(data["roas"], np.arange(10) * 0.1)
                self.assertTrue(result.projections["period"].dt.hour.eq(0).all())
                self.assertEqual(result.axis.age(acquisition, acquisition + pd.DateOffset(days=4)), 4)

    def test_missing_and_zero_spend_are_undefined(self):
        result = sample()
        spend = pd.DataFrame([{"cohort_id": "A", "amount": 0.0}])
        data = result.cohort_progression(spend=spend)
        self.assertTrue(data["roas"].isna().all())

    def test_ambiguous_spend_requires_explicit_allocation(self):
        result = sample()
        result.cohorts.loc[result.cohorts["cohort_id"].eq("B"), "acquisition_period"] = 0
        result.acquisition_spend.drop(columns="cohort_id", inplace=True)
        with self.assertRaisesRegex(tg.SchemaError, "maps to 2 cohorts"):
            tg.viz.cohort_spend_data(result)
        explicit = pd.DataFrame([{"cohort_id": "A", "amount": 80}, {"cohort_id": "B", "amount": 220}])
        data = tg.viz.cohort_spend_data(result, spend=explicit)
        self.assertEqual(data["acquisition_spend"].sum(), 300)

    def test_single_cohort_attribution_infers_by_acquisition_period(self):
        result = sample()
        result.acquisition_spend.drop(columns="cohort_id", inplace=True)
        self.assertEqual(tg.viz.cohort_spend_data(result)["acquisition_spend"].tolist(), [100, 200])

    def test_roas_uses_revenue_not_profit_or_activity(self):
        result = sample()
        extras = result.projections.copy()
        extras["component"] = "cost:" + extras["component"]
        extras["category"] = "cost"
        extras["amount"] = 1000
        extras["pnl_amount"] = -1000
        from dataclasses import replace
        changed = replace(result, projections=pd.concat([result.projections, extras], ignore_index=True))
        assert_frame_equal(result.cohort_progression(), changed.cohort_progression())


class FinancialDataTests(unittest.TestCase):
    def test_summary_reconciles_and_separates_estimates(self):
        result = sample()
        data = tg.viz.cohort_summary_data(result)
        np.testing.assert_allclose(
            data["expected_revenue"],
            data[["recorded_revenue", "estimated_to_date", "projected_receivable", "planned_revenue"]].sum(axis=1),
        )
        self.assertEqual(data["recorded_revenue"].sum(), 340)
        self.assertEqual(data["projected_receivable"].sum(), 440)
        self.assertEqual(data["cpi"].tolist(), [1.0, 1.0])
        np.testing.assert_allclose(data["expected_revenue_per_user"], [4.2, 1.8])
        model = tg.viz.cohort_summary_data(sample(observations=False))
        self.assertEqual(model["recorded_revenue"].sum(), 0)
        self.assertEqual(model["estimated_to_date"].sum(), 340)

    def test_receivables_exclude_unacquired_cohorts_and_reconcile(self):
        result = sample()
        data = tg.viz.receivables_data(result)
        self.assertAlmostEqual(data.iloc[0]["projected_receivable"], 400)
        self.assertAlmostEqual(data.iloc[-1]["projected_receivable"], 0)
        at_cursor = data.loc[data["period"].eq(result.cursor)].iloc[0]
        self.assertAlmostEqual(at_cursor["projected_receivable"], 440)

    def test_break_even_ignores_leading_empty_periods(self):
        result = sample()
        from dataclasses import replace
        events = tg.viz.break_even_data(replace(result, start=-2)).set_index("event")
        self.assertGreaterEqual(events.loc["cumulative_break_even", "period"], 0)

    def test_golden_pnl_and_funding_fixture(self):
        curves = pd.DataFrame([{"curve_id": "base", "age": age, "component": "revenue", "category": "revenue", "value": value} for age, value in enumerate([.5, .3, .2])])
        cohorts = pd.DataFrame([{"cohort_id": str(i), "acquisition_period": i, "population": 100, "curve_id": "base"} for i in range(2)])
        result = tg.forecast(cohorts, curves, acquisition_spend=pd.DataFrame({"period": [0, 1], "amount": [100, 100]}), as_of=1, forecast_end=3)
        data = tg.viz.portfolio_timeline_data(result)
        np.testing.assert_allclose(data["cumulative_marketing_pnl"], [-50, -70, -20, 0])
        self.assertEqual(data["capital_at_risk"].max(), 70)
        events = tg.viz.break_even_data(result).set_index("event")
        self.assertEqual(events.loc["daily_break_even", "period"], 2)
        self.assertEqual(events.loc["cumulative_break_even", "period"], 3)


@unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Install the viz extra to run rendering tests")
class ChartTests(unittest.TestCase):
    def test_entire_suite_renders_and_exports_on_both_axes(self):
        names = ["cohort_progression", "roas_heatmap", "cumulative_monetization", "daily_monetization",
                 "recorded_vs_projected", "cohort_revenue", "revenue_vs_spend", "cumulative_revenue_vs_spend",
                 "marketing_pnl", "cumulative_pnl", "projected_receivables", "dashboard"]
        from matplotlib import pyplot as plt
        with tempfile.TemporaryDirectory() as directory, patch.object(plt, "show") as show:
            for calendar in [False, True]:
                result = sample(calendar=calendar)
                before = result.projections.copy(deep=True)
                for name in names:
                    with self.subTest(chart=name, calendar=calendar):
                        chart = getattr(result.plot, name)()
                        path = chart.save(Path(directory) / f"{name}-{calendar}.png")
                        self.assertGreater(path.stat().st_size, 1000)
                        self.assertFalse(chart.data.empty)
                        self.assertIs(chart.ax.figure, chart.figure)
                assert_frame_equal(result.projections, before)
            show.assert_not_called()
            self.assertEqual(plt.get_fignums(), [])

    def test_charts_compose_on_supplied_axes_and_preserve_rcparams(self):
        import matplotlib as mpl
        from matplotlib.figure import Figure
        figure = Figure()
        ax = figure.subplots()
        before = dict(mpl.rcParams)
        chart = sample().plot.cohort_progression(ax=ax, interval="weekly")
        self.assertIs(chart.figure, figure)
        self.assertIs(chart.ax, ax)
        self.assertEqual(dict(mpl.rcParams), before)
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ["svg", "pdf"]:
                self.assertGreater(chart.save(Path(directory) / f"chart.{suffix}").stat().st_size, 1000)

    def test_scenarios_keep_different_timelines(self):
        chart = tg.viz.scenario_comparison({"finite": sample(), "ongoing": sample(n=30)})
        self.assertEqual(chart.data.groupby("scenario")["period"].max().to_dict(), {"finite": 20, "ongoing": 29})

    def test_heatmap_masks_immature_cells(self):
        chart = sample().plot.roas_heatmap(interval="weekly")
        matrix = chart.tables["matrix"]
        self.assertTrue(np.isnan(matrix.loc["B", 3]))
        self.assertAlmostEqual(matrix.loc["A", 3], 4.2)

    def test_observed_only_legend_matches_solid_lines(self):
        chart = sample().plot.cohort_progression(basis="observed")
        cohort_lines = [line for line in chart.ax.lines if line.get_label() in {"A", "B"}]
        self.assertTrue(all(line.get_linestyle() == "-" for line in cohort_lines))

    def test_dual_pnl_axes_share_the_same_zero_baseline(self):
        chart = sample().plot.marketing_pnl()
        for axis in chart.axes:
            low, high = axis.get_ylim()
            self.assertAlmostEqual(-low / (high - low), 0.5)


if __name__ == "__main__":
    unittest.main()
