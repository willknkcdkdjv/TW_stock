"""Plotly chart helpers for the TW Stock Streamlit dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

COLOR_POSITIVE = "rgb(40, 167, 69)"
COLOR_NEGATIVE = "rgb(220, 53, 69)"
COLOR_NEUTRAL = "rgb(128, 128, 128)"

RETURN_COLOR_SCALE = [
    [0.0, COLOR_NEGATIVE],
    [0.5, COLOR_NEUTRAL],
    [1.0, COLOR_POSITIVE],
]

TREEMAP_HOVER_FIELDS = [
    "stock_count",
    "up_ratio",
    "avg_return_pct",
    "total_turnover",
    "volume_spike_count",
    "breakout_count",
]


def format_return_color(value) -> str:
    """Return a CSS color for a return value (positive/negative/neutral)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return COLOR_NEUTRAL
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return COLOR_NEUTRAL
    if pd.isna(numeric):
        return COLOR_NEUTRAL
    if numeric > 0:
        return COLOR_POSITIVE
    if numeric < 0:
        return COLOR_NEGATIVE
    return COLOR_NEUTRAL


def _empty_figure(message: str = "No data available") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": COLOR_NEUTRAL},
    )
    fig.update_layout(
        margin={"t": 30, "l": 10, "r": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _prepare_trend_df(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    if df is None or df.empty or label_col not in df.columns:
        return pd.DataFrame()

    work = df.copy()
    work[label_col] = work[label_col].astype(str).str.strip()
    work = work[work[label_col].notna() & (work[label_col] != "")]

    if "total_turnover" in work.columns:
        work["total_turnover"] = _coerce_numeric(work["total_turnover"]).fillna(0)
    else:
        work["total_turnover"] = 0.0

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
) -> go.Figure:
    work = _prepare_trend_df(df, label_col)
    if work.empty:
        return _empty_figure(f"No {label_col} data with positive turnover.")

    color_col = "avg_return_pct" if "avg_return_pct" in work.columns else None
    hover_data = _build_treemap_hover_data(work, label_col)

    treemap_kwargs = {
        "data_frame": work,
        "path": [label_col],
        "values": "total_turnover",
        "title": title,
        "hover_data": hover_data,
        "color_continuous_scale": RETURN_COLOR_SCALE,
        "color_continuous_midpoint": 0,
    }
    if color_col is not None:
        treemap_kwargs["color"] = color_col

    fig = px.treemap(**treemap_kwargs)
    fig.update_traces(
        textinfo="label+value+percent parent",
        texttemplate="<b>%{label}</b><br>%{value:,.0f}",
    )
    fig.update_layout(
        margin={"t": 40, "l": 10, "r": 10, "b": 10},
        coloraxis_colorbar={"title": "Avg Return %"},
    )
    return fig


def render_market_heatmap(industry_df: pd.DataFrame) -> go.Figure:
    """Treemap of industry turnover colored by average return."""
    return _render_trend_treemap(
        industry_df,
        label_col="industry",
        title="Industry Turnover Heatmap",
    )


def render_subsector_heatmap(subsector_df: pd.DataFrame) -> go.Figure:
    """Treemap of sub-sector turnover colored by average return."""
    return _render_trend_treemap(
        subsector_df,
        label_col="sub_sector",
        title="Sub-sector Turnover Heatmap",
    )


def render_signal_bar(signal_summary_df: pd.DataFrame) -> go.Figure:
    """Bar chart of signal counts by signal name."""
    if signal_summary_df is None or signal_summary_df.empty:
        return _empty_figure("No signal summary data available.")

    required = {"signal_name", "count"}
    if not required.issubset(signal_summary_df.columns):
        return _empty_figure("Signal summary requires signal_name and count columns.")

    work = signal_summary_df.copy()
    work["signal_name"] = work["signal_name"].astype(str)
    work["count"] = _coerce_numeric(work["count"]).fillna(0).astype(int)
    work = work.sort_values("count", ascending=True)

    if work.empty or work["count"].sum() == 0:
        return _empty_figure("No signal counts to display.")

    fig = px.bar(
        work,
        x="count",
        y="signal_name",
        orientation="h",
        title="Signal Count Summary",
        labels={"count": "Count", "signal_name": "Signal"},
        color="count",
        color_continuous_scale=[COLOR_NEUTRAL, COLOR_POSITIVE],
    )
    fig.update_layout(
        margin={"t": 40, "l": 10, "r": 10, "b": 10},
        showlegend=False,
        yaxis={"categoryorder": "total ascending"},
    )
    fig.update_traces(hovertemplate="Signal=%{y}<br>Count=%{x}<extra></extra>")
    return fig
