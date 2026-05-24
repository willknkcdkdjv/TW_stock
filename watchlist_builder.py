import numpy as np
import pandas as pd

from data_service import apply_sector_mapping, get_subsector_trend
from signal_engine import calculate_hotness_score, score_signals

MIN_WATCHLIST_AMOUNT = 50_000_000
MIN_WATCHLIST_TECHNICAL_SCORE = 0

TURNOVER_PERCENTILE_HOT = 90
TECHNICAL_SCORE_HIGH = 2

OUTPUT_COLUMNS = [
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
        "close",
        "return_pct",
        "amount",
        "turnover_ratio_20d",
        "turnover_percentile_60d",
        "hotness_score",
        "technical_score",
    ]
    for col in numeric_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        else:
            result[col] = np.nan

    return result


def _ensure_industry_column(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "industry" not in result.columns and "industry_name" in result.columns:
        result["industry"] = result["industry_name"]
    return result


def _ensure_watchlist_scores(df: pd.DataFrame, market_return: float) -> pd.DataFrame:
    """Ensure technical_score, hotness_score, and signal_reason are present."""
    if df.empty:
        return df.copy()

    subsector_trend = get_subsector_trend(df)
    result = df.copy()

    if "technical_score" not in result.columns:
        if "signal_score" in result.columns and "signal_reason" in result.columns:
            result["technical_score"] = result["signal_score"]
        else:
            result = score_signals(
                result,
                market_return=market_return,
                subsector_trend_df=subsector_trend,
            )

    if "hotness_score" not in result.columns:
        result = calculate_hotness_score(
            result,
            market_return=market_return,
            subsector_trend_df=subsector_trend,
        )

    if "signal_reason" not in result.columns:
        result = score_signals(
            result,
            market_return=market_return,
            subsector_trend_df=subsector_trend,
        )
        if "technical_score" not in result.columns and "signal_score" in result.columns:
            result["technical_score"] = result["signal_score"]

    return result


def _build_observation_focus(
    hotness_reason: str,
    turnover_percentile_60d: float,
    technical_score: float,
) -> str:
    reason = str(hotness_reason or "")
    percentile = pd.to_numeric(turnover_percentile_60d, errors="coerce")

    if pd.notna(percentile) and percentile >= TURNOVER_PERCENTILE_HOT:
        return "觀察市場關注是否延續，避免單日爆量反轉"
    if "60日高分位" in reason:
        return "觀察市場關注是否延續，避免單日爆量反轉"
    if "熱門族群" in reason:
        return "觀察熱門族群是否持續擴散"

    tech = pd.to_numeric(technical_score, errors="coerce")
    if pd.notna(tech) and tech >= TECHNICAL_SCORE_HIGH:
        return "觀察技術型態是否延續"

    return "僅列為資料觀察"


def _annotate_observation_focus(work: pd.DataFrame) -> pd.DataFrame:
    result = work.copy()
    hotness_reason = result.get("hotness_reason", pd.Series("", index=result.index))
    turnover_percentile = _col_numeric(result, "turnover_percentile_60d")
    technical_score = _col_numeric(result, "technical_score")

    result["observation_focus"] = [
        _build_observation_focus(hr, tp, ts)
        for hr, tp, ts in zip(hotness_reason, turnover_percentile, technical_score)
    ]
    return result


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
    sort_cols = [
        col
        for col in (
            "hotness_score",
            "technical_score",
            "turnover_percentile_60d",
            "amount",
        )
        if col in df.columns
    ]
    if not sort_cols:
        return df
    return df.sort_values(sort_cols, ascending=[False] * len(sort_cols))


def watchlist_debug_summary(
    df: pd.DataFrame,
    min_amount: float,
    min_hotness_score: float = 0,
    min_technical_score: int = MIN_WATCHLIST_TECHNICAL_SCORE,
    industry: str = "All",
    sub_sector: str = "All",
    min_signal_score: int | None = None,
) -> dict:
    if min_signal_score is not None:
        min_technical_score = min_signal_score

    if df.empty:
        return {
            "latest_rows": 0,
            "rows_with_amount": 0,
            "rows_with_hotness_score": 0,
            "rows_with_technical_score": 0,
            "max_hotness_score": 0.0,
            "max_technical_score": 0,
            "top_activity_stocks": pd.DataFrame(),
        }

    work = _apply_industry_filters(_fill_missing_indicators(df.copy()), industry, sub_sector)
    if work.empty:
        return {
            "latest_rows": 0,
            "rows_with_amount": 0,
            "rows_with_hotness_score": 0,
            "rows_with_technical_score": 0,
            "max_hotness_score": 0.0,
            "max_technical_score": 0,
            "top_activity_stocks": pd.DataFrame(),
        }

    market_return = _market_median_return(work)
    work = _ensure_watchlist_scores(work, market_return)

    amount = _col_numeric(work, "amount")
    hotness_score = _col_numeric(work, "hotness_score").fillna(0)
    technical_score = _col_numeric(work, "technical_score").fillna(0)

    top_activity = work.copy()
    activity_cols = [
        "hotness_score",
        "technical_score",
        "turnover_percentile_60d",
        "turnover_ratio_20d",
    ]
    present = [c for c in activity_cols if c in top_activity.columns]
    if present:
        top_activity = top_activity.sort_values(
            present, ascending=[False] * len(present)
        ).head(10)
    elif "amount" in top_activity.columns:
        top_activity = top_activity.sort_values("amount", ascending=False).head(10)

    display_cols = [
        c
        for c in [
            "stock_id",
            "stock_name",
            "hotness_score",
            "technical_score",
            "turnover_percentile_60d",
            "turnover_ratio_20d",
            "amount",
            "return_pct",
        ]
        if c in top_activity.columns
    ]

    summary = {
        "latest_rows": len(work),
        "rows_with_amount": int((amount >= min_amount).sum()),
        "rows_with_hotness_score": int((hotness_score >= min_hotness_score).sum()),
        "rows_with_technical_score": int((technical_score >= min_technical_score).sum()),
        "max_hotness_score": float(hotness_score.max()) if len(work) else 0.0,
        "max_technical_score": int(technical_score.max()) if len(work) else 0,
        "top_activity_stocks": top_activity[display_cols] if display_cols else top_activity,
        # Backward compatibility for web_app debug panel
        "rows_with_signal_score": int((technical_score >= min_technical_score).sum()),
        "max_signal_score": int(technical_score.max()) if len(work) else 0,
        "top_amount_stocks": top_activity[display_cols] if display_cols else top_activity,
    }
    return summary


def build_watchlist(
    df: pd.DataFrame,
    max_rows: int = 50,
    min_amount: float = MIN_WATCHLIST_AMOUNT,
    min_hotness_score: float = 0,
    min_technical_score: int | None = None,
    min_signal_score: int | None = None,
    industry: str = "All",
    sub_sector: str = "All",
) -> pd.DataFrame:
    if min_technical_score is None:
        min_technical_score = (
            min_signal_score
            if min_signal_score is not None
            else MIN_WATCHLIST_TECHNICAL_SCORE
        )

    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    work = _ensure_sub_sector(_fill_missing_indicators(df.copy()))
    work = _apply_industry_filters(work, industry, sub_sector)
    if work.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    market_return = _market_median_return(work)
    work = _ensure_watchlist_scores(work, market_return)
    work = _annotate_observation_focus(work)
    work = _ensure_industry_column(work)

    amount = _col_numeric(work, "amount")
    hotness_score = _col_numeric(work, "hotness_score").fillna(0)
    technical_score = _col_numeric(work, "technical_score").fillna(0)

    filtered = work[
        _valid_identity_mask(work)
        & (amount >= min_amount)
        & (hotness_score >= min_hotness_score)
        & (technical_score >= min_technical_score)
    ].copy()

    if filtered.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    filtered = _sort_watchlist(filtered).head(max_rows)

    for col in OUTPUT_COLUMNS:
        if col not in filtered.columns:
            filtered[col] = pd.NA

    return filtered[OUTPUT_COLUMNS].reset_index(drop=True)
