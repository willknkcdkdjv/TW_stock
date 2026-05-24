import pandas as pd
import streamlit as st

import data_service
from data_service import (
    QUANT_DIR,
    add_price_indicators,
    apply_sector_mapping,
    build_llm_market_context,
    DEFAULT_SUB_SECTOR,
    get_breakout,
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
    get_volume_spike,
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
    get_breakout_signal,
    get_momentum_signal,
    get_relative_strength_signal,
    get_volume_spike_signal,
    score_signals,
)
from watchlist_builder import build_watchlist, watchlist_debug_summary
from visualization import (
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


def prepare_llm_context(
    snapshot: dict,
    filtered: pd.DataFrame,
    valuation: pd.DataFrame,
    latest_date,
    min_amount: int,
    keyword: str,
) -> dict:
    """Build compact JSON-serializable context (summary + top rows only, no raw dataframes)."""
    return build_llm_market_context(
        snapshot, filtered, valuation, latest_date, min_amount, keyword
    )


def render_ai_analyst_chat(
    snapshot: dict,
    filtered: pd.DataFrame,
    valuation: pd.DataFrame,
    latest_date,
    min_amount: int,
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
        snapshot, filtered, valuation, latest_date, min_amount, keyword
    )

    with st.chat_message("assistant"):
        with st.spinner("分析中…"):
            answer = answer_market_question(prompt, context)
        st.markdown(answer)

    st.session_state[CHAT_SESSION_KEY].append({"role": "assistant", "content": answer})


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    display_df = remove_duplicate_columns(df.copy())
    if "date" in display_df.columns:
        display_df["date"] = pd.to_datetime(display_df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    if "return_pct" in display_df.columns:
        display_df["return_pct"] = pd.to_numeric(display_df["return_pct"], errors="coerce")
        display_df["return_pct"] = display_df["return_pct"].fillna(0)

    ordered_cols = [
        "signal_score",
        "volume_spike_signal",
        "breakout_signal",
        "momentum_signal",
        "relative_strength_signal",
        "industry_name",
        "industry",
        "stock_count", "up_count", "down_count", "up_ratio",
        "avg_return_pct", "median_return_pct", "total_turnover",
        "volume_spike_count", "breakout_count", "sub_sector",
        "date", "stock_id", "stock_name", "close", "return_pct",
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
    else:
        text = f"{float(numeric):.2f}%"
    return f'<span style="color:{color}; font-weight:600;">{text}</span>'


def render_watchlist_cards(watchlist: pd.DataFrame, top_n: int = 10) -> None:
    if watchlist is None or watchlist.empty:
        return

    top = remove_duplicate_columns(watchlist.head(top_n))
    st.subheader(f"Top {min(top_n, len(top))} Watchlist")

    for row_start in range(0, len(top), 5):
        chunk = top.iloc[row_start:row_start + 5]
        cols = st.columns(len(chunk))
        for col, (_, row) in zip(cols, chunk.iterrows()):
            with col:
                with st.container(border=True):
                    stock_id = row.get("stock_id", "")
                    stock_name = row.get("stock_name", "")
                    st.markdown(f"**{stock_id}** {stock_name}")
                    signal_score = row.get("signal_score", "")
                    st.write(f"Signal score: {signal_score}")
                    st.markdown(
                        f"Return: {_format_return_label(row.get('return_pct'))}",
                        unsafe_allow_html=True,
                    )
                    amount = pd.to_numeric(row.get("amount"), errors="coerce")
                    amount_text = f"{amount:,.0f}" if pd.notna(amount) else "N/A"
                    st.write(f"Turnover: {amount_text}")
                    reason = row.get("signal_reason", "")
                    if pd.notna(reason) and str(reason).strip():
                        st.caption(str(reason))


def render_visual_overview(
    filtered: pd.DataFrame,
    latest: pd.DataFrame,
    market_return: float,
    wl_min_turnover: int,
    wl_min_signal_score: int,
    wl_industry: str,
    wl_sub_sector: str,
) -> None:
    st.caption("Visual summary of market breadth, sector turnover, and top watchlist picks.")

    st.subheader("Market Breadth")
    breadth = get_market_breadth(latest)
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Total Stocks", f"{breadth['total_stocks']:,}")
    b2.metric("Up / Down / Flat", f"{breadth['up_count']:,} / {breadth['down_count']:,} / {breadth['flat_count']:,}")
    b3.metric("Up Ratio", f"{breadth['up_ratio'] * 100:.1f}%")
    b4.metric("Avg Return", f"{breadth['average_return']:.2f}%")
    b5.metric("Median Return", f"{breadth['median_return']:.2f}%")

    st.subheader("Market Heatmap")
    industry_trend = remove_duplicate_columns(get_industry_trend(filtered))
    st.plotly_chart(
        render_market_heatmap(industry_trend),
        use_container_width=True,
    )

    st.subheader("Sub-sector Heatmap")
    subsector_trend = remove_duplicate_columns(get_subsector_trend(filtered))
    st.plotly_chart(
        render_subsector_heatmap(subsector_trend),
        use_container_width=True,
    )

    universe = apply_sector_mapping(enrich_industry_columns(latest))
    if "signal_score" not in universe.columns:
        universe = score_signals(universe, market_return)

    watchlist = build_watchlist(
        universe,
        max_rows=50,
        min_amount=wl_min_turnover,
        min_signal_score=wl_min_signal_score,
        industry=wl_industry,
        sub_sector=wl_sub_sector,
    )
    if not watchlist.empty:
        render_watchlist_cards(watchlist, top_n=10)
    else:
        st.info("No watchlist stocks available for card view with current filters.")


def apply_signal_scanner_filters(
    df: pd.DataFrame,
    min_turnover: int,
    industry: str,
    sub_sector: str,
) -> pd.DataFrame:
    filtered = df.copy()
    if min_turnover > 0 and "amount" in filtered.columns:
        filtered = filtered[filtered["amount"] >= min_turnover]
    if industry != "All" and "industry_name" in filtered.columns:
        filtered = filtered[filtered["industry_name"] == industry]
    if sub_sector != "All" and "sub_sector" in filtered.columns:
        filtered = filtered[filtered["sub_sector"].astype(str) == sub_sector]
    return filtered


def render_signal_scanner(latest: pd.DataFrame, market_return: float) -> None:
    st.caption(
        "Scan latest-market signals. Sub-sector filter uses sector_mapping.csv labels."
    )

    universe = enrich_industry_columns(latest)

    col1, col2, col3 = st.columns(3)
    with col1:
        scanner_min_turnover = st.number_input(
            "Minimum turnover",
            min_value=0,
            value=0,
            step=1_000_000,
            key="scanner_min_turnover",
        )
    with col2:
        industry_options = ["All"] + sorted(
            universe["industry_name"].dropna().unique().tolist()
        )
        selected_industry = st.selectbox(
            "Industry",
            industry_options,
            key="scanner_industry",
        )
    with col3:
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
        universe, scanner_min_turnover, selected_industry, selected_sub_sector
    )

    if scanner_df.empty:
        st.info("No stocks match the current Signal Scanner filters.")
        return

    show_table("Volume Spike Signal", get_volume_spike_signal(scanner_df).head(100))
    show_table("Breakout Signal", get_breakout_signal(scanner_df).head(100))
    show_table("Momentum Signal", get_momentum_signal(scanner_df).head(100))
    show_table(
        "Relative Strength Signal",
        get_relative_strength_signal(scanner_df, market_return).head(100),
    )

    ranked = score_signals(scanner_df, market_return)
    ranked = ranked[ranked["signal_score"] > 0].head(100)
    show_table("Combined Signal Ranking", ranked, height=600)


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


def render_watchlist(
    latest: pd.DataFrame,
    latest_date,
    market_return: float,
    wl_min_turnover: int,
    wl_min_signal_score: int,
    wl_industry: str,
    wl_sub_sector: str,
) -> None:
    st.caption(
        "Rule-based watchlist from latest signals and liquidity filters. "
        "Sub-sector labels come from sector_mapping.csv."
    )

    universe = apply_sector_mapping(enrich_industry_columns(latest))
    if "signal_score" not in universe.columns:
        universe = score_signals(universe, market_return)

    watchlist = build_watchlist(
        universe,
        max_rows=50,
        min_amount=wl_min_turnover,
        min_signal_score=wl_min_signal_score,
        industry=wl_industry,
        sub_sector=wl_sub_sector,
    )

    if watchlist.empty:
        st.info(
            "No stocks match the current watchlist filters. "
            "Try lowering turnover or signal score threshold."
        )
        debug = watchlist_debug_summary(
            universe,
            wl_min_turnover,
            wl_min_signal_score,
            wl_industry,
            wl_sub_sector,
        )
        st.subheader("Watchlist Debug Summary")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Latest rows", f"{debug['latest_rows']:,}")
        d2.metric("Rows amount >= threshold", f"{debug['rows_with_amount']:,}")
        d3.metric("Rows signal >= threshold", f"{debug['rows_with_signal_score']:,}")
        d4.metric("Max signal score", f"{debug['max_signal_score']:,}")
        if not debug["top_amount_stocks"].empty:
            st.caption("Top 10 stocks by turnover")
            st.dataframe(
                remove_duplicate_columns(debug["top_amount_stocks"]),
                use_container_width=True,
                hide_index=True,
            )
        return

    show_table("Today's Watchlist", watchlist, height=600, hide_index=True)

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

    st.subheader("Market Breadth")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Total Stocks", f"{breadth['total_stocks']:,}")
    b2.metric("Up / Down / Flat", f"{breadth['up_count']:,} / {breadth['down_count']:,} / {breadth['flat_count']:,}")
    b3.metric("Up Ratio", f"{breadth['up_ratio'] * 100:.1f}%")
    b4.metric("Advance/Decline", f"{breadth['advance_decline_ratio']:.2f}")

    b5, b6 = st.columns(2)
    b5.metric("Average Return", f"{breadth['average_return']:.2f}%")
    b6.metric("Median Return", f"{breadth['median_return']:.2f}%")

    st.subheader("Large Cap vs Small Cap")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Large Cap Avg Return", f"{cap_comparison['large_cap_avg_return']:.2f}%")
    c2.metric("Small Cap Avg Return", f"{cap_comparison['small_cap_avg_return']:.2f}%")
    c3.metric("Large Cap Up Ratio", f"{cap_comparison['large_cap_up_ratio'] * 100:.1f}%")
    c4.metric("Small Cap Up Ratio", f"{cap_comparison['small_cap_up_ratio'] * 100:.1f}%")
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

    min_amount = st.sidebar.number_input(
        "Minimum turnover",
        min_value=0,
        value=0,
        step=1000000
    )

    keyword = st.sidebar.text_input("Search stock code or name")

    st.sidebar.header("Watchlist")
    wl_min_turnover = st.sidebar.number_input(
        "Watchlist minimum turnover",
        min_value=0,
        value=50_000_000,
        step=1_000_000,
        key="wl_min_turnover",
    )
    wl_min_signal_score = st.sidebar.number_input(
        "Watchlist minimum signal score",
        min_value=0,
        value=1,
        step=1,
        key="wl_min_signal_score",
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

    filtered = latest.copy()
    if min_amount > 0:
        filtered = filtered[filtered["amount"] >= min_amount]

    if keyword.strip():
        kw = keyword.strip()
        filtered = filtered[
            filtered["stock_id"].astype(str).str.contains(kw, case=False, na=False) |
            filtered["stock_name"].astype(str).str.contains(kw, case=False, na=False)
        ]

    valid_returns = latest[latest["return_pct"].notna()].copy()

    if valid_returns.empty:
        up_down_display = "N/A"
        median_return_display = "N/A"
        st.warning(
            "Return data unavailable because historical price data is insufficient."
        )
    else:
        up_count = int((valid_returns["return_pct"] > 0).sum())
        down_count = int((valid_returns["return_pct"] < 0).sum())
        median_return = valid_returns["return_pct"].median()
        up_down_display = f"{up_count:,} / {down_count:,}"
        median_return_display = f"{median_return:.2f}%"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Date", latest_date.strftime("%Y-%m-%d"))
    c2.metric("Stocks", f"{snapshot['stock_count']:,}")
    c3.metric("Up / Down", up_down_display)
    c4.metric("Total Turnover", f"{snapshot['total_turnover']:,.0f}")
    c5.metric("Median Return", median_return_display)

    with st.expander("Market Overview debug"):
        min_date = snapshot.get("min_date")
        max_date = snapshot.get("max_date")
        return_pct = pd.to_numeric(latest["return_pct"], errors="coerce")
        st.write(f"Latest rows count: {len(latest):,}")
        st.write(f"Valid return_pct rows count: {len(valid_returns):,}")
        st.write(f"return_pct == 0 count: {int((return_pct == 0).sum()):,}")
        st.write(f"return_pct is NaN count: {int(return_pct.isna().sum()):,}")
        st.write(f"Latest date: {latest_date.strftime('%Y-%m-%d')}")
        st.write(f"Available historical dates count: {snapshot.get('historical_date_count', 0):,}")
        st.write(
            f"Min date: {min_date.strftime('%Y-%m-%d') if pd.notna(min_date) else 'N/A'}"
        )
        st.write(
            f"Max date: {max_date.strftime('%Y-%m-%d') if pd.notna(max_date) else 'N/A'}"
        )
        debug_cols = [c for c in ["stock_id", "close", "prev_close", "return_pct"] if c in latest.columns]
        if debug_cols:
            st.caption("First 20 rows: stock_id, close, prev_close, return_pct")
            st.dataframe(
                remove_duplicate_columns(latest[debug_cols].head(20)),
                use_container_width=True,
                hide_index=True,
            )

    if not valid_returns.empty:
        med = valid_returns["return_pct"].median()
        market_return = float(med) if pd.notna(med) else 0.0
    else:
        market_return = 0.0

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13 = st.tabs([
        "Market Scan",
        "Visual Overview",
        "Volume Spike",
        "Breakout",
        "Top Turnover",
        "Valuation",
        "Industry Trend",
        "Sub-sector Trend",
        "Market Regime",
        "Signal Scanner",
        "Watchlist",
        "Raw Latest Data",
        "AI Analyst Chat",
    ])

    with tab1:
        show_table("Top Gainers", get_top_gainers(filtered))
        show_table("Top Losers", get_top_losers(filtered))

    with tab2:
        render_visual_overview(
            filtered,
            latest,
            market_return,
            wl_min_turnover,
            wl_min_signal_score,
            wl_industry,
            wl_sub_sector,
        )

    with tab3:
        show_table(
            "Volume Spike: Volume >= 2x 20D Average",
            get_volume_spike(filtered),
        )

    with tab4:
        show_table(
            "Breakout: Close > Previous 20D High and Volume >= 1.5x",
            get_breakout(filtered),
        )

    with tab5:
        show_table("Top Turnover", get_top_turnover(filtered))

    with tab6:
        if valuation.empty:
            st.info("No valuation data available.")
        else:
            show_table("Cheap Value: PE <= 15 and PB <= 1.5", get_cheap_value(valuation))
            show_table("High Dividend: Dividend Yield >= 4%", get_high_dividend(valuation))

    with tab7:
        industry_trend = get_industry_trend(filtered)
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

    with tab8:
        render_subsector_trend(filtered)

    with tab9:
        render_market_regime(latest)

    with tab10:
        render_signal_scanner(latest, market_return)

    with tab11:
        render_watchlist(
            latest,
            latest_date,
            market_return,
            wl_min_turnover,
            wl_min_signal_score,
            wl_industry,
            wl_sub_sector,
        )

    with tab12:
        show_table(
            "Latest Raw Price Data",
            filtered.sort_values("amount", ascending=False),
            height=600,
        )

    with tab13:
        render_ai_analyst_chat(
            snapshot, filtered, valuation, latest_date, min_amount, keyword
        )


if __name__ == "__main__":
    main()
