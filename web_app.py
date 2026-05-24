import html

import pandas as pd
from pandas.io.formats.style import Styler
import streamlit as st

import data_service
from data_service import (
    QUANT_DIR,
    add_price_indicators,
    apply_sector_mapping,
    breakout_debug_summary,
    build_llm_market_context,
    DEFAULT_SUB_SECTOR,
    get_cheap_value,
    get_high_dividend,
    get_industry_trend,
    get_latest_market_snapshot,
    get_subsector_trend,
    load_company_profile,
    load_sector_mapping,
    map_industry_to_name,
    merge_industry_into_snapshot,
    remove_duplicate_columns,
    get_top_gainers,
    get_top_losers,
    get_top_turnover,
    load_price_data as _load_price_data,
    load_valuation_data as _load_valuation_data,
)
from llm_service import answer_market_question
from market_regime import (
    get_large_vs_small_cap,
    get_market_breadth,
    get_market_regime_summary,
    get_sector_leadership,
)
from signal_engine import (
    attach_breakout_metrics,
    get_confirmed_breakout_signal,
    get_momentum_signal,
    get_near_breakout_signal,
    get_price_breakout_signal,
    get_relative_strength_signal,
    get_volume_spike_signal,
    price_breakout_mask,
    score_signals,
    volume_spike_mask,
)
from watchlist_builder import build_watchlist, watchlist_debug_summary
from visualization import (
    format_large_number,
    format_return_color,
    render_market_heatmap,
    render_subsector_heatmap,
)


st.set_page_config(
    page_title="TW Stock Trader Dashboard",
    layout="wide"
)

data_service.set_warn_fn(st.warning)

load_price_data = st.cache_data(_load_price_data)
load_valuation_data = st.cache_data(_load_valuation_data)

CHAT_SESSION_KEY = "ai_analyst_messages"

STOCK_DISPLAY_COLUMNS = [
    "stock_id",
    "stock_name",
    "industry",
    "sub_sector",
    "close",
    "return_pct",
    "amount",
    "turnover_ratio_20d",
    "turnover_percentile_60d",
    "hotness_score",
    "hotness_reason",
    "technical_score",
    "signal_reason",
]

WATCHLIST_TABLE_COLUMNS = [
    "stock_id",
    "stock_name",
    "industry",
    "sub_sector",
    "hotness_score",
    "hotness_reason",
    "technical_score",
    "signal_reason",
    "turnover_ratio_20d",
    "turnover_percentile_60d",
    "amount",
]

BREAKOUT_DISPLAY_COLUMNS = [
    "stock_id",
    "stock_name",
    "industry",
    "sub_sector",
    "close",
    "high_20d_prev",
    "breakout_distance_pct",
    "turnover_ratio_20d",
    "turnover_percentile_60d",
    "hotness_score",
    "technical_score",
    "amount",
]

DISPLAY_COLUMN_LABELS = {
    "amount": "Turnover",
    "turnover_ratio_20d": "Turnover / 20D Avg",
    "turnover_percentile_60d": "60D Turnover Percentile",
    "hotness_score": "Hotness Score",
    "hotness_reason": "Hotness Reason",
    "technical_score": "Technical Score",
    "signal_reason": "Technical Reason",
    "high_20d_prev": "Previous 20D High",
    "breakout_distance_pct": "Distance to 20D High (%)",
}

STOCK_TABLE_FORMAT = {
    "close": "{:,.2f}",
    "return_pct": "{:.2f}",
    "Turnover": "{:,.0f}",
    "Turnover / 20D Avg": "{:.2f}",
    "60D Turnover Percentile": "{:.1f}",
    "Hotness Score": "{:.1f}",
    "Technical Score": "{:.0f}",
    "Previous 20D High": "{:,.2f}",
    "Distance to 20D High (%)": "{:.2f}",
}


def _ensure_technical_score_column(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "technical_score" in work.columns:
        technical = pd.to_numeric(work["technical_score"], errors="coerce")
    else:
        technical = pd.Series(index=work.index, dtype=float)
    if "signal_score" in work.columns:
        signal = pd.to_numeric(work["signal_score"], errors="coerce")
        technical = technical.fillna(signal)
    work["technical_score"] = technical
    return work


def prepare_stock_display_df(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work = remove_duplicate_columns(apply_sector_mapping(enrich_industry_columns(df.copy())))
    if "industry" not in work.columns and "industry_name" in work.columns:
        work["industry"] = work["industry_name"]

    work = _ensure_technical_score_column(work)

    needs_scoring = (
        "hotness_score" not in work.columns
        or "signal_reason" not in work.columns
        or work["technical_score"].isna().all()
    )
    if market_return is not None and needs_scoring:
        work = score_signals(work, market_return)
        work = _ensure_technical_score_column(work)

    cols = [c for c in STOCK_DISPLAY_COLUMNS if c in work.columns]
    if not cols:
        return pd.DataFrame()
    return remove_duplicate_columns(work[cols].copy())


def format_stock_table(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame | Styler:
    display = prepare_stock_display_df(df, market_return)
    if display.empty:
        return display

    if "return_pct" in display.columns:
        display["return_pct"] = pd.to_numeric(display["return_pct"], errors="coerce")

    display = display.rename(columns=DISPLAY_COLUMN_LABELS)

    format_specs = {
        key: value for key, value in STOCK_TABLE_FORMAT.items() if key in display.columns
    }

    def _return_pct_style(value) -> str:
        color = format_return_color(value)
        return f"color: {color}; font-weight: 600"

    styler = display.style
    if "return_pct" in display.columns:
        styler = styler.map(_return_pct_style, subset=["return_pct"])
    if format_specs:
        styler = styler.format(format_specs)
    return styler


def prepare_watchlist_table_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work = remove_duplicate_columns(_ensure_technical_score_column(df.copy()))
    cols = [c for c in WATCHLIST_TABLE_COLUMNS if c in work.columns]
    if not cols:
        return pd.DataFrame()
    return work[cols].copy()


def format_watchlist_table(df: pd.DataFrame) -> pd.DataFrame | Styler:
    display = prepare_watchlist_table_df(df)
    if display.empty:
        return display

    display = display.rename(columns=DISPLAY_COLUMN_LABELS)
    format_specs = {
        key: value for key, value in STOCK_TABLE_FORMAT.items() if key in display.columns
    }
    styler = display.style
    if format_specs:
        styler = styler.format(format_specs)
    return styler


def show_watchlist_table(
    title: str,
    df: pd.DataFrame,
    height: int = 600,
    hide_index: bool = False,
) -> None:
    if title:
        st.subheader(title)
    if df is None or df.empty:
        st.info("No data available.")
        return

    styled = format_watchlist_table(df)
    st.dataframe(
        styled,
        use_container_width=True,
        height=height,
        hide_index=hide_index,
    )


def prepare_breakout_display_df(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work = remove_duplicate_columns(df.copy())
    if "breakout_distance_pct" not in work.columns:
        work = attach_breakout_metrics(work)
    if "stock_name" not in work.columns or "industry_name" not in work.columns:
        work = enrich_industry_columns(work)
    work = apply_sector_mapping(work)
    if "industry" not in work.columns and "industry_name" in work.columns:
        work["industry"] = work["industry_name"]

    if market_return is not None and "hotness_score" not in work.columns:
        work = score_signals(work, market_return)
    work = _ensure_technical_score_column(work)

    cols = [c for c in BREAKOUT_DISPLAY_COLUMNS if c in work.columns]
    if not cols:
        return pd.DataFrame()
    return work[cols].copy()


def _prepare_breakout_universe(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    work = remove_duplicate_columns(
        apply_sector_mapping(enrich_industry_columns(attach_breakout_metrics(df.copy())))
    )
    if "industry" not in work.columns and "industry_name" in work.columns:
        work["industry"] = work["industry_name"]

    if market_return is not None and "hotness_score" not in work.columns:
        work = score_signals(work, market_return)
    work = _ensure_technical_score_column(work)
    return work


def format_breakout_table(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame | Styler:
    display = prepare_breakout_display_df(df, market_return)
    if display.empty:
        return display

    display = display.rename(columns=DISPLAY_COLUMN_LABELS)
    format_specs = {
        key: value for key, value in STOCK_TABLE_FORMAT.items() if key in display.columns
    }
    styler = display.style
    if format_specs:
        styler = styler.format(format_specs)
    return styler


def show_breakout_table(
    title: str,
    df: pd.DataFrame,
    market_return: float | None = None,
    height: int = 420,
    hide_index: bool = False,
) -> None:
    if title:
        st.subheader(title)
    if df is None or df.empty:
        st.info("No data available.")
        return

    styled = format_breakout_table(df, market_return)
    st.dataframe(
        styled,
        use_container_width=True,
        height=height,
        hide_index=hide_index,
    )


def show_stock_table(
    title: str,
    df: pd.DataFrame,
    market_return: float | None = None,
    height: int = 420,
    hide_index: bool = False,
) -> None:
    if title:
        st.subheader(title)
    if df is None or df.empty:
        st.info("No data available.")
        return

    styled = format_stock_table(df, market_return)
    st.dataframe(
        styled,
        use_container_width=True,
        height=height,
        hide_index=hide_index,
    )


def prepare_llm_context(
    snapshot: dict,
    filtered: pd.DataFrame,
    valuation: pd.DataFrame,
    latest_date,
    min_liquidity_amount: int,
    keyword: str,
) -> dict:
    """Build compact JSON-serializable context (summary + top rows only, no raw dataframes)."""
    return build_llm_market_context(
        snapshot, filtered, valuation, latest_date, min_liquidity_amount, keyword
    )


def render_ai_analyst_chat(
    snapshot: dict,
    filtered: pd.DataFrame,
    valuation: pd.DataFrame,
    latest_date,
    min_liquidity_amount: int,
    keyword: str,
) -> None:
    st.caption(
        "根據儀表板摘要與觀察名單回答問題。僅供研究參考，不構成投資建議。"
    )

    if CHAT_SESSION_KEY not in st.session_state:
        st.session_state[CHAT_SESSION_KEY] = []

    for message in st.session_state[CHAT_SESSION_KEY]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("請輸入想了解的市場問題…")
    if not prompt:
        return

    st.session_state[CHAT_SESSION_KEY].append({"role": "user", "content": prompt})

    context = prepare_llm_context(
        snapshot, filtered, valuation, latest_date, min_liquidity_amount, keyword
    )

    with st.chat_message("assistant"):
        with st.spinner("分析中…"):
            answer = answer_market_question(prompt, context)
        st.markdown(answer)

    st.session_state[CHAT_SESSION_KEY].append({"role": "assistant", "content": answer})


def apply_snapshot_filters(
    latest: pd.DataFrame,
    min_liquidity_amount: float,
    min_turnover_percentile_60d: float,
    keyword: str = "",
) -> tuple[pd.DataFrame, bool]:
    """Apply liquidity, turnover percentile, and keyword filters to the latest snapshot."""
    filtered = latest.copy()

    if min_liquidity_amount > 0 and "amount" in filtered.columns:
        amount = pd.to_numeric(filtered["amount"], errors="coerce")
        filtered = filtered[amount >= min_liquidity_amount]

    percentile_available = False
    if "turnover_percentile_60d" in latest.columns:
        all_percentiles = pd.to_numeric(latest["turnover_percentile_60d"], errors="coerce")
        percentile_available = all_percentiles.notna().any()

    if percentile_available and min_turnover_percentile_60d > 0:
        pct = pd.to_numeric(filtered["turnover_percentile_60d"], errors="coerce")
        filtered = filtered[pct.isna() | (pct >= min_turnover_percentile_60d)]

    if keyword.strip():
        kw = keyword.strip()
        filtered = filtered[
            filtered["stock_id"].astype(str).str.contains(kw, case=False, na=False)
            | filtered["stock_name"].astype(str).str.contains(kw, case=False, na=False)
        ]

    return filtered, percentile_available


def apply_keyword_filter(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    if df is None or df.empty or not keyword.strip():
        return df
    kw = keyword.strip()
    return df[
        df["stock_id"].astype(str).str.contains(kw, case=False, na=False)
        | df["stock_name"].astype(str).str.contains(kw, case=False, na=False)
    ]


def render_breakout_section(
    latest: pd.DataFrame,
    sidebar_filtered: pd.DataFrame,
    market_return: float,
    keyword: str = "",
    section_caption: str | None = None,
) -> None:
    st.subheader("Breakout")
    st.caption(
        section_caption
        or "Breakout lists use the full latest session (keyword only). "
        "Liquidity and 60D turnover percentile sidebar filters do not apply here."
    )

    breakout_universe = apply_keyword_filter(enrich_industry_columns(latest.copy()), keyword)
    scored_universe = _prepare_breakout_universe(breakout_universe, market_return)
    sidebar_view = apply_keyword_filter(
        sidebar_filtered.copy() if sidebar_filtered is not None else pd.DataFrame(),
        keyword,
    )
    debug = breakout_debug_summary(scored_universe, sidebar_view)

    with st.expander("Breakout debug summary", expanded=False):
        d1, d2, d3, d4, d5 = st.columns(5)
        d1.metric("Valid high_20d_prev rows", f"{debug['valid_high_20d_prev_rows']:,}")
        d2.metric("Confirmed breakout count", f"{debug['confirmed_breakout_count']:,}")
        d3.metric("Price breakout count", f"{debug['price_breakout_count']:,}")
        d4.metric("Near breakout count", f"{debug['near_breakout_count']:,}")
        d5.metric("Rows removed by filters", f"{debug['rows_removed_by_filters']:,}")

    candidate_count = (
        debug["price_breakout_count"]
        + debug["confirmed_breakout_count"]
        + debug["near_breakout_count"]
    )
    if (
        debug["price_breakout_count"] > 0
        and debug["rows_removed_by_filters"] >= debug["price_breakout_count"]
    ):
        st.warning(
            "Sidebar liquidity or turnover percentile filters removed breakout-related "
            "candidates from the filtered universe. Breakout tables below show the "
            "unfiltered latest session."
        )
    elif candidate_count == 0:
        st.info(
            "No confirmed, price, or near breakout candidates on the latest session."
        )
    elif debug["price_breakout_count"] == 0 and debug["confirmed_breakout_count"] == 0:
        st.info(
            "No stock closed above the previous 20D high today. "
            "See Near Breakout Watchlist for names within 3% of the prior high."
        )

    show_breakout_table(
        "A. Confirmed Breakout (Close > 20D High and Turnover / 20D Avg ≥ 1.5×)",
        get_confirmed_breakout_signal(scored_universe).head(100),
        market_return,
        height=420,
    )
    show_breakout_table(
        "B. Price Breakout (Close > Previous 20D High)",
        get_price_breakout_signal(scored_universe).head(100),
        market_return,
        height=420,
    )

    st.markdown(
        "Near Breakout shows stocks trading within 3% below their previous 20D high. "
        "These are not confirmed breakouts, but may be useful watchlist candidates."
    )
    show_breakout_table(
        "C. Near Breakout Watchlist (Within 3% Below Previous 20D High)",
        get_near_breakout_signal(scored_universe, limit=100),
        market_return,
        height=480,
    )


def get_abnormal_turnover(filtered: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if filtered is None or filtered.empty:
        return pd.DataFrame()

    work = filtered.copy()
    pct = pd.to_numeric(work.get("turnover_percentile_60d"), errors="coerce")
    ratio = pd.to_numeric(work.get("turnover_ratio_20d"), errors="coerce")
    mask = (pct.notna() & (pct >= 90)) | (ratio.notna() & (ratio >= 2))
    result = work[mask].copy()
    if result.empty:
        return result

    sort_cols = [
        c for c in ("turnover_percentile_60d", "turnover_ratio_20d", "amount")
        if c in result.columns
    ]
    return result.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(limit)


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    display_df = remove_duplicate_columns(df.copy())
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(display_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    if "return_pct" in display_df.columns:
        display_df["return_pct"] = pd.to_numeric(display_df["return_pct"], errors="coerce")

    ordered_cols = [
        "signal_score",
        "volume_spike_signal",
        "breakout_signal",
        "price_breakout_signal",
        "confirmed_breakout_signal",
        "momentum_signal",
        "relative_strength_signal",
        "industry_name",
        "industry",
        "stock_count", "up_count", "down_count", "up_ratio",
        "avg_return_pct", "median_return_pct", "total_turnover",
        "volume_spike_count", "breakout_count", "sub_sector",
        "date", "stock_id", "stock_name", "close", "return_pct",
        "turnover_ma20", "turnover_ratio_20d", "turnover_percentile_60d",
        "high_turnover_percentile_signal", "extreme_turnover_percentile_signal",
        "turnover_ratio_spike_signal",
        "volume", "volume_ratio_20d", "amount", "ma5", "ma20",
        "high_20d_prev", "pe", "pb", "div_yield",
        "signal_reason", "observation_focus",
    ]
    cols = list(dict.fromkeys(c for c in ordered_cols if c in display_df.columns))
    other_cols = [c for c in display_df.columns if c not in cols]
    return remove_duplicate_columns(display_df[cols + other_cols])


def enrich_industry_columns(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.copy()
    if "industry" in enriched.columns:
        enriched["industry_name"] = enriched["industry"].apply(map_industry_to_name)
    else:
        enriched["industry_name"] = "Unknown"
    return enriched


def _format_return_label(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    color = format_return_color(numeric)
    if pd.isna(numeric):
        text = "N/A"
    elif float(numeric) == 0:
        text = "0.00%"
    else:
        text = f"{float(numeric):.2f}%"
    return f'<span style="color:{color}; font-weight:600;">{text}</span>'


def _format_count_metric(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{int(value):,}"


def _format_pct_metric(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{float(value):.2f}%"


def _format_ratio_metric(value, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{float(value):.{decimals}f}"


def _format_up_down_flat(breadth: dict) -> str:
    if not breadth.get("has_valid_returns"):
        return "N/A"
    return (
        f"{_format_count_metric(breadth.get('up_count'))} / "
        f"{_format_count_metric(breadth.get('down_count'))} / "
        f"{_format_count_metric(breadth.get('flat_count'))}"
    )


def compute_up_down_display(latest: pd.DataFrame) -> tuple[str, bool]:
    if "return_pct" not in latest.columns:
        return "N/A / N/A", False
    valid_returns = latest[latest["return_pct"].notna()].copy()
    if valid_returns.empty:
        return "N/A / N/A", False
    up_count = int((valid_returns["return_pct"] > 0).sum())
    down_count = int((valid_returns["return_pct"] < 0).sum())
    return f"{up_count:,} / {down_count:,}", True


def build_watchlist_universe(latest: pd.DataFrame, market_return: float) -> pd.DataFrame:
    universe = apply_sector_mapping(enrich_industry_columns(latest))
    if "signal_score" not in universe.columns:
        universe = score_signals(universe, market_return)
    return universe


def build_watchlist_df(
    latest: pd.DataFrame,
    market_return: float,
    min_liquidity_amount: int,
    wl_min_hotness_score: float,
    wl_min_technical_score: int,
    wl_industry: str,
    wl_sub_sector: str,
) -> pd.DataFrame:
    universe = build_watchlist_universe(latest, market_return)
    return build_watchlist(
        universe,
        max_rows=50,
        min_amount=min_liquidity_amount,
        min_hotness_score=wl_min_hotness_score,
        min_technical_score=wl_min_technical_score,
        industry=wl_industry,
        sub_sector=wl_sub_sector,
    )


def _escape_html_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return html.escape(text)


def _format_turnover_ratio_display(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "N/A"
    return f"{float(numeric):.2f}x"


def _format_turnover_percentile_display(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "N/A"
    return f"{float(numeric):.1f}"


def _build_watchlist_card_html(rank: int, row: pd.Series) -> str:
    stock_id = _escape_html_text(row.get("stock_id"))
    stock_name = _escape_html_text(row.get("stock_name"))
    industry = _escape_html_text(row.get("industry") or row.get("industry_name"))
    sub_sector = _escape_html_text(row.get("sub_sector"))
    if industry and sub_sector:
        sector_line = f"{industry} / {sub_sector}"
    else:
        sector_line = industry or sub_sector or "—"

    return_label = _format_return_label(row.get("return_pct"))

    hotness = pd.to_numeric(row.get("hotness_score"), errors="coerce")
    technical = pd.to_numeric(row.get("technical_score"), errors="coerce")
    if pd.isna(technical):
        technical = pd.to_numeric(row.get("signal_score"), errors="coerce")
    hotness_text = "N/A" if pd.isna(hotness) else f"{float(hotness):.1f}"
    technical_text = "N/A" if pd.isna(technical) else f"{int(technical)}"

    amount_text = format_large_number(row.get("amount"))
    ratio_text = _format_turnover_ratio_display(row.get("turnover_ratio_20d"))
    percentile_text = _format_turnover_percentile_display(row.get("turnover_percentile_60d"))

    reason = _escape_html_text(row.get("hotness_reason")) or "—"
    signal_reason = _escape_html_text(row.get("signal_reason")) or "—"
    focus = _escape_html_text(row.get("observation_focus")) or "—"

    return f"""
<div style="
  border: 1px solid #d0d7de;
  border-radius: 12px;
  background: #f8f9fa;
  padding: 16px 20px;
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  align-items: flex-start;
  width: 100%;
  box-sizing: border-box;
">
  <div style="flex: 1 1 220px; min-width: 200px;">
    <div style="font-size: 1.15rem; font-weight: 700; line-height: 1.4;">
      <span style="color: #6c757d; margin-right: 8px;">#{rank}</span>
      {stock_id} {stock_name}
    </div>
    <div style="color: #6c757d; font-size: 0.9rem; margin-top: 6px;">{sector_line}</div>
  </div>

  <div style="flex: 1 1 240px; min-width: 220px;">
    <div style="margin-bottom: 8px;"><strong>Return</strong> {return_label}</div>
    <div style="margin-bottom: 8px;">
      <strong>Hotness Score</strong>
      <span style="
        display: inline-block;
        margin-left: 8px;
        font-size: 1.45rem;
        font-weight: 800;
        color: #0b5ed7;
        line-height: 1;
      ">{hotness_text}</span>
      <span style="margin-left: 12px; font-size: 0.92rem;">
        <strong>Technical Score</strong> {technical_text}
      </span>
    </div>
    <div style="margin-bottom: 6px; font-size: 0.92rem;"><strong>Turnover</strong> {amount_text}</div>
    <div style="margin-bottom: 6px; font-size: 0.92rem;"><strong>Turnover / 20D Avg</strong> {ratio_text}</div>
    <div style="font-size: 0.92rem;"><strong>60D Turnover Percentile</strong> {percentile_text}</div>
  </div>

  <div style="flex: 2 1 320px; min-width: 260px;">
    <div style="margin-bottom: 10px; font-size: 0.92rem; line-height: 1.45;">
      <strong>Hotness Reason</strong><br>{reason}
    </div>
    <div style="margin-bottom: 10px; font-size: 0.92rem; line-height: 1.45;">
      <strong>Technical Reason</strong><br>{signal_reason}
    </div>
    <div style="font-size: 0.92rem; line-height: 1.45; color: #495057;">
      <strong>Observation Focus</strong><br>{focus}
    </div>
  </div>
</div>
"""


def render_watchlist_cards(watchlist_df: pd.DataFrame, max_cards: int = 10) -> None:
    if watchlist_df is None or watchlist_df.empty:
        return

    display_df = remove_duplicate_columns(_ensure_technical_score_column(watchlist_df.copy()))

    if "stock_id" in display_df.columns:
        display_df = display_df.drop_duplicates(subset=["stock_id"], keep="first")

    sort_cols: list[str] = []
    for col in (
        "hotness_score",
        "technical_score",
        "turnover_percentile_60d",
        "amount",
    ):
        if col in display_df.columns:
            display_df[col] = pd.to_numeric(display_df[col], errors="coerce")
            sort_cols.append(col)
    if sort_cols:
        display_df = display_df.sort_values(sort_cols, ascending=[False] * len(sort_cols))

    display_df = display_df.head(max_cards).copy()
    if display_df.empty:
        return

    display_df = apply_sector_mapping(enrich_industry_columns(display_df))
    if "industry" not in display_df.columns and "industry_name" in display_df.columns:
        display_df["industry"] = display_df["industry_name"]

    st.subheader(f"Top {len(display_df)} Watchlist")

    for rank, (_, row) in enumerate(display_df.iterrows(), start=1):
        st.markdown(_build_watchlist_card_html(rank, row), unsafe_allow_html=True)



def render_market_data_debug(
    show_debug_info: bool,
    price: pd.DataFrame,
    latest: pd.DataFrame,
    snapshot: dict,
    latest_date,
    valid_returns: pd.DataFrame,
) -> None:
    if not show_debug_info:
        return

    with st.expander("Market data debug", expanded=False):
        min_date = snapshot.get("min_date")
        max_date = snapshot.get("max_date")
        return_pct = pd.to_numeric(latest["return_pct"], errors="coerce")
        unique_dates = int(price["date"].nunique()) if not price.empty else 0
        st.write(f"Latest rows count: {len(latest):,}")
        st.write(f"Valid return_pct rows count: {len(valid_returns):,}")
        st.write(f"Unique dates in price data: {unique_dates:,}")
        st.write(f"return_pct == 0 count: {int((return_pct == 0).sum()):,}")
        st.write(f"return_pct is NaN count: {int(return_pct.isna().sum()):,}")
        st.write(f"Latest date: {latest_date.strftime('%Y-%m-%d')}")
        st.write(
            f"Min date: {min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else 'N/A'}"
        )
        st.write(
            f"Max date: {max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else 'N/A'}"
        )
        debug_cols = [
            c for c in ["stock_id", "close", "prev_close", "return_pct"]
            if c in latest.columns
        ]
        if debug_cols:
            st.caption("First 20 rows: stock_id, close, prev_close, return_pct")
            st.dataframe(
                remove_duplicate_columns(latest[debug_cols].head(20)),
                use_container_width=True,
                hide_index=True,
            )


def render_visual_overview(
    filtered: pd.DataFrame,
    latest: pd.DataFrame,
    snapshot: dict,
    latest_date,
    market_return: float,
    min_liquidity_amount: int,
    wl_min_hotness_score: float,
    wl_min_technical_score: int,
    wl_industry: str,
    wl_sub_sector: str,
    show_debug_info: bool = False,
    price: pd.DataFrame | None = None,
    valid_returns: pd.DataFrame | None = None,
) -> None:
    st.caption("Trader workstation view — market KPIs and top watchlist cards.")

    up_down_display, has_valid_returns = compute_up_down_display(latest)
    volume_spike_count = int(volume_spike_mask(filtered).sum()) if not filtered.empty else 0
    breakout_count = int(price_breakout_mask(latest).sum()) if not latest.empty else 0

    if not has_valid_returns:
        st.warning(
            "Return data unavailable because historical price data is insufficient."
        )

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Date", latest_date.strftime("%Y-%m-%d"))
    k2.metric("Stocks", f"{snapshot['stock_count']:,}")
    k3.metric("Up / Down", up_down_display)
    k4.metric("Total Turnover", f"{snapshot['total_turnover']:,.0f}")
    k5.metric("Volume Spike Count", f"{volume_spike_count:,}")
    k6.metric("Breakout Count", f"{breakout_count:,}")

    st.markdown("---")

    watchlist = build_watchlist_df(
        latest,
        market_return,
        min_liquidity_amount,
        wl_min_hotness_score,
        wl_min_technical_score,
        wl_industry,
        wl_sub_sector,
    )
    if not watchlist.empty:
        render_watchlist_cards(watchlist, max_cards=10)
    else:
        st.subheader("Watchlist Highlights")
        st.info("No watchlist stocks available for card view with current filters.")

    if show_debug_info and price is not None and valid_returns is not None:
        st.markdown("---")
        render_market_data_debug(
            show_debug_info, price, latest, snapshot, latest_date, valid_returns
        )


def apply_signal_scanner_filters(
    df: pd.DataFrame,
    industry: str,
    sub_sector: str,
) -> pd.DataFrame:
    filtered = df.copy()
    if industry != "All" and "industry_name" in filtered.columns:
        filtered = filtered[filtered["industry_name"] == industry]
    if sub_sector != "All" and "sub_sector" in filtered.columns:
        filtered = filtered[filtered["sub_sector"].astype(str) == sub_sector]
    return filtered


def render_signal_scanner(
    latest: pd.DataFrame,
    filtered: pd.DataFrame,
    market_return: float,
    keyword: str = "",
) -> None:
    st.caption(
        "Scan latest-market signals. Breakout lists ignore sidebar liquidity and turnover "
        "percentile filters. Other scanner tables use sidebar filters. "
        "Sub-sector filter uses sector_mapping.csv labels."
    )

    if latest.empty:
        st.info("No market data available.")
        return

    universe = enrich_industry_columns(filtered if not filtered.empty else latest)

    col1, col2 = st.columns(2)
    with col1:
        industry_options = ["All"] + sorted(
            universe["industry_name"].dropna().unique().tolist()
        )
        selected_industry = st.selectbox(
            "Industry",
            industry_options,
            key="scanner_industry",
        )
    with col2:
        sub_sector_pool = universe
        if selected_industry != "All":
            sub_sector_pool = sub_sector_pool[
                sub_sector_pool["industry_name"] == selected_industry
            ]
        if "sub_sector" in sub_sector_pool.columns:
            sub_sector_labels = sorted(
                sub_sector_pool["sub_sector"].dropna().astype(str).unique().tolist()
            )
        else:
            sub_sector_labels = []
        selected_sub_sector = st.selectbox(
            "Sub-sector",
            ["All"] + sub_sector_labels,
            key="scanner_sub_sector",
        )

    scanner_df = apply_signal_scanner_filters(
        universe, selected_industry, selected_sub_sector
    )

    breakout_universe = apply_signal_scanner_filters(
        apply_keyword_filter(enrich_industry_columns(latest.copy()), keyword),
        selected_industry,
        selected_sub_sector,
    )

    if scanner_df.empty and breakout_universe.empty:
        st.info("No stocks match the current Signal Scanner filters.")
        return

    if not scanner_df.empty:
        show_stock_table(
            "Volume Spike Signal",
            get_volume_spike_signal(scanner_df).head(100),
            market_return,
        )
    else:
        st.info("No volume spike signals under current scanner filters.")

    st.markdown("---")
    render_breakout_section(
        latest=breakout_universe,
        sidebar_filtered=scanner_df,
        market_return=market_return,
        keyword="",
        section_caption=(
            "Breakout lists use the latest session with industry/sub-sector scanner filters only. "
            "Sidebar liquidity and 60D turnover percentile filters do not apply."
        ),
    )

    if not scanner_df.empty:
        show_stock_table(
            "Momentum Signal",
            get_momentum_signal(scanner_df).head(100),
            market_return,
        )
        show_stock_table(
            "Relative Strength Signal",
            get_relative_strength_signal(scanner_df, market_return).head(100),
            market_return,
        )

        ranked = _ensure_technical_score_column(
            score_signals(scanner_df, market_return)
        )
        ranked = ranked[ranked["technical_score"].fillna(0) > 0].head(100)
        show_stock_table("Combined Signal Ranking", ranked, market_return, height=600)


def render_subsector_trend(filtered: pd.DataFrame) -> None:
    st.caption("Sub-sector aggregates from sector_mapping.csv.")

    if load_sector_mapping().empty:
        st.warning(
            "sector_mapping.csv not found or empty. "
            f"All stocks are grouped as '{DEFAULT_SUB_SECTOR}'."
        )

    exclude_unclassified = st.checkbox(
        f'Exclude "{DEFAULT_SUB_SECTOR}"',
        value=False,
        key="subsector_exclude_unclassified",
    )

    subsector_df = get_subsector_trend(filtered)
    subsector_df = remove_duplicate_columns(subsector_df)

    if subsector_df.empty:
        st.info("No sub-sector trend data available.")
        return

    if exclude_unclassified:
        subsector_df = subsector_df[subsector_df["sub_sector"] != DEFAULT_SUB_SECTOR].copy()
        if subsector_df.empty:
            st.info(f"No mapped sub-sectors after excluding '{DEFAULT_SUB_SECTOR}'.")
            return

    cols = [
        "sub_sector",
        "stock_count",
        "up_count",
        "down_count",
        "up_ratio",
        "avg_return_pct",
        "median_return_pct",
        "total_turnover",
        "volume_spike_count",
        "breakout_count",
    ]
    subsector_df = remove_duplicate_columns(subsector_df)
    subsector_df = subsector_df[[c for c in cols if c in subsector_df.columns]]

    show_table(
        "Sub-sector Trend",
        subsector_df,
        height=600,
        hide_index=True,
    )


def render_sector_theme(filtered: pd.DataFrame, snapshot: dict) -> None:
    st.caption(
        "Sector and theme rotation — treemap heatmaps plus industry and sub-sector tables."
    )

    industry_trend = remove_duplicate_columns(get_industry_trend(filtered))
    subsector_trend = remove_duplicate_columns(get_subsector_trend(filtered))

    st.subheader("Heatmaps")
    heatmap_left, heatmap_right = st.columns(2)
    with heatmap_left:
        st.markdown("**Industry Heatmap**")
        market_fig = render_market_heatmap(industry_trend)
        if market_fig is not None:
            st.plotly_chart(market_fig, use_container_width=True)
        else:
            st.info("No industry heatmap data available.")

    with heatmap_right:
        st.markdown("**Sub-sector Heatmap**")
        subsector_fig = render_subsector_heatmap(subsector_trend)
        if subsector_fig is not None:
            st.plotly_chart(subsector_fig, use_container_width=True)
        else:
            st.info("No sub-sector heatmap data available.")

    st.markdown("---")
    st.subheader("Industry Trend")
    if not snapshot.get("industry_profile_loaded", False):
        st.warning(
            "Industry profile data not found (t187ap03_L.parquet under quant_data/). "
            "All stocks are grouped as 'Unknown'."
        )
    elif snapshot.get("industry_unknown_count", 0) > 0:
        st.warning(
            f"Industry unknown for {snapshot['industry_unknown_count']:,} stock(s). "
            "Those stocks are grouped as 'Unknown'."
        )
    show_table(
        "Industry Trend by Sector",
        industry_trend,
        height=600,
        hide_index=True,
    )

    st.markdown("---")
    render_subsector_trend(filtered)


def render_market_tables(
    latest: pd.DataFrame,
    filtered: pd.DataFrame,
    market_return: float,
    keyword: str = "",
) -> None:
    st.caption(
        "Market scan and signal-based stock lists. Breakout ignores sidebar liquidity and "
        "turnover percentile filters; other sections use sidebar filters."
    )

    st.subheader("Market Scan")
    show_table("Top Gainers", get_top_gainers(filtered))
    show_table("Top Losers", get_top_losers(filtered))

    st.markdown("---")
    st.subheader("Volume Spike")
    show_stock_table(
        "Volume Spike: Volume >= 2x 20D Average",
        get_volume_spike_signal(filtered).head(100),
        market_return,
    )

    st.markdown("---")
    render_breakout_section(latest, filtered, market_return, keyword=keyword)

    st.markdown("---")
    st.subheader("Top Liquidity")
    show_table("Top Liquidity", get_top_turnover(filtered))
    show_table("Abnormal Turnover", get_abnormal_turnover(filtered))


def render_raw_data(filtered: pd.DataFrame) -> None:
    st.caption("Unaggregated latest-session rows after sidebar filters.")
    show_table(
        "Latest Raw Price Data",
        filtered.sort_values("amount", ascending=False),
        height=600,
    )


def render_watchlist(
    latest: pd.DataFrame,
    latest_date,
    market_return: float,
    min_liquidity_amount: int,
    wl_min_hotness_score: float,
    wl_min_technical_score: int,
    wl_industry: str,
    wl_sub_sector: str,
) -> None:
    st.caption(
        "Rule-based watchlist ranked by market hotness, with technical setup quality shown "
        "alongside. Sub-sector labels come from sector_mapping.csv."
    )

    universe = build_watchlist_universe(latest, market_return)

    watchlist = build_watchlist(
        universe,
        max_rows=50,
        min_amount=min_liquidity_amount,
        min_hotness_score=wl_min_hotness_score,
        min_technical_score=wl_min_technical_score,
        industry=wl_industry,
        sub_sector=wl_sub_sector,
    )

    if watchlist.empty:
        st.info(
            "No stocks match the current watchlist filters. "
            "Try lowering the minimum hotness score or liquidity threshold."
        )
        debug = watchlist_debug_summary(
            universe,
            min_liquidity_amount,
            wl_min_hotness_score,
            wl_min_technical_score,
            wl_industry,
            wl_sub_sector,
        )
        st.subheader("Watchlist Debug Summary")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Latest rows", f"{debug['latest_rows']:,}")
        d2.metric("Rows amount >= threshold", f"{debug['rows_with_amount']:,}")
        d3.metric("Rows hotness >= threshold", f"{debug['rows_with_hotness_score']:,}")
        d4.metric("Max hotness score", f"{debug['max_hotness_score']:.1f}")
        if not debug["top_activity_stocks"].empty:
            st.caption("Top 10 stocks by abnormal activity")
            st.dataframe(
                remove_duplicate_columns(debug["top_activity_stocks"]),
                use_container_width=True,
                hide_index=True,
            )
        return

    render_watchlist_cards(watchlist, max_cards=10)
    st.markdown("---")
    show_watchlist_table("Today's Watchlist", watchlist, height=600, hide_index=True)

    csv_data = watchlist.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="Download watchlist CSV",
        data=csv_data,
        file_name=f"watchlist_{latest_date.strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )


def render_market_regime(latest: pd.DataFrame) -> None:
    st.caption("Rule-based market regime view for the latest trading session.")

    if latest.empty:
        st.info("No market data available for regime analysis.")
        return

    industry_df = get_industry_trend(latest)
    breadth = get_market_breadth(latest)
    cap_comparison = get_large_vs_small_cap(latest)
    sector_leadership = get_sector_leadership(industry_df)
    summary = get_market_regime_summary(breadth, cap_comparison, sector_leadership)

    if not breadth.get("has_valid_returns"):
        st.warning(
            "Return data unavailable because historical price data is insufficient."
        )

    st.subheader("Market Breadth")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Total Stocks", _format_count_metric(breadth.get("total_stocks")))
    b2.metric("Up / Down / Flat", _format_up_down_flat(breadth))
    b3.metric(
        "Up Ratio",
        "N/A"
        if breadth.get("up_ratio") is None
        else f"{float(breadth['up_ratio']) * 100:.1f}%",
    )
    b4.metric(
        "Advance/Decline",
        _format_ratio_metric(breadth.get("advance_decline_ratio")),
    )

    b5, b6 = st.columns(2)
    b5.metric("Average Return", _format_pct_metric(breadth.get("average_return")))
    b6.metric("Median Return", _format_pct_metric(breadth.get("median_return")))

    st.subheader("Large Cap vs Small Cap")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Large Cap Avg Return",
        _format_pct_metric(cap_comparison.get("large_cap_avg_return")),
    )
    c2.metric(
        "Small Cap Avg Return",
        _format_pct_metric(cap_comparison.get("small_cap_avg_return")),
    )
    c3.metric(
        "Large Cap Up Ratio",
        "N/A"
        if cap_comparison.get("large_cap_up_ratio") is None
        else f"{float(cap_comparison['large_cap_up_ratio']) * 100:.1f}%",
    )
    c4.metric(
        "Small Cap Up Ratio",
        "N/A"
        if cap_comparison.get("small_cap_up_ratio") is None
        else f"{float(cap_comparison['small_cap_up_ratio']) * 100:.1f}%",
    )
    st.caption(
        "Large cap: top 30% by turnover. Small cap: bottom 30% by turnover."
    )

    st.subheader("Sector Leadership")
    if industry_df.empty:
        st.info("No industry data available.")
    else:
        sector_table = industry_df.sort_values(
            ["avg_return_pct", "total_turnover"], ascending=[False, False]
        )
        show_table("", sector_table, height=420, hide_index=True)

    st.subheader("Market Regime Summary")
    st.markdown(summary)


def render_methodology_guide() -> None:
    st.caption(
        "Reference guide for dashboard metrics, signals, and watchlist methodology."
    )

    st.markdown("### A. Dashboard Purpose")
    st.markdown(
        """
This dashboard is a **trader research tool**, not a buy/sell recommendation system.
It is designed to help you:

- Assess **market regime** (breadth, size/style behavior, sector leadership)
- Monitor **sector and sub-sector rotation**
- Surface **abnormal turnover activity** relative to each stock's own history
- Build a **rule-based watchlist** of candidates worth further research

All outputs are deterministic and based on price, volume, and turnover data.
They should be combined with your own judgment, risk controls, and additional research.
        """
    )

    st.markdown("### B. Key Metrics")
    st.markdown(
        """
| Metric | Definition |
|--------|------------|
| **Turnover / Amount** | Total traded value (price × volume). Used mainly as a **liquidity filter**, not as a standalone alpha signal. Large-cap names naturally rank higher on raw turnover. |
| **Turnover / 20D Avg** | Today's turnover divided by the stock's 20-day average turnover. Values above 1.0 mean above-normal money flow; **≥ 2.0** indicates a significant spike relative to recent history. |
| **60D Turnover Percentile** | Today's turnover ranked against the same stock's prior 60 trading-day observations. **90** means today's turnover exceeds 90% of its own past 60 observations — a stock-specific abnormal activity measure. |
| **Return %** | Daily percentage change versus the previous close: `(close / prev_close − 1) × 100`. |
| **Volume Ratio 20D** | Today's share volume divided by the 20-day average volume. Complements turnover-based activity measures. |
| **Liquidity Amount** | Sidebar minimum turnover threshold. Stocks below this level are excluded to avoid illiquid names. This filter does **not** add to Hotness Score or Technical Score. |
        """
    )

    st.markdown("### C. Scoring System")
    st.markdown(
        """
The dashboard uses **two independent scores** to surface candidates for further research.
Neither score is a buy or sell recommendation. Both are rule-based summaries of the latest
session's data.
        """
    )

    st.markdown("#### Hotness Score")
    st.markdown(
        """
**Purpose:** Measures **market attention and popularity** on a **0–100** scale — how much
interest a stock is attracting relative to its own history, the broader market, and its
sector context.

Hotness Score does **not** tell you whether to buy or sell. It identifies names that are
currently standing out in terms of activity and attention.
        """
    )

    hotness_table = pd.DataFrame(
        [
            {"Component": "Turnover Percentile 60D", "Maximum Points": 30},
            {"Component": "Turnover / 20D Avg", "Maximum Points": 20},
            {"Component": "Relative Strength", "Maximum Points": 20},
            {"Component": "Sector / Sub-sector Heat", "Maximum Points": 15},
            {"Component": "Raw Turnover Participation", "Maximum Points": 10},
            {"Component": "Technical Confirmation Bonus", "Maximum Points": 5},
            {"Component": "Total maximum", "Maximum Points": 100},
        ]
    )
    st.table(hotness_table)

    st.markdown(
        """
**How to read it:** The main drivers of Hotness Score are **abnormal turnover relative to
the stock's own history** (percentile and 20D ratio), **relative strength** versus the
market, and **sector / theme heat**. These components carry most of the weight.

**Raw turnover participation:** Raw turnover (amount) is included only as a **small
participation component** (maximum 10 points). It helps prevent illiquid names from ranking
too highly when other activity signals are weak, but it **does not dominate** the score.
It does not replace turnover percentile or turnover ratio — a stock cannot score highly on
hotness from raw size alone.

The sidebar **Minimum Liquidity Amount** is a separate **filter** that removes names too
illiquid for practical research. It is not a scoring component.
        """
    )

    st.markdown("#### Technical Score")
    st.markdown(
        """
**Purpose:** Measures **technical setup quality** — how many independent technical patterns
are active on the latest bar. Technical Score reflects the strength of the price and activity
setup, independent of market-wide attention.
        """
    )

    technical_table = pd.DataFrame(
        [
            {"Component": "Confirmed Breakout", "Points": "+3"},
            {"Component": "Price Breakout only", "Points": "+1"},
            {"Component": "Relative Strength", "Points": "+2"},
            {"Component": "Turnover / 20D Avg ≥ 2", "Points": "+2"},
            {"Component": "Turnover Percentile 60D ≥ 95", "Points": "+2"},
            {"Component": "Turnover Percentile 60D ≥ 90 (not ≥ 95)", "Points": "+1"},
            {"Component": "Momentum", "Points": "+1"},
        ]
    )
    st.table(technical_table)

    st.markdown(
        """
Technical Score components are additive. Multiple conditions can be met on the same session.
The legacy `signal_score` column, when present in underlying data, is displayed as
**Technical Score** for backward compatibility.
        """
    )

    st.markdown("#### Watchlist Ranking")
    st.markdown(
        """
The watchlist combines both scores with a liquidity gate:

1. **Liquidity filter** — stocks below the minimum liquidity amount (default: NT$ 50M) are
   excluded. This removes names that are too illiquid; it does not add to either score.
2. **Hotness threshold** — stocks must meet the sidebar minimum hotness score (default: 20).
3. **Optional technical floor** — an advanced filter can require a minimum technical score.
4. **Default ranking** — candidates are sorted by **Hotness Score** (descending) first.
   **Technical Score** is the secondary sort key, followed by 60D turnover percentile and
   amount.

**Visual Overview** displays the top 10 watchlist cards. The **Watchlist** tab shows the
full ranked list (up to 50 rows) with CSV download.
        """
    )

    st.markdown("### D. Interpretation Notes")
    st.markdown(
        """
- **High turnover alone does not mean buy.** A large company can have high absolute turnover every day without abnormal activity. Raw turnover adds at most 10 hotness points; percentile and ratio matter more.
- **Turnover percentile is more meaningful than raw turnover.** It compares today's activity against the stock's own recent history.
- **Breakout with turnover expansion is stronger than breakout alone.** A price breakout accompanied by elevated turnover ratio or percentile suggests broader participation.
- **Insufficient history produces N/A values.** Metrics such as Turnover / 20D Avg and 60D Turnover Percentile require adequate trading history (typically 20+ and 60+ prior observations per stock). When history is limited, filters may be skipped and warnings will appear.
- **Taiwan color convention:** positive returns are shown in red; negative returns in green.
        """
    )


def show_table(
    title: str, df: pd.DataFrame, height: int = 420, hide_index: bool = False
):
    if title:
        st.subheader(title)
    if df is None or df.empty:
        st.info("No data available.")
    else:
        df = remove_duplicate_columns(df)
        st.dataframe(
            format_table(df),
            use_container_width=True,
            height=height,
            hide_index=hide_index,
        )


def main():
    st.title("TW Stock Daily Trader Dashboard")
    st.caption("Local dashboard powered by your TWSE data pipeline.")

    if not QUANT_DIR.exists():
        st.error("Cannot find quant_data/. Please run `python3 main.py` first.")
        return

    price = add_price_indicators(load_price_data())
    valuation = load_valuation_data()

    if price.empty:
        st.error("Cannot find price data. Please make sure STOCK_DAY_ALL.parquet exists under quant_data/.")
        return

    latest_date = price["date"].max()
    latest = price[price["date"] == latest_date].copy()
    if "return_pct" not in latest.columns:
        latest["return_pct"] = pd.NA

    snapshot = get_latest_market_snapshot(price)
    latest = merge_industry_into_snapshot(latest, load_company_profile())
    latest = apply_sector_mapping(latest)

    st.sidebar.header("Filters")

    min_turnover_percentile_60d = st.sidebar.slider(
        "Minimum 60D Turnover Percentile",
        min_value=0,
        max_value=100,
        value=80,
        step=5,
        key="min_turnover_percentile_60d",
    )

    min_liquidity_amount = st.sidebar.number_input(
        "Minimum Liquidity Amount",
        min_value=0,
        value=50_000_000,
        step=1_000_000,
        key="min_liquidity_amount",
        help="Exclude illiquid stocks. Filter only — does not affect Hotness or Technical scores.",
    )

    keyword = st.sidebar.text_input("Search stock code or name")

    st.sidebar.header("Watchlist")
    wl_min_hotness_score = st.sidebar.slider(
        "Minimum Hotness Score",
        min_value=0,
        max_value=100,
        value=20,
        step=1,
        key="wl_min_hotness_score",
        help="Primary watchlist filter. Ranks by market attention (0–100).",
    )

    with st.sidebar.expander("Advanced watchlist filters"):
        wl_min_technical_score = st.number_input(
            "Minimum Technical Score",
            min_value=0,
            value=0,
            step=1,
            key="wl_min_technical_score",
            help="Optional floor on technical setup quality. Does not affect ranking.",
        )

    watchlist_universe = enrich_industry_columns(latest)
    wl_industry_options = ["All"]
    if "industry_name" in watchlist_universe.columns:
        wl_industry_options += sorted(
            watchlist_universe["industry_name"].dropna().unique().tolist()
        )
    elif "industry" in watchlist_universe.columns:
        wl_industry_options += sorted(
            watchlist_universe["industry"].dropna().astype(str).unique().tolist()
        )

    wl_industry = st.sidebar.selectbox(
        "Watchlist industry",
        wl_industry_options,
        key="wl_industry",
    )

    wl_sub_sector_pool = watchlist_universe
    if wl_industry != "All" and "industry_name" in watchlist_universe.columns:
        wl_sub_sector_pool = watchlist_universe[
            watchlist_universe["industry_name"] == wl_industry
        ]
    elif wl_industry != "All" and "industry" in watchlist_universe.columns:
        wl_sub_sector_pool = watchlist_universe[
            watchlist_universe["industry"].astype(str) == wl_industry
        ]

    wl_sub_sector_options = ["All"]
    if "sub_sector" in wl_sub_sector_pool.columns:
        wl_sub_sector_options += sorted(
            wl_sub_sector_pool["sub_sector"].dropna().astype(str).unique().tolist()
        )

    wl_sub_sector = st.sidebar.selectbox(
        "Watchlist sub-sector",
        wl_sub_sector_options,
        key="wl_sub_sector",
    )

    show_debug_info = st.sidebar.checkbox(
        "Show debug info",
        value=False,
        key="show_debug_info",
    )

    filtered, percentile_available = apply_snapshot_filters(
        latest,
        min_liquidity_amount,
        min_turnover_percentile_60d,
        keyword,
    )

    if not percentile_available:
        st.warning(
            "60D turnover percentile is unavailable because historical data is insufficient."
        )

    valid_returns = latest[latest["return_pct"].notna()].copy()
    if not valid_returns.empty:
        med = valid_returns["return_pct"].median()
        market_return = float(med) if pd.notna(med) else 0.0
    else:
        market_return = 0.0

    (
        tab_visual,
        tab_regime,
        tab_watchlist,
        tab_sector,
        tab_scanner,
        tab_market_tables,
        tab_valuation,
        tab_methodology,
        tab_raw,
        tab_chat,
    ) = st.tabs([
        "Visual Overview",
        "Market Regime",
        "Watchlist",
        "Sector & Theme",
        "Signal Scanner",
        "Market Tables",
        "Valuation",
        "Methodology",
        "Raw Data",
        "AI Analyst Chat",
    ])

    with tab_visual:
        render_visual_overview(
            filtered,
            latest,
            snapshot,
            latest_date,
            market_return,
            min_liquidity_amount,
            wl_min_hotness_score,
            wl_min_technical_score,
            wl_industry,
            wl_sub_sector,
            show_debug_info=show_debug_info,
            price=price,
            valid_returns=valid_returns,
        )

    with tab_regime:
        render_market_regime(latest)

    with tab_watchlist:
        render_watchlist(
            latest,
            latest_date,
            market_return,
            min_liquidity_amount,
            wl_min_hotness_score,
            wl_min_technical_score,
            wl_industry,
            wl_sub_sector,
        )

    with tab_sector:
        render_sector_theme(filtered, snapshot)

    with tab_scanner:
        render_signal_scanner(latest, filtered, market_return, keyword)

    with tab_market_tables:
        render_market_tables(latest, filtered, market_return, keyword)

    with tab_valuation:
        if valuation.empty:
            st.info("No valuation data available.")
        else:
            show_table("Cheap Value: PE <= 15 and PB <= 1.5", get_cheap_value(valuation))
            show_table("High Dividend: Dividend Yield >= 4%", get_high_dividend(valuation))

    with tab_methodology:
        render_methodology_guide()

    with tab_raw:
        render_raw_data(filtered)

    with tab_chat:
        render_ai_analyst_chat(
            snapshot, filtered, valuation, latest_date, min_liquidity_amount, keyword
        )


if __name__ == "__main__":
    main()
