"""Composable Matplotlib charts for cohort financial analytics.

Matplotlib is imported only when a chart is requested. Charts never call show(),
change a global style, or mutate their input result. Every chart exposes its data.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..exceptions import SchemaError
from .data import (
    break_even_data,
    cohort_daily_data,
    cohort_progression_data,
    cohort_summary_data,
    interval_spec,
    portfolio_timeline_data,
    receivables_data,
    select_cohorts,
)


PALETTE = ("#2463A6", "#0A8B7A", "#C76B21", "#7F5AA2", "#C24F65", "#578445", "#357E97", "#A48B35")
BLUE, TEAL, ORANGE, PURPLE, RED = PALETTE[:5]
INK = "#24364B"
MUTED = "#64748B"


@dataclass
class Chart:
    """A figure, its axes, and the exact DataFrames used to draw it."""

    figure: Any
    axes: tuple[Any, ...]
    data: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def ax(self):
        return self.axes[0]

    def save(self, path: str | Path, **kwargs) -> Path:
        """Export using Matplotlib, e.g. PNG, SVG or PDF; return the saved path."""
        path = Path(path)
        self.figure.savefig(path, **{"dpi": 160, "bbox_inches": "tight", **kwargs})
        return path


def _mpl():
    try:
        from matplotlib.figure import Figure
        from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter
    except ImportError as exc:
        raise ImportError("Charts require Matplotlib: pip install 'theseus-growth[viz]'.") from exc
    return Figure, FuncFormatter, MaxNLocator, PercentFormatter


def _axes(ax, title, xlabel, ylabel, figsize=(10, 5)):
    Figure, _, _, _ = _mpl()
    if ax is None:
        figure = Figure(figsize=figsize, layout="constrained", facecolor="white")
        ax = figure.subplots()
    else:
        figure = ax.figure
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=15)
    ax.set_xlabel(xlabel, color=MUTED, labelpad=9)
    ax.set_ylabel(ylabel, color=MUTED, labelpad=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#D9E1EB")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#E8EDF3", linewidth=0.7)
    ax.set_axisbelow(True)
    ax.margins(x=0.02)
    return figure, ax


def _money(ax, currency):
    _, FuncFormatter, _, _ = _mpl()

    def fmt(value, _):
        sign = "−" if value < 0 else ""
        absolute = abs(value)
        if absolute >= 1_000_000:
            return f"{sign}{currency}{absolute / 1_000_000:,.1f}m"
        if absolute >= 10_000:
            return f"{sign}{currency}{absolute / 1000:,.0f}k"
        if absolute and absolute < 10:
            return f"{sign}{currency}{absolute:,.2f}"
        return f"{sign}{currency}{absolute:,.0f}"

    ax.yaxis.set_major_formatter(FuncFormatter(fmt))


def _percent(ax):
    ax.yaxis.set_major_formatter(_mpl()[3](xmax=1.0))


def _legend(ax, **kwargs):
    handles, labels = ax.get_legend_handles_labels()
    if labels:
        ax.legend(handles, labels, frameon=False, fontsize=8, **kwargs)


def _calendar(ax, result):
    if result.axis.kind == "calendar":
        from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
        locator = AutoDateLocator(minticks=3, maxticks=7)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    else:
        ax.xaxis.set_major_locator(_mpl()[2](integer=True, nbins=7))


def _period_label(result):
    return "Calendar date" if result.axis.kind == "calendar" else "Period"


def _cursor(ax, result):
    if result.start < result.cursor < result.forecast_end:
        ax.axvline(result.cursor, color=MUTED, linestyle=":", linewidth=1, label="As of")


def _colors(result):
    # Keep the same cohort color across filters, without repeating every eight IDs.
    return {
        value: PALETTE[i] if i < len(PALETTE) else colorsys.hls_to_rgb(
            (i * 0.61803398875) % 1, 0.40 + (i % 3) * 0.06, 0.57
        )
        for i, value in enumerate(result.cohorts["cohort_id"])
    }


def _status_line(ax, x, y, statuses, *, color, label):
    """Draw complete actual prefixes solid; any modeled cumulative point dashed."""
    y = np.asarray(y, dtype=float)
    statuses = np.asarray(statuses)
    style = "--" if np.any(statuses == "projected") else "-"
    ax.plot(x, y, color=color, linewidth=2, linestyle=style, label=label)
    actual = np.isin(statuses, ["observed", "origin"])
    ax.plot(x, np.where(actual, y, np.nan), color=color, linewidth=2.2)
    if len(y) <= 32:
        ax.scatter(x, y, color=color, s=12, zorder=3)


def cohort_progression(
    result, *, interval="daily", cohorts=None, basis="resolved", spend=None,
    components=None, ax=None, title=None, legend=True,
) -> Chart:
    """Compare origin-aligned cumulative cohort ROAS by completed age interval."""
    data = cohort_progression_data(
        result, interval=interval, cohorts=cohorts, basis=basis, spend=spend, components=components
    )
    label = interval_spec(interval)[2]
    figure, ax = _axes(ax, title or "Cohort ROAS progression", f"{label} since acquisition", "Cumulative ROAS")
    colors = _colors(result)
    for cohort_id, group in data.groupby("cohort_id", sort=False):
        _status_line(ax, group["interval_index"], group["roas"], group["value_status"],
                     color=colors[cohort_id], label=str(cohort_id))
    ax.axhline(1.0, color=MUTED, linestyle=":", linewidth=1.2, label="100% recoup")
    ax.set_xlim(left=0)
    ax.xaxis.set_major_locator(_mpl()[2](integer=True, nbins=8))
    _percent(ax)
    if legend:
        _legend(ax, loc="best", ncol=2 if data["cohort_id"].nunique() > 6 else 1)
    ax.text(0, -0.23, "Solid: observed  ·  Dashed: includes projections  ·  Missing ages are not filled", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data)


def roas_heatmap(result, *, interval="weekly", cohorts=None, basis="resolved", spend=None, components=None, ax=None, title=None) -> Chart:
    """Cohort × elapsed-interval ROAS matrix, masking immature or unknown values."""
    data = cohort_progression_data(result, interval=interval, cohorts=cohorts, basis=basis, spend=spend, components=components)
    ids = data["cohort_id"].drop_duplicates().tolist()
    matrix = data.pivot(index="cohort_id", columns="interval_index", values="roas").reindex(index=ids)
    figure, ax = _axes(ax, title or "Cohort ROAS by age", f"{interval_spec(interval)[2]} since acquisition", "Cohort")
    from matplotlib import colormaps
    cmap = colormaps["YlGnBu"].copy()
    cmap.set_bad("#EDF1F6")
    artist = ax.imshow(np.ma.masked_invalid(matrix.to_numpy(dtype=float)), aspect="auto", cmap=cmap, vmin=0)
    ax.grid(False)
    indexes = np.unique(np.linspace(0, len(matrix.columns) - 1, min(12, len(matrix.columns)), dtype=int))
    ax.set_xticks(indexes, [str(matrix.columns[i]) for i in indexes])
    ax.set_yticks(range(len(ids)), [str(value) for value in ids])
    bar = figure.colorbar(artist, ax=ax, fraction=0.035, pad=0.03)
    bar.ax.yaxis.set_major_formatter(_mpl()[3](1))
    bar.set_label("Cumulative ROAS")
    ax.text(0, -0.23, f"Basis: {basis}  ·  Gray: immature / missing / no positive spend", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax, bar.ax), data, {"matrix": matrix})


def cumulative_monetization(result, *, cohorts=None, basis="resolved", components=None, per_user=True, currency="$", ax=None, title=None) -> Chart:
    """Cumulative cohort monetization, with observed and projected segments."""
    data = cohort_daily_data(result, cohorts=cohorts, basis=basis, components=components)
    column = "cumulative_revenue_per_user" if per_user else "cumulative_revenue"
    figure, ax = _axes(ax, title or "Cumulative cohort monetization", "Days since acquisition", "Revenue per original user" if per_user else "Cumulative revenue")
    colors = _colors(result)
    for cohort_id, group in data.groupby("cohort_id", sort=False):
        _status_line(ax, np.r_[0, group["elapsed_days"]], np.r_[0.0, group[column]],
                     ["origin", *group["cumulative_status"]], color=colors[cohort_id], label=str(cohort_id))
    _money(ax, currency)
    _legend(ax)
    ax.set_xlim(left=0)
    ax.text(0, -0.23, "Solid: observed  ·  Dashed: includes projections", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data)


def daily_monetization(result, *, cohorts=None, basis="resolved", components=None, per_user=True, currency="$", ax=None, title=None) -> Chart:
    """Incremental revenue by cohort age, rather than cumulative revenue."""
    data = cohort_daily_data(result, cohorts=cohorts, basis=basis, components=components)
    column = "revenue_per_user" if per_user else "revenue"
    figure, ax = _axes(ax, title or "Daily cohort monetization", "Cohort age (days)", "Daily revenue per original user" if per_user else "Daily revenue")
    colors = _colors(result)
    for cohort_id, group in data.groupby("cohort_id", sort=False):
        _status_line(ax, group["age"], group[column], group["value_status"], color=colors[cohort_id], label=str(cohort_id))
    _money(ax, currency)
    _legend(ax)
    ax.text(0, -0.23, "Solid: observed  ·  Dashed: projected", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data)


def recorded_vs_projected(result, *, cohorts=None, spend=None, currency="$", ax=None, title=None) -> Chart:
    """Recorded revenue, historical estimates and receivables versus cohort cost."""
    data = cohort_summary_data(result, cohorts=cohorts, spend=spend)
    figure, ax = _axes(ax, title or "Cohort revenue and projected receivable", "Cohort", "Revenue / acquisition spend")
    x = np.arange(len(data))
    bottom = np.zeros(len(data))
    series = [
        ("recorded_revenue", "Recorded revenue", BLUE, None),
        ("estimated_to_date", "Estimated to date", ORANGE, "//"),
        ("projected_receivable", "Projected receivable", TEAL, ".."),
        ("planned_revenue", "Planned cohort revenue", PURPLE, ".."),
    ]
    for column, label, color, hatch in series:
        values = data[column].to_numpy(dtype=float)
        if np.any(values):
            ax.bar(x, values, bottom=bottom, label=label, color=color, alpha=0.8, hatch=hatch, edgecolor="white", linewidth=0.5)
        bottom += values
    ax.scatter(x, data["acquisition_spend"], marker="_", s=230, linewidth=2.5, color=INK, label="Acquisition spend", zorder=4)
    ax.set_xticks(x, data["cohort_id"].astype(str), rotation=35 if len(data) > 5 else 0, ha="right" if len(data) > 5 else "center")
    _money(ax, currency)
    _legend(ax)
    return Chart(figure, (ax,), data)


def cohort_revenue(result, *, cohorts=None, currency="$", max_cohorts=8, ax=None, title=None) -> Chart:
    """Calendar-aligned stacked revenue contributions; excess cohorts form Other."""
    if not isinstance(max_cohorts, int) or max_cohorts < 1:
        raise SchemaError("max_cohorts must be a positive integer.")
    selected = select_cohorts(result, cohorts)
    ledger = result.contributions
    data = ledger.loc[ledger["category"].eq("revenue") & ledger["cohort_id"].isin(selected["cohort_id"])].copy()
    if data.empty:
        raise SchemaError("No revenue rows to stack.")
    if data["amount"].lt(0).any():
        raise SchemaError("Stacked cohort revenue requires non-negative values; use revenue_vs_spend for net revenue with refunds.")
    periods = result.axis.range(result.start, result.forecast_end)
    matrix = data.pivot_table(index="period", columns="cohort_id", values="amount", aggfunc="sum", sort=False).reindex(periods).fillna(0.0)
    ranking = matrix.sum().sort_values(ascending=False, kind="stable").index.tolist()
    ids = ranking[:max_cohorts]
    values = [matrix[cohort_id].to_numpy() for cohort_id in ids]
    labels = [str(cohort_id) for cohort_id in ids]
    colors = [_colors(result)[cohort_id] for cohort_id in ids]
    if len(ranking) > max_cohorts:
        values.append(matrix[ranking[max_cohorts:]].sum(axis=1).to_numpy())
        labels.append(f"Other ({len(ranking) - max_cohorts} cohorts)")
        colors.append("#B4BFCD")
    figure, ax = _axes(ax, title or "Daily revenue contributed by cohort", _period_label(result), "Daily revenue")
    ax.stackplot(periods, *values, labels=labels, colors=colors, alpha=0.85)
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    _legend(ax, loc="upper right", ncol=2)
    ax.text(0, -0.23, "Resolved observed + modeled contributions; only supplied ledger rows contribute", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data, {"matrix": matrix})


def revenue_vs_spend(result, *, currency="$", ax=None, title=None) -> Chart:
    data = portfolio_timeline_data(result)
    figure, ax = _axes(ax, title or "Daily revenue and acquisition spend", _period_label(result), "Daily amount")
    _status_line(ax, data["period"], data["revenue"], data["revenue_status"], color=BLUE, label="Revenue (dashed = modeled)")
    ax.plot(data["period"], data["acquisition_spend"], color=PURPLE, linewidth=2, label="Acquisition spend")
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    _legend(ax)
    return Chart(figure, (ax,), data)


def cumulative_revenue_vs_spend(result, *, currency="$", ax=None, title=None) -> Chart:
    data = portfolio_timeline_data(result)
    figure, ax = _axes(ax, title or "Cumulative revenue and acquisition spend", _period_label(result), "Cumulative amount")
    statuses = np.where(data["revenue_status"].eq("observed").cummin(), "observed", "projected")
    _status_line(ax, data["period"], data["cumulative_revenue"], statuses, color=BLUE, label="Revenue (dashed = modeled)")
    ax.plot(data["period"], data["cumulative_spend"], color=PURPLE, linewidth=2, label="Acquisition spend")
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    _legend(ax)
    return Chart(figure, (ax,), data)


def _profit_fill(ax, x, y):
    y = np.asarray(y, dtype=float)
    ax.fill_between(x, y, 0, where=y < 0, interpolate=True, color=RED, alpha=0.16)
    ax.fill_between(x, y, 0, where=y >= 0, interpolate=True, color=TEAL, alpha=0.16)
    ax.axhline(0, color=MUTED, linewidth=0.8)


def _event_annotations(ax, data, events, column, event, label, color, position):
    found = events.loc[events["event"].eq(event), "period"].iloc[0]
    if pd.isna(found):
        return
    row = data.loc[data["period"].eq(found)].iloc[0]
    period_label = str(found.date()) if isinstance(found, pd.Timestamp) else str(found)
    ax.scatter([found], [row[column]], color=color, s=24, zorder=5)
    ax.annotate(f"{label}: {period_label}", xy=(found, row[column]), xytext=position,
                textcoords="axes fraction", fontsize=8, color=color,
                arrowprops={"arrowstyle": "-", "color": color, "lw": 0.8},
                bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "none", "pad": 2})


def marketing_pnl(result, *, currency="$", ax=None, title=None, annotate=True) -> Chart:
    """Daily revenue/spend/P&L with cumulative P&L on a labeled second axis."""
    data = portfolio_timeline_data(result)
    events = break_even_data(result)
    figure, ax = _axes(ax, title or "Marketing P&L and cumulative recoup", _period_label(result), "Daily amount")
    ax.plot(data["period"], data["revenue"], color=BLUE, lw=1.7, label="Daily revenue")
    ax.plot(data["period"], data["acquisition_spend"], color=PURPLE, lw=1.7, label="Daily acquisition spend")
    ax.plot(data["period"], data["marketing_pnl"], color=ORANGE, lw=1.7, label="Daily marketing P&L")
    second = ax.twinx()
    second.set_ylabel("Cumulative marketing P&L", color=TEAL, labelpad=10)
    second.tick_params(axis="y", colors=TEAL, labelsize=9)
    second.spines["top"].set_visible(False)
    second.spines["right"].set_color("#D9E1EB")
    second.plot(data["period"], data["cumulative_marketing_pnl"], color=TEAL, lw=2.4)
    _profit_fill(second, data["period"], data["cumulative_marketing_pnl"])
    # Both monetary scales share a zero baseline, so profit/loss signs agree visually.
    daily_limit = max(1.0, float(data[["revenue", "acquisition_spend", "marketing_pnl"]].abs().max().max())) * 1.08
    cumulative_limit = max(1.0, float(data["cumulative_marketing_pnl"].abs().max())) * 1.08
    ax.set_ylim(-daily_limit, daily_limit)
    second.set_ylim(-cumulative_limit, cumulative_limit)
    # A legend proxy keeps daily and cumulative series in a single legend.
    ax.plot([], [], color=TEAL, lw=2.4, label="Cumulative marketing P&L (right)")
    if annotate:
        _event_annotations(ax, data, events, "marketing_pnl", "daily_break_even", "Daily break-even", ORANGE, (0.12, 0.56))
        _event_annotations(second, data, events, "cumulative_marketing_pnl", "cumulative_break_even", "Cumulative break-even", TEAL, (0.54, 0.22))
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    _money(second, currency)
    _legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    ax.text(0, -0.40, "Resolved actuals + estimates; P&L includes operating components before acquisition spend", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax, second), data, {"events": events})


def cumulative_pnl(result, *, currency="$", ax=None, title=None, annotate=True) -> Chart:
    """Cumulative profitability, peak capital at risk and recoup period."""
    data = portfolio_timeline_data(result)
    events = break_even_data(result)
    figure, ax = _axes(ax, title or "Cumulative P&L and capital at risk", _period_label(result), "Cumulative marketing P&L")
    ax.plot(data["period"], data["cumulative_marketing_pnl"], color=BLUE, linewidth=2.3)
    _profit_fill(ax, data["period"], data["cumulative_marketing_pnl"])
    if annotate:
        trough = data.loc[data["cumulative_marketing_pnl"].idxmin()]
        risk = max(0.0, -float(trough["cumulative_marketing_pnl"]))
        ax.annotate(f"Maximum capital at risk: {currency}{risk:,.0f}",
                    xy=(trough["period"], trough["cumulative_marketing_pnl"]),
                    xytext=(0.08, 0.12), textcoords="axes fraction", fontsize=9, color=RED,
                    arrowprops={"arrowstyle": "-", "color": RED},
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9})
        _event_annotations(ax, data, events, "cumulative_marketing_pnl", "cumulative_break_even", "Cumulative break-even", TEAL, (0.53, 0.65))
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    ax.text(0, -0.23, "Includes projections; capital at risk assumes same-period cash settlement", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data, {"events": events})


def projected_receivables(result, *, currency="$", ax=None, title=None) -> Chart:
    data = receivables_data(result)
    figure, ax = _axes(ax, title or "Projected receivables from acquired cohorts", _period_label(result), "Remaining projected revenue")
    ax.fill_between(data["period"], data["projected_receivable"], color=TEAL, alpha=0.13)
    ax.plot(data["period"], data["projected_receivable"], color=TEAL, linewidth=2.2)
    _cursor(ax, result)
    _calendar(ax, result)
    _money(ax, currency)
    ax.text(0, -0.23, "Fixed forecast horizon; future acquisitions excluded until their acquisition period", transform=ax.transAxes, fontsize=8, color=MUTED)
    return Chart(figure, (ax,), data)


def scenario_comparison(scenarios: Mapping[str, Any], *, currency="$", ax=None, title=None) -> Chart:
    """Compare cumulative P&L for finite or ongoing acquisition scenarios."""
    if not scenarios:
        raise SchemaError("At least one named scenario is required.")
    if len({result.axis.kind for result in scenarios.values()}) != 1:
        raise SchemaError("Scenario charts cannot mix integer and calendar axes.")
    first = next(iter(scenarios.values()))
    figure, ax = _axes(ax, title or "Acquisition scenario comparison", _period_label(first), "Cumulative marketing P&L")
    pieces = []
    for i, (name, result) in enumerate(scenarios.items()):
        data = portfolio_timeline_data(result).assign(scenario=name)
        pieces.append(data)
        ax.plot(data["period"], data["cumulative_marketing_pnl"], color=PALETTE[i % len(PALETTE)], linewidth=2, label=name)
    ax.axhline(0, color=MUTED, linestyle=":", linewidth=1)
    _calendar(ax, first)
    _money(ax, currency)
    _legend(ax)
    return Chart(figure, (ax,), pd.concat(pieces, ignore_index=True))


def dashboard(result, *, cohorts=None, interval="weekly", spend=None, currency="$") -> Chart:
    """Compose six primary views; all individual charts also accept supplied axes."""
    Figure = _mpl()[0]
    figure = Figure(figsize=(16, 14), layout="constrained", facecolor="white")
    axes = figure.subplots(3, 2)
    first_id = select_cohorts(result, cohorts)["cohort_id"].iloc[0]
    charts = {
        "monetization": cumulative_monetization(result, cohorts=[first_id], ax=axes[0, 0], currency=currency),
        "progression": cohort_progression(result, cohorts=cohorts, interval=interval, spend=spend, ax=axes[0, 1]),
        "cohort_revenue": cohort_revenue(result, cohorts=cohorts, ax=axes[1, 0], currency=currency),
        "daily_revenue": revenue_vs_spend(result, ax=axes[1, 1], currency=currency),
        "receivables": projected_receivables(result, ax=axes[2, 0], currency=currency),
        "cumulative_pnl": cumulative_pnl(result, ax=axes[2, 1], currency=currency),
    }
    figure.suptitle("Theseus · Cohort financial analytics", fontsize=20, fontweight="bold", color=INK)
    return Chart(figure, tuple(axes.flat), portfolio_timeline_data(result), {name: chart.data for name, chart in charts.items()})


class PlotAccessor:
    """Chart methods bound to a ForecastResult, accessed via ``result.plot``."""

    def __init__(self, result):
        self.result = result

    def cohort_progression(self, **kwargs):
        return cohort_progression(self.result, **kwargs)

    def roas_heatmap(self, **kwargs):
        return roas_heatmap(self.result, **kwargs)

    def cumulative_monetization(self, **kwargs):
        return cumulative_monetization(self.result, **kwargs)

    def daily_monetization(self, **kwargs):
        return daily_monetization(self.result, **kwargs)

    def recorded_vs_projected(self, **kwargs):
        return recorded_vs_projected(self.result, **kwargs)

    def cohort_revenue(self, **kwargs):
        return cohort_revenue(self.result, **kwargs)

    def revenue_vs_spend(self, **kwargs):
        return revenue_vs_spend(self.result, **kwargs)

    def cumulative_revenue_vs_spend(self, **kwargs):
        return cumulative_revenue_vs_spend(self.result, **kwargs)

    def marketing_pnl(self, **kwargs):
        return marketing_pnl(self.result, **kwargs)

    def cumulative_pnl(self, **kwargs):
        return cumulative_pnl(self.result, **kwargs)

    def projected_receivables(self, **kwargs):
        return projected_receivables(self.result, **kwargs)

    def dashboard(self, **kwargs):
        return dashboard(self.result, **kwargs)
