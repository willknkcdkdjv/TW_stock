"""Reusable Plotly visualization helpers for the TW Stock dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Taiwan market convention: up = red, down = green
COLOR_UP = "rgb(220, 53, 69)"
COLOR_DOWN = "rgb(40, 167, 69)"
COLOR_NEUTRAL = "rgb(128, 128, 128)"

# Backward-compatible aliases
COLOR_POSITIVE = COLOR_UP
COLOR_NEGATIVE = COLOR_DOWN

RETURN_COLOR_SCALE = [
    [0.0, COLOR_DOWN],
    [0.5, COLOR_NEUTRAL],
    [1.0, COLOR_UP],
]

TREEMAP_HOVER_FIELDS = [
    "stock_count",
    "up_ratio",
    "avg_return_pct",
    "total_turnover",
    "volume_spike_count",
    "breakout_count",
]

TREEMAP_REQUIRED_COLUMNS = {"total_turnover", "avg_return_pct"}


def get_tw_return_color(value) -> str:
    """Taiwan convention: positive=red, negative=green, zero/missing=gray."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return COLOR_NEUTRAL
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return COLOR_NEUTRAL
    if pd.isna(numeric):
        return COLOR_NEUTRAL
    if numeric > 0:
        return COLOR_UP
    if numeric < 0:
        return COLOR_DOWN
    return COLOR_NEUTRAL


def format_return_color(value) -> str:
    """Alias for get_tw_return_color (backward compatibility)."""
    return get_tw_return_color(value)


def format_large_number(value) -> str:
    """Format numbers with Taiwan-friendly 億 / 萬 units."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if pd.isna(numeric):
        return "N/A"

    yi = 100_000_000
    if abs(numeric) >= yi:
        return f"{numeric / yi:.1f}億"

    wan = 10_000
    if abs(numeric) >= wan:
        return f"{numeric / wan:.1f}萬"

    return f"{numeric:,.0f}"


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _has_required_treemap_columns(df: pd.DataFrame, label_col: str) -> bool:
    if df is None or df.empty:
        return False
    if label_col not in df.columns:
        return False
    return TREEMAP_REQUIRED_COLUMNS.issubset(df.columns)


def _prepare_trend_df(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    if not _has_required_treemap_columns(df, label_col):
        return pd.DataFrame()

    work = df.copy()
    work[label_col] = work[label_col].astype(str).str.strip()
    work = work[work[label_col].notna() & (work[label_col] != "")]

    work["total_turnover"] = _coerce_numeric(work["total_turnover"]).fillna(0)
    work["avg_return_pct"] = _coerce_numeric(work["avg_return_pct"])

    for col in TREEMAP_HOVER_FIELDS:
        if col in work.columns and col != label_col:
            if col in {"stock_count", "volume_spike_count", "breakout_count"}:
                work[col] = _coerce_numeric(work[col]).fillna(0).astype(int)
            else:
                work[col] = _coerce_numeric(work[col])

    work = work[work["total_turnover"] > 0]
    return work.reset_index(drop=True)


def _build_treemap_hover_data(df: pd.DataFrame, label_col: str) -> dict:
    hover_data: dict[str, bool | str] = {label_col: False}
    format_map = {
        "up_ratio": ":.1%",
        "avg_return_pct": ":.2f",
        "total_turnover": ":,.0f",
    }
    for col in TREEMAP_HOVER_FIELDS:
        if col in df.columns:
            hover_data[col] = format_map.get(col, True)
    return hover_data


def _render_trend_treemap(
    df: pd.DataFrame,
    label_col: str,
    title: str,
) -> go.Figure | None:
    if not _has_required_treemap_columns(df, label_col):
        return None

    work = _prepare_trend_df(df, label_col)
    if work.empty:
        return None

    hover_data = _build_treemap_hover_data(work, label_col)

    color_df = work.copy()
    color_df["avg_return_pct_color"] = color_df["avg_return_pct"].fillna(0)

    fig = px.treemap(
        color_df,
        path=[label_col],
        values="total_turnover",
        color="avg_return_pct_color",
        title=title,
        hover_data=hover_data,
        color_continuous_scale=RETURN_COLOR_SCALE,
        color_continuous_midpoint=0,
    )
    fig.update_traces(
        textinfo="label+value+percent parent",
        texttemplate="<b>%{label}</b><br>%{value:,.0f}",
    )
    fig.update_layout(
        margin={"t": 40, "l": 10, "r": 10, "b": 10},
        coloraxis_colorbar={"title": "Avg Return %"},
    )
    return fig


def render_market_heatmap(industry_df: pd.DataFrame) -> go.Figure | None:
    """Treemap of industry turnover colored by average return."""
    return _render_trend_treemap(
        industry_df,
        label_col="industry",
        title="Industry Turnover Heatmap",
    )


def render_subsector_heatmap(subsector_df: pd.DataFrame) -> go.Figure | None:
    """Treemap of sub-sector turnover colored by average return."""
    return _render_trend_treemap(
        subsector_df,
        label_col="sub_sector",
        title="Sub-sector Turnover Heatmap",
    )


def render_signal_bar(signal_summary_df: pd.DataFrame) -> go.Figure | None:
    """Bar chart of signal counts by signal name."""
    if signal_summary_df is None or signal_summary_df.empty:
        return None

    required = {"signal_name", "count"}
    if not required.issubset(signal_summary_df.columns):
        return None

    work = signal_summary_df.copy()
    work["signal_name"] = work["signal_name"].astype(str)
    work["count"] = _coerce_numeric(work["count"]).fillna(0).astype(int)
    work = work.sort_values("count", ascending=True)

    if work.empty or work["count"].sum() == 0:
        return None

    fig = px.bar(
        work,
        x="count",
        y="signal_name",
        orientation="h",
        title="Signal Count Summary",
        labels={"count": "Count", "signal_name": "Signal"},
        color="count",
        color_continuous_scale=[COLOR_NEUTRAL, COLOR_UP],
    )
    fig.update_layout(
        margin={"t": 40, "l": 10, "r": 10, "b": 10},
        showlegend=False,
        yaxis={"categoryorder": "total ascending"},
    )
    fig.update_traces(hovertemplate="Signal=%{y}<br>Count=%{x}<extra></extra>")
    return fig
