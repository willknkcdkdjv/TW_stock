import numpy as np
import pandas as pd

FLAT_RETURN_THRESHOLD = 0.01
LARGE_CAP_PERCENTILE = 70
SMALL_CAP_PERCENTILE = 30
SECTOR_LEADERSHIP_TOP_N = 5


def _return_series(df: pd.DataFrame) -> pd.Series:
    if "return_pct" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["return_pct"], errors="coerce")


def _amount_series(df: pd.DataFrame) -> pd.Series:
    if "amount" not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df["amount"], errors="coerce")


def get_market_breadth(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_stocks": 0,
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "up_ratio": 0.0,
            "advance_decline_ratio": 0.0,
            "average_return": 0.0,
            "median_return": 0.0,
        }

    returns = _return_series(df)
    valid = returns.notna()
    total_stocks = int(valid.sum())

    up_count = int((returns > FLAT_RETURN_THRESHOLD).sum())
    down_count = int((returns < -FLAT_RETURN_THRESHOLD).sum())
    flat_count = int(total_stocks - up_count - down_count)

    up_ratio = up_count / total_stocks if total_stocks else 0.0
    if down_count > 0:
        advance_decline_ratio = up_count / down_count
    elif up_count > 0:
        advance_decline_ratio = float(up_count)
    else:
        advance_decline_ratio = 0.0

    return {
        "total_stocks": total_stocks,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "up_ratio": round(up_ratio, 4),
        "advance_decline_ratio": round(advance_decline_ratio, 4),
        "average_return": round(float(returns.mean()), 4) if valid.any() else 0.0,
        "median_return": round(float(returns.median()), 4) if valid.any() else 0.0,
    }


def get_large_vs_small_cap(df: pd.DataFrame) -> dict:
    empty = {
        "large_cap_avg_return": 0.0,
        "small_cap_avg_return": 0.0,
        "large_cap_up_ratio": 0.0,
        "small_cap_up_ratio": 0.0,
    }
    if df.empty:
        return empty

    returns = _return_series(df)
    amount = _amount_series(df)
    valid = returns.notna() & amount.notna()
    if not valid.any():
        return empty

    work = df.loc[valid, ["return_pct", "amount"]].copy()
    work["return_pct"] = pd.to_numeric(work["return_pct"], errors="coerce")
    work["amount"] = pd.to_numeric(work["amount"], errors="coerce")

    large_threshold = np.percentile(work["amount"], LARGE_CAP_PERCENTILE)
    small_threshold = np.percentile(work["amount"], SMALL_CAP_PERCENTILE)

    large_cap = work[work["amount"] >= large_threshold]
    small_cap = work[work["amount"] <= small_threshold]

    def _up_ratio(group: pd.DataFrame) -> float:
        if group.empty:
            return 0.0
        return float((group["return_pct"] > FLAT_RETURN_THRESHOLD).mean())

    return {
        "large_cap_avg_return": round(float(large_cap["return_pct"].mean()), 4)
        if not large_cap.empty
        else 0.0,
        "small_cap_avg_return": round(float(small_cap["return_pct"].mean()), 4)
        if not small_cap.empty
        else 0.0,
        "large_cap_up_ratio": round(_up_ratio(large_cap), 4),
        "small_cap_up_ratio": round(_up_ratio(small_cap), 4),
    }


def get_sector_leadership(
    industry_df: pd.DataFrame, top_n: int = SECTOR_LEADERSHIP_TOP_N
) -> dict:
    columns = {
        "top_by_avg_return_pct": "avg_return_pct",
        "top_by_total_turnover": "total_turnover",
        "top_by_breakout_count": "breakout_count",
        "top_by_volume_spike_count": "volume_spike_count",
    }
    empty_result = {key: pd.DataFrame() for key in columns}

    if industry_df is None or industry_df.empty:
        return empty_result

    result = {}
    for key, sort_col in columns.items():
        if sort_col not in industry_df.columns:
            result[key] = pd.DataFrame()
            continue
        ranked = industry_df.sort_values(sort_col, ascending=False).head(top_n)
        result[key] = ranked.reset_index(drop=True)
    return result


def get_market_regime_summary(
    breadth: dict,
    large_vs_small: dict,
    sector_leadership: dict,
) -> str:
    comments: list[str] = []

    total = breadth.get("total_stocks", 0)
    if total == 0:
        return "資料不足，無法判斷市場體質。"

    up_ratio = breadth.get("up_ratio", 0.0)
    ad_ratio = breadth.get("advance_decline_ratio", 0.0)
    avg_return = breadth.get("average_return", 0.0)
    median_return = breadth.get("median_return", 0.0)

    if up_ratio >= 0.6 and ad_ratio >= 1.2:
        comments.append("市場廣度偏強，上漲家數具廣泛參與。")
    elif up_ratio >= 0.55:
        comments.append("市場廣度溫和偏強，多數個股收紅。")
    elif up_ratio <= 0.4 and ad_ratio <= 0.8:
        comments.append("市場廣度偏弱，下跌家數占優。")
    elif up_ratio <= 0.45:
        comments.append("市場廣度溫和偏弱，參與度有限。")
    else:
        comments.append("市場廣度中性，多空力量大致均衡。")

    large_ret = large_vs_small.get("large_cap_avg_return", 0.0)
    small_ret = large_vs_small.get("small_cap_avg_return", 0.0)
    large_up = large_vs_small.get("large_cap_up_ratio", 0.0)
    small_up = large_vs_small.get("small_cap_up_ratio", 0.0)
    ret_spread = large_ret - small_ret

    if ret_spread >= 0.3 and large_up >= small_up + 0.05:
        comments.append("大型股領漲，資金偏向高成交核心標的。")
    elif ret_spread <= -0.3 and small_up >= large_up + 0.05:
        comments.append("小型股表現優於大型股，投機與輪動特徵較明顯。")
    elif abs(ret_spread) < 0.15:
        comments.append("大小型股表現差距不大，風格未明顯分化。")

    top_return = sector_leadership.get("top_by_avg_return_pct", pd.DataFrame())
    top_turnover = sector_leadership.get("top_by_total_turnover", pd.DataFrame())
    top_breakout = sector_leadership.get("top_by_breakout_count", pd.DataFrame())
    top_spike = sector_leadership.get("top_by_volume_spike_count", pd.DataFrame())

    if not top_return.empty and "industry" in top_return.columns:
        leader = top_return.iloc[0]["industry"]
        leader_ret = top_return.iloc[0].get("avg_return_pct", 0.0)
        comments.append(f"產業輪動上，{leader}（平均漲幅 {leader_ret:.2f}%）相對領先。")

    if not top_turnover.empty and "industry" in top_turnover.columns:
        turnover_leader = top_turnover.iloc[0]["industry"]
        comments.append(f"成交熱度集中於 {turnover_leader}。")

    total_breakouts = 0
    total_spikes = 0
    industry_count = 0
    if not top_breakout.empty:
        industry_count = max(industry_count, len(top_breakout))
        if "breakout_count" in top_breakout.columns:
            total_breakouts = int(top_breakout["breakout_count"].sum())
    if not top_spike.empty and "volume_spike_count" in top_spike.columns:
        total_spikes = int(top_spike["volume_spike_count"].sum())

    breakout_participation = total_breakouts / total if total else 0.0
    spike_participation = total_spikes / total if total else 0.0

    if spike_participation >= 0.08 or total_spikes >= 30:
        comments.append("風險偏好偏高，量能異常放大個股增多。")
    elif spike_participation <= 0.02 and avg_return > 0:
        comments.append("指數偏強但量能異常有限，追價意願仍偏保守。")

    if avg_return > 0 and breakout_participation < 0.03:
        comments.append("整體報酬為正，但突破參與度偏弱，漲勢仍以少數標的驅動。")
    elif breakout_participation >= 0.05:
        comments.append("突破型態參與度尚可，趨勢延續動能存在。")

    if median_return < 0 <= avg_return:
        comments.append("平均報酬受少數大漲股拉抬，中位數仍偏弱，結構並非全面走強。")
    elif median_return > 0 and avg_return > 0:
        comments.append("平均與中位數報酬同步偏正，上漲結構較為健康。")

    return "\n".join(comments)
