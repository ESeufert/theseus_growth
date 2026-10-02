# Synthetic CFO scenario data

These datasets support the executed notebooks in `examples/notebooks/`. All values are deterministic synthetic assumptions for demonstrating Theseus; they are not market benchmarks.

## Game

`game/` models an IAP and ad-supported title over a 365-day forecast.

- `channel_assumptions.csv`: CPI, weekly capacity, retention, monetization, and variable-cost assumptions.
- `curves.csv`: canonical age-indexed Theseus curves for retention, IAP revenue, ad revenue, and live-ops cost.
- `cohorts.csv` and `acquisition_spend.csv`: a baseline 26-week plan.
- `cash_assumptions.csv`: starting cash, daily non-marketing cash flow, liquidity floor, target cash, and planning horizons.

## Subscription

`subscription/` models established acquisition plus podcast, display, and CTV experiments.

- `curve_assumptions.csv`: compact prior, actual, and halo curve assumptions.
- `curves.csv`: canonical Theseus retention, subscription-revenue, and payment-fee curves.
- `cohorts.csv`, `acquisition_spend.csv`, and `observations.csv`: the experiment history through day 111.
- `channel_assumptions.csv`: the post-test decision state and channel capacities.
- `scenario_assumptions.csv`: cash and future-budget assumptions.
- `campaign_response_assumptions.csv`: weekly spend bounds and synthetic saturation assumptions used by the CMO campaign-optimization lab.

The CTV halo is intentionally represented separately from CTV's directly attributed cohort curve. In real analysis, estimate such a halo with a causal design and avoid double-counting direct and incremental conversions.

## Regeneration

From the repository root:

```bash
python examples/generate_cfo_datasets.py
```

The generator replaces only the named CSV files in these two directories.
