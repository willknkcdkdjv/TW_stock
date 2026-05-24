import numpy as np
import pandas as pd

VOLUME_SPIKE_MIN_AMOUNT = 100_000_000
DEFAULT_MIN_LIQUIDITY = VOLUME_SPIKE_MIN_AMOUNT
LIQUIDITY_TOP_20_PERCENTILE = 0.8

TURNOVER_PERCENTILE_HIGH = 90
TURNOVER_PERCENTILE_EXTREME = 95
TURNOVER_RATIO_SPIKE = 2
TURNOVER_RATIO_BREAKOUT = 1.5
NEAR_BREAKOUT_MIN_DISTANCE_PCT = -3.0

UNCLASSIFIED_SUB_SECTOR = "未分類"

HOTNESS_MAX_SCORE = 100
HOTNESS_PCT_60D_MAX = 30
HOTNESS_RATIO_20D_MAX = 20
HOTNESS_RELATIVE_STRENGTH_MAX = 20
HOTNESS_SECTOR_HEAT_MAX = 15
HOTNESS_PARTICIPATION_MAX = 10
HOTNESS_TECH_CONFIRM_MAX = 5


def _compute_technical_score_series(
    confirmed_breakout: pd.Series,
    price_breakout_only: pd.Series,
    momentum: pd.Series,
    relative_strength: pd.Series,
    extreme_turnover_percentile: pd.Series,
    high_percentile_only: pd.Series,
    turnover_ratio_spike: pd.Series,
) -> pd.Series:
    """Technical setup score. Raw amount is not used."""
    return (
        confirmed_breakout.astype(int) * 3
        + price_breakout_only.astype(int) * 1
        + relative_strength.astype(int) * 2
        + extreme_turnover_percentile.astype(int) * 2
        + high_percentile_only.astype(int)
        + turnover_ratio_spike.astype(int) * 2
        + momentum.astype(int)
    )


def _attach_technical_signals_and_scores(
    df: pd.DataFrame, market_return: float
) -> pd.DataFrame:
    """Attach technical signal flags, signal_score, technical_score, and signal_reason."""
    scored = df.copy()

    volume_spike = volume_spike_reason_mask(scored)
    price_breakout = price_breakout_mask(scored)
    confirmed_breakout = confirmed_breakout_mask(scored)
    price_breakout_only = price_breakout & ~confirmed_breakout
    momentum = momentum_mask(scored)
    relative_strength = relative_strength_mask(scored, market_return)
    _, high_turnover = _liquidity_scores(scored)

    high_turnover_percentile = high_turnover_percentile_mask(scored)
    extreme_turnover_percentile = extreme_turnover_percentile_mask(scored)
    turnover_ratio_spike = turnover_ratio_spike_mask(scored)
    liquidity_pass = liquidity_pass_mask(scored)
    high_percentile_only = high_turnover_percentile & ~extreme_turnover_percentile

    scored["volume_spike_signal"] = volume_spike.fillna(False)
    scored["price_breakout_signal"] = price_breakout.fillna(False)
    scored["confirmed_breakout_signal"] = confirmed_breakout.fillna(False)
    scored["breakout_signal"] = confirmed_breakout.fillna(False)
    scored["momentum_signal"] = momentum.fillna(False)
    scored["relative_strength_signal"] = relative_strength.fillna(False)
    scored["liquidity_score"] = 0
    scored["high_turnover_signal"] = high_turnover.fillna(False)
    scored["high_turnover_percentile_signal"] = high_turnover_percentile.fillna(False)
    scored["extreme_turnover_percentile_signal"] = extreme_turnover_percentile.fillna(
        False
    )
    scored["turnover_ratio_spike_signal"] = turnover_ratio_spike.fillna(False)
    scored["liquidity_pass"] = liquidity_pass.fillna(False)

    technical_score = _compute_technical_score_series(
        confirmed_breakout,
        price_breakout_only,
        momentum,
        relative_strength,
        extreme_turnover_percentile,
        high_percentile_only,
        turnover_ratio_spike,
    )
    scored["signal_score"] = technical_score
    scored["technical_score"] = technical_score
    scored["signal_reason"] = build_signal_reasons(scored)

    return scored


def _col_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _liquidity_scores(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (liquidity_score, high_turnover_signal).

    Raw amount is display-only; liquidity_score is always 0 (not used in signal_score).
    """
    if df.empty:
        return pd.Series(dtype=int), pd.Series(dtype=bool)

    amount = _col_numeric(df, "amount")
    liquidity_score = pd.Series(0, index=df.index, dtype=int)
    high_turnover = pd.Series(False, index=df.index, dtype=bool)

    if not amount.notna().any():
        return liquidity_score, high_turnover

    p80 = amount.quantile(LIQUIDITY_TOP_20_PERCENTILE)
    valid = amount.notna()
    high_turnover = valid & (amount >= p80)

    return liquidity_score, high_turnover


def liquidity_pass_mask(
    df: pd.DataFrame, min_amount: float = DEFAULT_MIN_LIQUIDITY
) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    amount = _col_numeric(df, "amount")
    return amount.notna() & (amount >= min_amount)


def high_turnover_percentile_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    percentile = _col_numeric(df, "turnover_percentile_60d")
    return percentile.notna() & (percentile >= TURNOVER_PERCENTILE_HIGH)


def extreme_turnover_percentile_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    percentile = _col_numeric(df, "turnover_percentile_60d")
    return percentile.notna() & (percentile >= TURNOVER_PERCENTILE_EXTREME)


def turnover_ratio_spike_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    ratio = _col_numeric(df, "turnover_ratio_20d")
    return ratio.notna() & (ratio >= TURNOVER_RATIO_SPIKE)


def volume_spike_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    volume_ratio = _col_numeric(df, "volume_ratio_20d")
    amount = _col_numeric(df, "amount")
    valid_ratio = volume_ratio.notna()
    return valid_ratio & (volume_ratio >= 2) & (amount >= VOLUME_SPIKE_MIN_AMOUNT)


def volume_spike_reason_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    volume_ratio = _col_numeric(df, "volume_ratio_20d")
    return volume_ratio.notna() & (volume_ratio >= 2)


def compute_breakout_distance_pct(df: pd.DataFrame) -> pd.Series:
    close = _col_numeric(df, "close")
    high_20d_prev = _col_numeric(df, "high_20d_prev")
    valid = close.notna() & high_20d_prev.notna() & (high_20d_prev != 0)
    distance = pd.Series(np.nan, index=df.index, dtype=float)
    distance.loc[valid] = (close.loc[valid] / high_20d_prev.loc[valid] - 1.0) * 100.0
    return distance


def attach_breakout_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    result["breakout_distance_pct"] = compute_breakout_distance_pct(result)
    return result


def price_breakout_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    close = _col_numeric(df, "close")
    high_20d_prev = _col_numeric(df, "high_20d_prev")
    valid = close.notna() & high_20d_prev.notna()
    return valid & (close > high_20d_prev)


def near_breakout_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    distance = compute_breakout_distance_pct(df)
    valid = distance.notna()
    return valid & (distance >= NEAR_BREAKOUT_MIN_DISTANCE_PCT) & (distance <= 0)


def confirmed_breakout_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    price_breakout = price_breakout_mask(df)
    turnover_ratio = _col_numeric(df, "turnover_ratio_20d")
    return price_breakout & turnover_ratio.notna() & (
        turnover_ratio >= TURNOVER_RATIO_BREAKOUT
    )


def breakout_mask(df: pd.DataFrame) -> pd.Series:
    """Backward-compatible alias for confirmed breakout."""
    return confirmed_breakout_mask(df)


def momentum_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    ma5 = _col_numeric(df, "ma5")
    ma20 = _col_numeric(df, "ma20")
    close = _col_numeric(df, "close")
    return_pct = _col_numeric(df, "return_pct")
    valid = ma5.notna() & ma20.notna() & close.notna() & return_pct.notna()
    return valid & (ma5 > ma20) & (close > ma5) & (return_pct > 0)


def relative_strength_mask(df: pd.DataFrame, market_return: float) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    return_pct = _col_numeric(df, "return_pct")
    if not return_pct.notna().any():
        return pd.Series(False, index=df.index)
    return return_pct.notna() & (return_pct > market_return)


# Backward-compatible aliases
_momentum_mask = momentum_mask
_relative_strength_mask = relative_strength_mask


def _build_signal_reason_row(
    extreme_turnover_percentile: bool,
    high_turnover_percentile: bool,
    turnover_ratio_spike: bool,
    confirmed_breakout: bool,
    price_breakout_only: bool,
    momentum: bool,
    relative_strength: bool,
) -> str:
    reasons: list[str] = []
    if extreme_turnover_percentile:
        reasons.append("成交金額異常放大")
    elif high_turnover_percentile:
        reasons.append("成交金額高於近期常態")
    if turnover_ratio_spike:
        reasons.append("成交金額大於20日均值2倍")
    if confirmed_breakout:
        reasons.append("突破前高（量能確認）")
    elif price_breakout_only:
        reasons.append("突破前高")
    if momentum:
        reasons.append("短線動能")
    if relative_strength:
        reasons.append("相對強勢")
    return "、".join(reasons)


def build_signal_reasons(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)

    extreme = extreme_turnover_percentile_mask(df).fillna(False)
    high = high_turnover_percentile_mask(df).fillna(False)
    ratio_spike = turnover_ratio_spike_mask(df).fillna(False)
    price_breakout = price_breakout_mask(df).fillna(False)
    confirmed_breakout = confirmed_breakout_mask(df).fillna(False)
    price_breakout_only = price_breakout & ~confirmed_breakout
    momentum = momentum_mask(df).fillna(False)

    if "relative_strength_signal" in df.columns:
        relative_strength = df["relative_strength_signal"].fillna(False).astype(bool)
    else:
        relative_strength = pd.Series(False, index=df.index)

    return pd.Series(
        [
            _build_signal_reason_row(ext, hi, tr, conf, pbo, mo, rs)
            for ext, hi, tr, conf, pbo, mo, rs in zip(
                extreme,
                high,
                ratio_spike,
                confirmed_breakout,
                price_breakout_only,
                momentum,
                relative_strength,
            )
        ],
        index=df.index,
        dtype=str,
    )


def get_volume_spike_signal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    mask = volume_spike_mask(df)
    if not mask.any():
        return pd.DataFrame(columns=df.columns)

    result = df.loc[mask].copy()
    return result.sort_values(
        ["volume_ratio_20d", "amount"], ascending=[False, False]
    )


def get_price_breakout_signal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    work = attach_breakout_metrics(df)
    mask = price_breakout_mask(work)
    if not mask.any():
        return pd.DataFrame(columns=work.columns)

    result = work.loc[mask].copy()
    sort_cols = [
        c for c in ("breakout_distance_pct", "return_pct", "amount", "close")
        if c in result.columns
    ]
    if not sort_cols:
        return result
    return result.sort_values(sort_cols, ascending=[False] * len(sort_cols))


def get_confirmed_breakout_signal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    work = attach_breakout_metrics(df)
    mask = confirmed_breakout_mask(work)
    if not mask.any():
        return pd.DataFrame(columns=work.columns)

    result = work.loc[mask].copy()
    sort_cols = [
        c
        for c in (
            "breakout_distance_pct",
            "turnover_ratio_20d",
            "return_pct",
            "amount",
        )
        if c in result.columns
    ]
    if not sort_cols:
        return result
    return result.sort_values(sort_cols, ascending=[False] * len(sort_cols))


def get_near_breakout_signal(df: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    work = attach_breakout_metrics(df)
    mask = near_breakout_mask(work)
    if not mask.any():
        return pd.DataFrame(columns=work.columns)

    result = work.loc[mask].copy()
    sort_cols = [
        c
        for c in (
            "breakout_distance_pct",
            "hotness_score",
            "turnover_percentile_60d",
            "amount",
        )
        if c in result.columns
    ]
    if not sort_cols:
        return result
    return result.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(limit)


def get_breakout_signal(df: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible alias returning confirmed breakouts."""
    return get_confirmed_breakout_signal(df)


def get_momentum_signal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    mask = momentum_mask(df)
    if not mask.any():
        return pd.DataFrame(columns=df.columns)

    result = df.loc[mask].copy()
    return result.sort_values("return_pct", ascending=False)


def get_relative_strength_signal(
    df: pd.DataFrame, market_return: float
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    mask = relative_strength_mask(df, market_return)
    if not mask.any():
        return pd.DataFrame(columns=df.columns)

    result = df.loc[mask].copy()
    return result.sort_values("return_pct", ascending=False)


def _market_median_return(df: pd.DataFrame) -> float:
    returns = _col_numeric(df, "return_pct")
    if returns.notna().any():
        med = returns.median()
        return float(med) if pd.notna(med) else 0.0
    return 0.0


def _turnover_percentile_hotness_component(df: pd.DataFrame) -> pd.Series:
    percentile = _col_numeric(df, "turnover_percentile_60d")
    score = percentile / 100.0 * HOTNESS_PCT_60D_MAX
    return score.where(percentile.notna(), 0.0).fillna(0.0)


def _turnover_ratio_hotness_component(df: pd.DataFrame) -> pd.Series:
    ratio = _col_numeric(df, "turnover_ratio_20d")
    normalized = (ratio / 3.0).clip(upper=1.0)
    score = normalized * HOTNESS_RATIO_20D_MAX
    return score.where(ratio.notna(), 0.0).fillna(0.0)


def _relative_strength_hotness_component(
    df: pd.DataFrame, market_return: float
) -> pd.Series:
    return_pct = _col_numeric(df, "return_pct")
    scores = pd.Series(0.0, index=df.index, dtype=float)

    valid = return_pct.notna()
    if not valid.any():
        return scores

    relative_strength = return_pct - market_return
    ranked = relative_strength[valid].rank(pct=True, method="average")

    for idx, pct_rank in ranked.items():
        rs_val = relative_strength.loc[idx]
        if pct_rank >= 0.90:
            scores.loc[idx] = 20.0
        elif pct_rank >= 0.80:
            scores.loc[idx] = 15.0
        elif pct_rank >= 0.70:
            scores.loc[idx] = 10.0
        elif rs_val > 0:
            scores.loc[idx] = 5.0
        else:
            scores.loc[idx] = 0.0

    return scores


def _build_subsector_heat_ranks(subsector_trend_df: pd.DataFrame | None) -> dict[str, int]:
    if subsector_trend_df is None or subsector_trend_df.empty:
        return {}
    if "sub_sector" not in subsector_trend_df.columns:
        return {}

    trend = subsector_trend_df.copy()
    trend["sub_sector"] = trend["sub_sector"].astype(str).str.strip()
    trend = trend[
        trend["sub_sector"].notna()
        & (trend["sub_sector"] != "")
        & (trend["sub_sector"] != UNCLASSIFIED_SUB_SECTOR)
    ]
    if trend.empty:
        return {}

    sort_cols = [c for c in ("total_turnover", "avg_return_pct") if c in trend.columns]
    if not sort_cols:
        return {}

    trend = trend.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return {
        str(row.sub_sector): rank + 1
        for rank, row in trend.reset_index(drop=True).iterrows()
    }


def _subsector_heat_score(sub_sector, heat_ranks: dict[str, int]) -> float:
    if sub_sector is None or (isinstance(sub_sector, float) and pd.isna(sub_sector)):
        return 0.0

    label = str(sub_sector).strip()
    if label == "" or label == UNCLASSIFIED_SUB_SECTOR:
        return 0.0

    rank = heat_ranks.get(label)
    if rank is None:
        return 0.0
    if rank <= 3:
        return 15.0
    if rank <= 10:
        return 10.0
    return 5.0


def _sector_heat_hotness_component(
    df: pd.DataFrame, subsector_trend_df: pd.DataFrame | None
) -> pd.Series:
    heat_ranks = _build_subsector_heat_ranks(subsector_trend_df)
    if not heat_ranks or "sub_sector" not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)

    return df["sub_sector"].apply(lambda value: _subsector_heat_score(value, heat_ranks))


def _raw_turnover_participation_hotness_component(df: pd.DataFrame) -> pd.Series:
    """Small participation component from raw turnover. Max 10 points; does not dominate."""
    amount = _col_numeric(df, "amount")
    scores = pd.Series(0.0, index=df.index, dtype=float)
    valid = amount.notna()
    if not valid.any():
        return scores

    scores.loc[valid & (amount >= 1_000_000_000)] = 10.0
    scores.loc[valid & (amount >= 500_000_000) & (amount < 1_000_000_000)] = 8.0
    scores.loc[valid & (amount >= 100_000_000) & (amount < 500_000_000)] = 6.0
    scores.loc[valid & (amount >= 50_000_000) & (amount < 100_000_000)] = 4.0
    scores.loc[valid & (amount >= 20_000_000) & (amount < 50_000_000)] = 2.0
    return scores


def _technical_confirmation_hotness_component(df: pd.DataFrame) -> pd.Series:
    confirmed = confirmed_breakout_mask(df).fillna(False).astype(int)
    momentum = momentum_mask(df).fillna(False).astype(int)
    return confirmed * 3 + momentum * 2


def _build_hotness_reason_row(
    pct_60d_score: float,
    ratio_score: float,
    rs_score: float,
    sector_score: float,
    participation_score: float,
    tech_bonus: float,
    turnover_percentile_60d: float,
    turnover_ratio_20d: float,
) -> str:
    reasons: list[str] = []
    if pd.notna(turnover_percentile_60d) and turnover_percentile_60d >= 70:
        reasons.append("成交金額位於60日高分位")
    elif pct_60d_score >= 15:
        reasons.append("成交金額位於60日高分位")
    if (
        (pd.notna(turnover_ratio_20d) and turnover_ratio_20d >= 1.5)
        or ratio_score >= 10
    ):
        reasons.append("成交金額明顯高於20日均值")
    if rs_score >= 5:
        reasons.append("相對市場強勢")
    if sector_score >= 5:
        reasons.append("熱門族群")
    if participation_score >= 2:
        reasons.append("市場參與度高")
    if tech_bonus > 0:
        reasons.append("技術確認")
    return "、".join(reasons)


def calculate_hotness_score(
    df: pd.DataFrame,
    market_return: float | None = None,
    subsector_trend_df: pd.DataFrame | None = None,
    industry_trend_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add hotness_score (0-100) and hotness_reason.

    Raw turnover contributes at most 10 participation points and does not replace
    turnover percentile or ratio components.
    """
    if df.empty:
        return df.copy()

    _ = industry_trend_df  # reserved for future industry-level heat fallback

    result = df.copy()
    if market_return is None:
        market_return = _market_median_return(result)

    pct_60d_score = _turnover_percentile_hotness_component(result)
    ratio_score = _turnover_ratio_hotness_component(result)
    rs_score = _relative_strength_hotness_component(result, market_return)
    sector_score = _sector_heat_hotness_component(result, subsector_trend_df)
    participation_score = _raw_turnover_participation_hotness_component(result)
    tech_bonus = _technical_confirmation_hotness_component(result)

    hotness = (
        pct_60d_score
        + ratio_score
        + rs_score
        + sector_score
        + participation_score
        + tech_bonus
    )
    result["hotness_score"] = hotness.round(2).clip(lower=0, upper=HOTNESS_MAX_SCORE)

    turnover_percentile = _col_numeric(result, "turnover_percentile_60d")
    turnover_ratio = _col_numeric(result, "turnover_ratio_20d")

    result["hotness_reason"] = [
        _build_hotness_reason_row(p, r, rs, sec, part, tb, tp, tr)
        for p, r, rs, sec, part, tb, tp, tr in zip(
            pct_60d_score,
            ratio_score,
            rs_score,
            sector_score,
            participation_score,
            tech_bonus,
            turnover_percentile,
            turnover_ratio,
        )
    ]

    return result


def calculate_technical_score(
    df: pd.DataFrame,
    market_return: float | None = None,
) -> pd.DataFrame:
    """Add technical_score (= signal_score) and signal_reason. Raw amount is not used."""
    if df.empty:
        return df.copy()

    if market_return is None:
        market_return = _market_median_return(df)

    return _attach_technical_signals_and_scores(df, market_return)


def score_signals(
    df: pd.DataFrame,
    market_return: float | None = None,
    subsector_trend_df: pd.DataFrame | None = None,
    industry_trend_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    scored = df.copy()
    returns = _col_numeric(scored, "return_pct")
    if market_return is None:
        market_return = float(returns.median()) if returns.notna().any() else 0.0

    scored = _attach_technical_signals_and_scores(scored, market_return)

    scored = calculate_hotness_score(
        scored,
        market_return=market_return,
        subsector_trend_df=subsector_trend_df,
        industry_trend_df=industry_trend_df,
    )

    sort_cols = ["technical_score", "signal_score"]
    for col in ("hotness_score", "technical_score", "amount", "return_pct"):
        if col in scored.columns:
            sort_cols.append(col)
    return scored.sort_values(sort_cols, ascending=[False] * len(sort_cols))
