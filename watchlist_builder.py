import numpy as np
import pandas as pd

from data_service import apply_sector_mapping
from signal_engine import (
    breakout_mask,
    momentum_mask,
    relative_strength_mask,
    score_signals,
    volume_spike_reason_mask,
)

MIN_WATCHLIST_AMOUNT = 50_000_000
MIN_WATCHLIST_SIGNAL_SCORE = 1

OUTPUT_COLUMNS = [
    "stock_id",
    "stock_name",
    "industry",
    "sub_sector",
    "close",
    "return_pct",
    "amount",
    "volume_ratio_20d",
    "signal_score",
    "signal_reason",
    "observation_focus",
]


def _col_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _market_median_return(df: pd.DataFrame) -> float:
    returns = _col_numeric(df, "return_pct")
    if returns.notna().any():
        return float(returns.median())
    return 0.0


def _fill_missing_indicators(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    numeric_cols = [
        "close", "return_pct", "amount", "volume_ratio_20d",
        "ma5", "ma20", "high_20d_prev",
    ]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    if "volume_ratio_20d" not in result.columns:
        result["volume_ratio_20d"] = np.nan
    if "ma5" not in result.columns:
        result["ma5"] = np.nan
    if "ma20" not in result.columns:
        result["ma20"] = np.nan
    if "high_20d_prev" not in result.columns:
        result["high_20d_prev"] = np.nan

    return result


def _build_signal_reason_row(
    volume_spike: bool,
    breakout: bool,
    momentum: bool,
    relative_strength: bool,
    high_turnover: bool,
) -> str:
    reasons: list[str] = []
    if high_turnover:
        reasons.append("高成交金額")
    if volume_spike:
        reasons.append("量能放大")
    if breakout:
        reasons.append("突破前高")
    if momentum:
        reasons.append("短線動能")
    if relative_strength:
        reasons.append("相對強勢")
    return "、".join(reasons)


def _build_observation_focus(
    volume_spike: bool,
    breakout: bool,
    momentum: bool,
    high_turnover: bool,
) -> str:
    focuses: list[str] = []
    if breakout:
        focuses.append("觀察是否站穩突破區與量能是否延續")
    if volume_spike:
        focuses.append("觀察放量後是否續強或轉為爆量反轉")
    if momentum:
        focuses.append("觀察短期均線是否維持多頭排列")
    if high_turnover:
        focuses.append("觀察資金是否持續集中")
    if focuses:
        return "；".join(focuses)
    return "僅列為資料觀察"


def _annotate_signals(work: pd.DataFrame, market_return: float) -> pd.DataFrame:
    volume_spike = volume_spike_reason_mask(work)
    breakout = breakout_mask(work)
    momentum = momentum_mask(work)
    relative_strength = relative_strength_mask(work, market_return)

    if "high_turnover_signal" in work.columns:
        high_turnover = work["high_turnover_signal"].fillna(False).astype(bool)
    else:
        high_turnover = pd.Series(False, index=work.index)

    work["signal_reason"] = [
        _build_signal_reason_row(vs, bo, mo, rs, ht)
        for vs, bo, mo, rs, ht in zip(
            volume_spike, breakout, momentum, relative_strength, high_turnover
        )
    ]
    work["observation_focus"] = [
        _build_observation_focus(vs, bo, mo, ht)
        for vs, bo, mo, ht in zip(volume_spike, breakout, momentum, high_turnover)
    ]
    return work


def _ensure_sub_sector(df: pd.DataFrame) -> pd.DataFrame:
    return apply_sector_mapping(df)


def _valid_identity_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)

    if "stock_id" not in df.columns or "stock_name" not in df.columns:
        return pd.Series(False, index=df.index)

    stock_id = df["stock_id"].astype(str).str.strip()
    stock_name = df["stock_name"].astype(str).str.strip()
    invalid_names = {"", "nan", "None", "NA", "<NA>"}

    return (
        df["stock_id"].notna()
        & df["stock_name"].notna()
        & ~stock_id.isin(invalid_names)
        & ~stock_name.isin(invalid_names)
    )


def _apply_industry_filters(
    df: pd.DataFrame, industry: str, sub_sector: str
) -> pd.DataFrame:
    work = df
    if industry != "All":
        if "industry_name" in work.columns:
            work = work[work["industry_name"] == industry]
        elif "industry" in work.columns:
            work = work[work["industry"].astype(str) == industry]

    if sub_sector != "All" and "sub_sector" in work.columns:
        work = work[work["sub_sector"].astype(str) == sub_sector]
    return work


def _sort_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    sort_cols = ["signal_score"]
    for col in ("amount", "return_pct"):
        if col in df.columns:
            sort_cols.append(col)
    return df.sort_values(sort_cols, ascending=[False] * len(sort_cols))


def _fallback_turnover_watchlist(
    work: pd.DataFrame, min_amount: float, max_rows: int
) -> pd.DataFrame:
    amount = _col_numeric(work, "amount")
    fallback = work[_valid_identity_mask(work) & (amount >= min_amount)].copy()
    if fallback.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    fallback = _sort_watchlist(fallback).head(max_rows)
    fallback["signal_reason"] = "高成交金額"
    fallback["observation_focus"] = "觀察資金是否持續集中"
    if "signal_score" not in fallback.columns:
        fallback["signal_score"] = 0
    return fallback


def watchlist_debug_summary(
    df: pd.DataFrame,
    min_amount: float,
    min_signal_score: int,
    industry: str = "All",
    sub_sector: str = "All",
) -> dict:
    if df.empty:
        return {
            "latest_rows": 0,
            "rows_with_amount": 0,
            "rows_with_signal_score": 0,
            "max_signal_score": 0,
            "top_amount_stocks": pd.DataFrame(),
        }

    work = _apply_industry_filters(_fill_missing_indicators(df.copy()), industry, sub_sector)
    if "signal_score" not in work.columns:
        work = score_signals(work, _market_median_return(work))

    amount = _col_numeric(work, "amount")
    signal_score = _col_numeric(work, "signal_score").fillna(0)

    top_amount = work.copy()
    if "amount" in top_amount.columns:
        top_amount = top_amount.sort_values("amount", ascending=False).head(10)

    display_cols = [
        c for c in ["stock_id", "stock_name", "amount", "signal_score", "return_pct"]
        if c in top_amount.columns
    ]

    return {
        "latest_rows": len(work),
        "rows_with_amount": int((amount >= min_amount).sum()),
        "rows_with_signal_score": int((signal_score >= min_signal_score).sum()),
        "max_signal_score": int(signal_score.max()) if len(work) else 0,
        "top_amount_stocks": top_amount[display_cols] if display_cols else top_amount,
    }


def build_watchlist(
    df: pd.DataFrame,
    max_rows: int = 50,
    min_amount: float = MIN_WATCHLIST_AMOUNT,
    min_signal_score: int = MIN_WATCHLIST_SIGNAL_SCORE,
    industry: str = "All",
    sub_sector: str = "All",
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    work = _ensure_sub_sector(_fill_missing_indicators(df.copy()))
    work = _apply_industry_filters(work, industry, sub_sector)
    if work.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    market_return = _market_median_return(work)
    work = score_signals(work, market_return)
    work = _annotate_signals(work, market_return)

    amount = _col_numeric(work, "amount")
    signal_score = _col_numeric(work, "signal_score").fillna(0)

    filtered = work[
        _valid_identity_mask(work)
        & (amount >= min_amount)
        & (signal_score >= min_signal_score)
    ].copy()

    if filtered.empty:
        if int(signal_score.max()) == 0:
            filtered = _fallback_turnover_watchlist(work, min_amount, max_rows)
    else:
        filtered = _sort_watchlist(filtered).head(max_rows)
        empty_reason = filtered["signal_reason"].astype(str).str.strip() == ""
        filtered.loc[empty_reason, "signal_reason"] = "高成交金額"

    if filtered.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    for col in OUTPUT_COLUMNS:
        if col not in filtered.columns:
            filtered[col] = pd.NA

    return filtered[OUTPUT_COLUMNS].reset_index(drop=True)
