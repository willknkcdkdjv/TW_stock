import numpy as np
import pandas as pd

VOLUME_SPIKE_MIN_AMOUNT = 100_000_000
LIQUIDITY_TOP_10_PERCENTILE = 0.9
LIQUIDITY_TOP_20_PERCENTILE = 0.8


def _col_numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def _liquidity_scores(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return (liquidity_score, high_turnover_signal) from amount percentiles."""
    if df.empty:
        return pd.Series(dtype=int), pd.Series(dtype=bool)

    amount = _col_numeric(df, "amount")
    liquidity_score = pd.Series(0, index=df.index, dtype=int)
    high_turnover = pd.Series(False, index=df.index, dtype=bool)

    if not amount.notna().any():
        return liquidity_score, high_turnover

    p80 = amount.quantile(LIQUIDITY_TOP_20_PERCENTILE)
    p90 = amount.quantile(LIQUIDITY_TOP_10_PERCENTILE)
    valid = amount.notna()
    high_turnover = valid & (amount >= p80)
    top_10 = valid & (amount >= p90)
    top_20 = valid & (amount >= p80) & (amount < p90)
    liquidity_score = liquidity_score.mask(top_10, 2).mask(top_20, 1)

    return liquidity_score, high_turnover


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


def breakout_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)
    close = _col_numeric(df, "close")
    high_20d_prev = _col_numeric(df, "high_20d_prev")
    volume_ratio = _col_numeric(df, "volume_ratio_20d")
    valid = close.notna() & high_20d_prev.notna() & volume_ratio.notna()
    return valid & (close > high_20d_prev) & (volume_ratio >= 1.5)


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


def get_breakout_signal(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    mask = breakout_mask(df)
    if not mask.any():
        return pd.DataFrame(columns=df.columns)

    result = df.loc[mask].copy()
    return result.sort_values(
        ["return_pct", "volume_ratio_20d"], ascending=[False, False]
    )


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


def score_signals(df: pd.DataFrame, market_return: float | None = None) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    scored = df.copy()
    returns = _col_numeric(scored, "return_pct")
    if market_return is None:
        market_return = float(returns.median()) if returns.notna().any() else 0.0

    volume_spike = volume_spike_reason_mask(scored)
    breakout = breakout_mask(scored)
    momentum = momentum_mask(scored)
    relative_strength = relative_strength_mask(scored, market_return)
    liquidity_score, high_turnover = _liquidity_scores(scored)

    scored["volume_spike_signal"] = volume_spike.fillna(False)
    scored["breakout_signal"] = breakout.fillna(False)
    scored["momentum_signal"] = momentum.fillna(False)
    scored["relative_strength_signal"] = relative_strength.fillna(False)
    scored["liquidity_score"] = liquidity_score.fillna(0).astype(int)
    scored["high_turnover_signal"] = high_turnover.fillna(False)

    scored["signal_score"] = (
        scored["volume_spike_signal"].astype(int)
        + scored["breakout_signal"].astype(int) * 2
        + scored["momentum_signal"].astype(int)
        + scored["relative_strength_signal"].astype(int)
        + scored["liquidity_score"]
        + scored["high_turnover_signal"].astype(int)
    )

    sort_cols = ["signal_score"]
    for col in ("amount", "return_pct"):
        if col in scored.columns:
            sort_cols.append(col)
    return scored.sort_values(sort_cols, ascending=[False] * len(sort_cols))
