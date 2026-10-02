# Theseus

Theseus is an opinionated, DataFrame-first Python library for cohort financial analytics. It turns cohort populations and age-indexed curves into a long-form contribution ledger, then derives revenue, acquisition spend, marketing P&L, break-even, LTV, and ROAS.

Theseus is a library, not an application or data platform. Callers decide where DataFrames come from and where results are stored. Lightweight XLSX, CSV, and read-only database adapters are included at the boundary.

## Install

```bash
pip install theseus-growth
```

XLSX support is optional:

```bash
pip install "theseus-growth[excel]"
```

## Interactive walkthrough

Open [Theseus_Walkthrough.ipynb](Theseus_Walkthrough.ipynb) for an executed, self-contained V1 tutorial. It follows the original notebook's curve-to-cohort progression and covers financial metrics, the visualization suite, daily `advance` updates, full/partial cohort broadcasts, integer/calendar dates, and CSV/XLSX/database adapters. All examples use deterministic synthetic data.

To run it from this checkout with Python 3.10 or newer:

```bash
python -m pip install -e ".[viz,excel]" jupyterlab ipykernel
python -m jupyter lab Theseus_Walkthrough.ipynb
```

Choose the same environment's Python kernel, then **Restart Kernel and Run All Cells**. No credentials or external data are needed. Demo exports go to the Git-ignored `examples/output/notebook/` directory relative to the notebook's working directory. The notebook includes executable checks for incremental/full-rebuild equivalence, observation preservation, partial-broadcast isolation, and adapter round-trips.

## CFO scenario-planning labs

Two executed notebooks extend the primer into capital-allocation decisions using deterministic synthetic CSV datasets:

- [`examples/notebooks/Game_CFO_Cash_Flow_Optimization.ipynb`](examples/notebooks/Game_CFO_Cash_Flow_Optimization.ipynb) optimizes acquisition for active-player growth subject to a daily cash floor, then solves for the minimum spend required to grow bank cash from $400k to $1MM.
- [`examples/notebooks/Subscription_CFO_Channel_Experiments.ipynb`](examples/notebooks/Subscription_CFO_Channel_Experiments.ipynb) re-underwrites a winning podcast test, a failed display test, and a CTV test whose direct ROAS is poor but whose modeled retention and monetization halo can create portfolio value.
- [`examples/notebooks/Subscription_CMO_Campaign_Optimization.ipynb`](examples/notebooks/Subscription_CMO_Campaign_Optimization.ipynb) applies Waterfall and Distributed budgeting to cohort-derived campaign response curves, contrasting a primary marginal-ROAS constraint with a primary fixed-budget constraint.

Install the planning dependencies and open either notebook from the repository root:

```bash
python -m pip install -e ".[planning]"
python -m jupyter lab examples/notebooks/
```

The source data live under `examples/data/game/` and `examples/data/subscription/`. Regenerate the deterministic CSV files with `python examples/generate_cfo_datasets.py`. The examples are decision-model demonstrations, not measured channel benchmarks or causal evidence.

## V1 model

V1 has three principal operations:

- `broadcast` is the atomic operation. It maps one cohort's age-indexed curve onto all or part of a shared timeline.
- `forecast` broadcasts a collection of cohorts and creates a financial result.
- `advance` moves a result's cursor forward by exactly one period and consumes only that period's new DataFrames.

Revising a historical cohort is another broadcast. It replaces that cohort's modeled rows over the selected interval and deterministically recalculates the result. Observed rows remain authoritative.

Periods may be either abstract integers (`0, 1, 2, ...`) or daily calendar values. A forecast cannot mix the two kinds. Calendar-specific concepts such as months are deliberately not inferred from integer periods.

## Source DataFrames

### `cohorts`

| Column | Meaning |
| --- | --- |
| `cohort_id` | Unique cohort identifier |
| `acquisition_period` | Integer period or calendar date at age zero |
| `population` | Original cohort population |
| `curve_id` | Curve assigned to the cohort |

Additional cohort columns, such as channel, geography, or product, are preserved on contribution rows.

### `curves`

| Column | Meaning |
| --- | --- |
| `curve_id` | Curve identifier |
| `age` | Non-negative integer cohort age |
| `component` | Component name, such as `iap_revenue` |
| `category` | `revenue`, `cost`, `contribution`, or `activity` |
| `value` | Per-original-user quantity for that age and component |

`curve_version` is optional and defaults to `1`. `cohort_id` is optional and defines a cohort-specific override. Revenue and contribution values enter P&L positively, cost values enter negatively, and activity rows are non-financial.

`value_basis` defaults to `per_original_user`. A financial component may instead use `per_active_user`; it will be multiplied by the activity component named by `driver_component`, which defaults to `retention`. Retention driver values are proportions between zero and one. This separates retention from per-active-user economics, so a retention-only broadcast can recalculate contribution without restating monetization assumptions.

For cumulative monetization inputs, use `cumulative_to_incremental` before forecasting.

### `observations`

| Column | Meaning |
| --- | --- |
| `cohort_id` | Cohort being observed |
| `period` | Observation period |
| `component` | Component being observed |
| `amount` | Observed total amount, not a per-user value |
| `category` | Optional when a matching projected row exists |

An observation replaces the matching modeled `(cohort_id, period, component)` row in resolved contributions.

### `acquisition_spend`

Required columns are `period` and non-negative `amount`. Additional dimensions are allowed. Multiple spend rows in a period are summed.

## Forecast example

```python
import pandas as pd
import theseus_growth as tg

cohorts = pd.DataFrame([
    {"cohort_id": "c0", "acquisition_period": 0, "population": 100, "curve_id": "base"},
    {"cohort_id": "c1", "acquisition_period": 1, "population": 100, "curve_id": "base"},
])

curves = pd.DataFrame([
    {"curve_id": "base", "age": 0, "component": "revenue", "category": "revenue", "value": 0.50},
    {"curve_id": "base", "age": 1, "component": "revenue", "category": "revenue", "value": 0.30},
    {"curve_id": "base", "age": 2, "component": "revenue", "category": "revenue", "value": 0.20},
])

spend = pd.DataFrame([
    {"period": 0, "amount": 100},
    {"period": 1, "amount": 100},
])

result = tg.forecast(
    cohorts,
    curves,
    acquisition_spend=spend,
    as_of=1,
    forecast_end=3,
)

result.contributions  # canonical long-form cohort ledger
result.timeline()     # period-level revenue and marketing P&L
result.metrics()      # LTV, ROAS, break-even, cash at risk, etc.
```

This example produces revenue `[50, 80, 50, 20]` and cumulative marketing P&L `[-50, -70, -20, 0]`.

## Atomic broadcasting

```python
projection = tg.broadcast(cohorts.iloc[0], curves, start=1, end=2)
```

To revise one cohort over a historical or future range:

```python
corrected_curve = curves.assign(
    value=[0.50, 0.40, 0.25],
    curve_version=2,
)

revised = result.broadcast(
    cohorts=["c0"],
    curves=corrected_curve,
    start=0,
    end=3,
)
```

The result is new; the original result is not mutated. Supplied rows patch the cohort's assigned curve by `(age, component)`, and the merged curve is retained as a cohort-scoped override so later `advance` calls use it.

## Incremental advance

```python
tomorrow = result.advance(
    observations=pd.DataFrame([
        {"cohort_id": "c0", "period": 2, "component": "revenue", "amount": 22},
        {"cohort_id": "c1", "period": 2, "component": "revenue", "amount": 31},
    ]),
    acquisition_spend=pd.DataFrame([{"period": 2, "amount": 110}]),
)
```

`advance` accepts only rows for the next period. By default it also extends `forecast_end` by one period, preserving the forecast horizon. New cohorts may be supplied in the same call. Passing `extend=False` moves only the cursor. Newly supplied acquisition-spend rows replace any previously planned spend rows for that period.

Batch forecasting and repeated daily advancement are tested to produce the same canonical result.

## XLSX, CSV, and database inputs

```python
frames = tg.io.read_xlsx("planning_inputs.xlsx")
result = tg.forecast(frames, as_of=10, forecast_end=90)
```

The default workbook sheets are `Cohorts`, `Curves`, `Observations`, and `Acquisition Spend`. Sheet names can be remapped. Helpers are also available to validate a workbook and write an input template:

```python
tg.io.write_xlsx_template("theseus_template.xlsx")
frames = tg.io.validate_xlsx("planning_inputs.xlsx")
```

CSV directories use `cohorts.csv`, `curves.csv`, and optional `observations.csv` and `acquisition_spend.csv`:

```python
frames = tg.io.read_csv_directory("inputs/")
tg.io.write_csv_directory(frames, "normalized_inputs/")
```

The database adapter is intentionally read-only and owns no connection lifecycle:

```python
source = tg.io.DatabaseSource(
    connection=my_connection,
    queries={
        "cohorts": "select * from analytics.cohorts",
        "curves": "select * from analytics.curves",
        "observations": "select * from analytics.observations",
        "acquisition_spend": "select * from analytics.acquisition_spend",
    },
)

frames = tg.io.load_source(source)
```

Any custom object implementing `load() -> SourceFrames` can be used through the same `DataFrameSource` protocol.

## Visualization suite

Install the optional plotting dependency from this checkout:

```bash
pip install -e ".[viz]"
```

The suite follows the analytical sequence in [Building a marketing P&L using LTV and ROAS](https://mobiledevmemo.com/ltv-roas-marketing-p-and-l/): monetization by cohort age, recorded revenue and projected receivables, stacked cohort revenue, acquisition costs, recoup, and capital at risk.

```python
chart = result.plot.cohort_progression(interval="weekly")
chart.save("cohort_roas.svg")
chart.data                  # exact chart-ready DataFrame
chart.figure                # Matplotlib Figure, for custom layout/export
chart.ax                    # primary Axes

# Also available as a standalone function:
chart = tg.viz.cohort_progression(result, interval="weekly")

# Financial transforms do not require Matplotlib:
progression_df = result.cohort_progression(interval="weekly")
```

| Chart method on `result.plot` | Purpose |
| --- | --- |
| `cohort_progression` | Cumulative ROAS curves aligned to each cohort's origin |
| `roas_heatmap` | Cohort × elapsed-interval ROAS, masking immature values |
| `cumulative_monetization` | Cumulative revenue per original user, with observed/projected segments |
| `daily_monetization` | Incremental daily revenue per original user |
| `recorded_vs_projected` | Recorded revenue, historical estimates, receivables and cohort acquisition spend |
| `cohort_revenue` | Revenue stacked across cohorts on the shared timeline |
| `revenue_vs_spend` | Daily revenue against acquisition spend |
| `cumulative_revenue_vs_spend` | Cumulative revenue against cumulative acquisition spend |
| `marketing_pnl` | Daily revenue, spend and P&L, plus cumulative P&L on a second axis |
| `cumulative_pnl` | Cumulative P&L, cumulative break-even and maximum capital at risk |
| `projected_receivables` | Remaining projected revenue from cohorts already acquired at each point |
| `dashboard` | Six views in a single composable figure |

`tg.viz.scenario_comparison({"Finite campaign": finite_result, "Ongoing acquisition": ongoing_result})` compares cumulative P&L across scenarios.

All individual charts accept an existing Matplotlib `ax` and a custom `title`. Monetary charts accept `currency="€"` to change formatting (this does not convert currencies). No chart calls `show()` or alters global plotting styles. Export uses `chart.save(...)` for PNG, SVG or PDF. `Chart.tables` exposes additional frames such as heatmap matrices or break-even events. Cohort filters apply to cohort charts; portfolio panels in a dashboard always show the full portfolio.

### Cohort ROAS progression

Cohorts remain the cohort IDs supplied by the caller. `interval` controls the age checkpoints, not how acquisition dates are regrouped. Each curve uses **cumulative revenue / total acquisition spend for that cohort**, never an average of daily ROAS ratios.

- The origin `(0, 0)` is immediately before revenue accrues. Point 1 for `daily` includes age-zero revenue. Point 1 for `weekly` includes ages 0 through 6.
- Supported intervals: `daily`, `weekly`, `monthly`, `quarterly`, `yearly`, or a positive integer number of daily periods. `D`, `W`, `M`, `Q`, and `Y` are aliases.
- Monthly boundaries are calendar anniversaries of acquisition. A cohort acquired January 31 has boundaries February 28/29, March 31, etc.; calendar boundaries do not drift after a short month. An integer timeline must use an explicit fixed interval such as `interval=30`, not `monthly`.
- Only complete intervals appear. Younger cohorts end earlier; immature ages are not padded with zero. A missing revenue component/day makes subsequent cumulative values unknown, so sparse curves need explicit zero rows where revenue is known to be zero.
- `basis="resolved"` combines observations with remaining projections. Solid segments require fully observed cumulative history; dashed segments contain at least one modeled value, including historical estimates. `basis="observed"` restricts data to actual observations through the cursor. `basis="projected"` shows the original modeled contribution rows.
- Curves with missing or zero acquisition spend have undefined (`NaN`) ROAS. Spend rows can identify `cohort_id`; otherwise they are assigned by acquisition period only when exactly one cohort matches. Ambiguous allocation raises an error. Pass `spend=pd.DataFrame({"cohort_id": [...], "amount": [...]})` to supply explicit cohort totals.
- Optional `components=["iap", "ads"]` selects revenue components; costs and activity never enter the ROAS numerator. Partial historical forecasts beginning after cohort acquisition cannot produce full-life ROAS without the missing revenue history.

```python
result.plot.cohort_progression(
    cohorts=["c0", "c1"],
    interval="weekly",
    basis="observed",
).save("observed_roas.png")

result.plot.roas_heatmap(interval="weekly").save("cohort_roas_heatmap.png")
result.plot.dashboard(interval="weekly").save("cohort_financials.pdf")
```

The P&L charts use the engine's signed contributions, including costs, while ROAS and monetization charts use revenue only. Historical estimates are never labeled Recorded Revenue. Receivables exclude not-yet-acquired cohorts and are limited to the forecast horizon. Their time series uses the current model/observation snapshot; it is not a replay of previous forecast vintages. Capital at risk assumes same-period cash settlement and is not a settlement-lag cash-flow forecast. Break-even annotations show the first crossing after spending begins, not a guarantee that subsequent periods stay profitable.

Generate the complete gallery with reproducible synthetic data:

```bash
python -m examples.visualization_suite --output examples/output
```

The example writes 15 PNG/SVG charts and their underlying CSV files, including weekly/monthly progression and finite-versus-ongoing acquisition scenarios. The synthetic data illustrates the article's concepts; it does not reproduce the article's source dataset.

## Legacy API

The original `theseus()` retention and DAU API remains available for compatibility:

```python
legacy = tg.theseus()
```

It requires the optional legacy dependencies and is not used by the V1 financial engine.

Theseus is released under the MIT license.
