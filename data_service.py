from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from signal_engine import (
    breakout_mask,
    get_breakout_signal,
    get_volume_spike_signal,
    volume_spike_mask,
)

BASE_DIR = Path(__file__).resolve().parent
QUANT_DIR = BASE_DIR / "quant_data"
SECTOR_MAPPING_PATH = BASE_DIR / "sector_mapping.csv"
DEFAULT_SUB_SECTOR = "未分類"

_warn_fn = None


def set_warn_fn(fn) -> None:
    global _warn_fn
    _warn_fn = fn


def remove_duplicate_columns(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    return df.loc[:, ~df.columns.duplicated()].copy()


DISPLAY_COLUMNS = [
    "date", "stock_id", "stock_name", "close", "return_pct", "volume",
    "vol_ma20", "volume_ratio_20d", "amount", "ma5", "ma20", "high_20d_prev",
]


def read_parquet_safe(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as e:
        if _warn_fn is not None:
            _warn_fn(f"Cannot read {path.name}: {e}")
        return pd.DataFrame()


def clean_stock_id(df: pd.DataFrame) -> pd.DataFrame:
    id_col = None
    if "stock_id" in df.columns:
        id_col = "stock_id"
    elif "公司代號" in df.columns:
        id_col = "公司代號"

    if id_col is None:
        return df

    df = df.copy()
    df[id_col] = (
        df[id_col]
        .astype(str)
        .str.replace('="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    return df


def load_price_data() -> pd.DataFrame:
    candidates = list(QUANT_DIR.rglob("STOCK_DAY_ALL.parquet"))
    if not candidates:
        return pd.DataFrame()

    df = read_parquet_safe(candidates[0])
    if df.empty:
        return df

    df = clean_stock_id(df)

    needed = [
        "date", "stock_id", "stock_name", "volume", "amount",
        "open", "high", "low", "close", "change", "transactions",
    ]
    for col in needed:
        if col not in df.columns:
            df[col] = pd.NA

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["volume", "amount", "open", "high", "low", "close", "change", "transactions"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "stock_id"])
    return remove_duplicate_columns(df)


def _resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


@lru_cache(maxsize=1)
def load_company_profile() -> pd.DataFrame:
    candidates = list(QUANT_DIR.rglob("t187ap03_L.parquet"))
    if not candidates:
        return pd.DataFrame(columns=["stock_id", "industry"])

    df = read_parquet_safe(candidates[0])
    if df.empty:
        return pd.DataFrame(columns=["stock_id", "industry"])

    df = clean_stock_id(df)

    stock_col = _resolve_column(df, ["stock_id", "公司代號", "Code"])
    industry_col = _resolve_column(df, ["industry", "產業別"])
    if stock_col is None or industry_col is None:
        return pd.DataFrame(columns=["stock_id", "industry"])

    profile = df[[stock_col, industry_col]].copy()
    profile = profile.rename(columns={stock_col: "stock_id", industry_col: "industry"})
    profile = clean_stock_id(profile)
    profile["industry"] = profile["industry"].astype(str).str.strip()
    profile = profile.dropna(subset=["stock_id"])
    profile = profile[profile["stock_id"] != ""]
    profile = profile.drop_duplicates(subset=["stock_id"], keep="last")
    return profile[["stock_id", "industry"]].reset_index(drop=True)


def _normalize_mapping_stock_id(series: pd.Series) -> pd.Series:
    """Normalize stock_id for mapping joins; preserve leading zeros."""
    normalized = (
        series.astype(str)
        .str.replace('="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    return normalized


@lru_cache(maxsize=1)
def load_sector_mapping() -> pd.DataFrame:
    empty = pd.DataFrame(columns=["stock_id", "sub_sector"])
    if not SECTOR_MAPPING_PATH.exists():
        return empty

    try:
        df = pd.read_csv(SECTOR_MAPPING_PATH, dtype={"stock_id": str})
    except Exception as e:
        if _warn_fn is not None:
            _warn_fn(f"Cannot read sector_mapping.csv: {e}")
        return empty

    if "stock_id" not in df.columns or "sub_sector" not in df.columns:
        if _warn_fn is not None:
            _warn_fn("sector_mapping.csv must include stock_id and sub_sector columns.")
        return empty

    mapping = df[["stock_id", "sub_sector"]].copy()
    mapping["stock_id"] = _normalize_mapping_stock_id(mapping["stock_id"])
    mapping["sub_sector"] = mapping["sub_sector"].astype(str).str.strip()
    mapping = mapping.dropna(subset=["stock_id"])
    mapping = mapping[mapping["stock_id"] != ""]
    mapping = mapping[mapping["sub_sector"] != ""]
    mapping = mapping.drop_duplicates(subset=["stock_id"], keep="last")
    return remove_duplicate_columns(mapping.reset_index(drop=True))


def apply_sector_mapping(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        result = df.copy()
        if "sub_sector" not in result.columns:
            result["sub_sector"] = pd.Series(dtype=str)
        return remove_duplicate_columns(result)

    result = remove_duplicate_columns(clean_stock_id(df.copy()))
    mapping = load_sector_mapping()

    sub_sector_cols = [c for c in result.columns if c == "sub_sector"]
    if sub_sector_cols:
        result = result.drop(columns=sub_sector_cols)

    if mapping.empty:
        result["sub_sector"] = DEFAULT_SUB_SECTOR
        return remove_duplicate_columns(result)

    result = result.merge(mapping, on="stock_id", how="left")
    if "sub_sector" not in result.columns:
        result["sub_sector"] = DEFAULT_SUB_SECTOR
    else:
        missing = result["sub_sector"].isna() | (
            result["sub_sector"].astype(str).str.strip() == ""
        )
        result.loc[missing, "sub_sector"] = DEFAULT_SUB_SECTOR

    return remove_duplicate_columns(result)


def merge_industry_into_snapshot(
    latest: pd.DataFrame, profile: pd.DataFrame
) -> pd.DataFrame:
    if latest.empty:
        return latest

    latest = clean_stock_id(latest.copy())
    if "industry" in latest.columns:
        latest = latest.drop(columns=["industry"])

    if profile.empty:
        latest["industry"] = pd.NA
        return remove_duplicate_columns(latest)

    profile = clean_stock_id(profile.copy())
    return remove_duplicate_columns(latest.merge(profile, on="stock_id", how="left"))


def load_valuation_data() -> pd.DataFrame:
    candidates = list(QUANT_DIR.rglob("BWIBBU_ALL.parquet"))
    if not candidates:
        return pd.DataFrame()

    df = read_parquet_safe(candidates[0])
    if df.empty:
        return df

    df = clean_stock_id(df)

    for col in ["date", "stock_id", "stock_name", "pe", "div_yield", "pb"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["pe", "div_yield", "pb"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "stock_id"])
    return remove_duplicate_columns(df)


def add_price_indicators(price: pd.DataFrame) -> pd.DataFrame:
    if price.empty:
        return price

    price = price.sort_values(["stock_id", "date"]).copy()

    price["prev_close"] = price.groupby("stock_id")["close"].shift(1)
    prev_close = pd.to_numeric(price["prev_close"], errors="coerce")
    close = pd.to_numeric(price["close"], errors="coerce")
    price["return_pct"] = np.where(
        prev_close.notna() & (prev_close != 0) & close.notna(),
        (close / prev_close - 1) * 100,
        np.nan,
    )

    price["vol_ma20"] = price.groupby("stock_id")["volume"].transform(
        lambda x: x.rolling(20, min_periods=5).mean()
    )
    price["volume_ratio_20d"] = price["volume"] / price["vol_ma20"]

    price["ma5"] = price.groupby("stock_id")["close"].transform(
        lambda x: x.rolling(5, min_periods=3).mean()
    )
    price["ma20"] = price.groupby("stock_id")["close"].transform(
        lambda x: x.rolling(20, min_periods=5).mean()
    )
    price["high_20d_prev"] = price.groupby("stock_id")["high"].transform(
        lambda x: x.shift(1).rolling(20, min_periods=5).max()
    )

    return remove_duplicate_columns(price)


def get_latest_market_snapshot(price: pd.DataFrame) -> dict:
    latest_date = price["date"].max()
    latest = price[price["date"] == latest_date].copy()
    profile = load_company_profile()
    latest = merge_industry_into_snapshot(latest, profile)
    latest = apply_sector_mapping(latest)

    industry_unknown_count = 0
    if "industry" in latest.columns:
        unknown_mask = latest["industry"].isna() | (
            latest["industry"].astype(str).str.strip() == ""
        )
        industry_unknown_count = int(unknown_mask.sum())

    if "return_pct" in latest.columns:
        valid = latest[latest["return_pct"].notna()]
    else:
        valid = latest.iloc[0:0]

    has_valid_returns = not valid.empty
    if has_valid_returns:
        returns = valid["return_pct"]
        up_count = int((returns > 0).sum())
        down_count = int((returns < 0).sum())
        median_return = float(returns.median())
    else:
        up_count = None
        down_count = None
        median_return = None

    latest = remove_duplicate_columns(latest)

    return {
        "latest_date": latest_date,
        "latest": latest,
        "up_count": up_count,
        "down_count": down_count,
        "total_turnover": latest["amount"].sum(),
        "median_return": median_return,
        "has_valid_returns": has_valid_returns,
        "valid_return_count": int(len(valid)),
        "latest_rows_count": int(len(latest)),
        "historical_date_count": int(price["date"].nunique()) if not price.empty else 0,
        "min_date": price["date"].min() if not price.empty else pd.NaT,
        "max_date": price["date"].max() if not price.empty else pd.NaT,
        "stock_count": latest["stock_id"].nunique(),
        "industry_profile_loaded": not profile.empty,
        "industry_unknown_count": industry_unknown_count,
    }


def _select_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = remove_duplicate_columns(df)
    cols = [c for c in DISPLAY_COLUMNS if c in df.columns]
    if not cols:
        return df
    return remove_duplicate_columns(df[cols])


def get_volume_spike(filtered: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    return remove_duplicate_columns(
        _select_display_columns(get_volume_spike_signal(filtered)).head(limit)
    )


def get_breakout(filtered: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    return remove_duplicate_columns(
        _select_display_columns(get_breakout_signal(filtered)).head(limit)
    )


def get_top_turnover(filtered: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    work = remove_duplicate_columns(filtered)
    cols = [c for c in DISPLAY_COLUMNS if c in work.columns]
    return remove_duplicate_columns(
        work.sort_values("amount", ascending=False)[cols].head(limit)
    )


def get_top_gainers(filtered: pd.DataFrame, limit: int = 50) -> pd.DataFrame:
    work = remove_duplicate_columns(filtered)
    cols = [c for c in DISPLAY_COLUMNS if c in work.columns]
    return remove_duplicate_columns(
        work.sort_values("return_pct", ascending=False)[cols].head(limit)
    )


def get_top_losers(filtered: pd.DataFrame, limit: int = 50) -> pd.DataFrame:
    work = remove_duplicate_columns(filtered)
    cols = [c for c in DISPLAY_COLUMNS if c in work.columns]
    return remove_duplicate_columns(
        work.sort_values("return_pct", ascending=True)[cols].head(limit)
    )


def get_cheap_value(valuation: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if valuation.empty:
        return pd.DataFrame()

    latest_val_date = valuation["date"].max()
    latest_val = valuation[valuation["date"] == latest_val_date].copy()

    cheap_value = latest_val[
        (latest_val["pe"] > 0) &
        (latest_val["pe"] <= 15) &
        (latest_val["pb"] > 0) &
        (latest_val["pb"] <= 1.5)
    ].sort_values(["pe", "pb"], ascending=[True, True])

    return remove_duplicate_columns(cheap_value.head(limit))


def get_high_dividend(valuation: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if valuation.empty:
        return pd.DataFrame()

    latest_val_date = valuation["date"].max()
    latest_val = valuation[valuation["date"] == latest_val_date].copy()

    high_dividend = latest_val[
        (latest_val["div_yield"] >= 4) &
        (latest_val["pe"] > 0)
    ].sort_values(["div_yield", "pe"], ascending=[False, True])

    return remove_duplicate_columns(high_dividend.head(limit))


TWSE_INDUSTRY_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "20": "其他",
    "21": "化學工業",
    "22": "生技醫療",
    "23": "油電燃氣",
    "24": "半導體業",
    "25": "電腦及週邊設備",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技",
    "34": "電子商務",
}

INDUSTRY_TREND_COLUMNS = [
    "industry",
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

SUBSECTOR_TREND_COLUMNS = [
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


def normalize_industry_code(code) -> str | None:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return None

    raw = str(code).strip()
    if raw == "" or raw.lower() == "unknown" or raw.lower() == "nan":
        return None

    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]

    if not raw.isdigit():
        return None

    return f"{int(raw):02d}"


def map_industry_to_name(code) -> str:
    normalized = normalize_industry_code(code)
    if normalized is None:
        return "Unknown"
    return TWSE_INDUSTRY_MAP.get(normalized, "Unknown")


def get_industry_trend(filtered: pd.DataFrame) -> pd.DataFrame:
    if filtered.empty:
        return pd.DataFrame(columns=INDUSTRY_TREND_COLUMNS)

    profile = load_company_profile()
    df = merge_industry_into_snapshot(filtered, profile)

    df["industry_name"] = df["industry"].apply(map_industry_to_name)

    df["is_up"] = df["return_pct"] > 0
    df["is_down"] = df["return_pct"] < 0
    df["is_volume_spike"] = volume_spike_mask(df)
    df["is_breakout"] = breakout_mask(df)

    trend = df.groupby("industry_name", dropna=False, as_index=False).agg(
        stock_count=("stock_id", "nunique"),
        up_count=("is_up", "sum"),
        down_count=("is_down", "sum"),
        avg_return_pct=("return_pct", "mean"),
        median_return_pct=("return_pct", "median"),
        total_turnover=("amount", "sum"),
        volume_spike_count=("is_volume_spike", "sum"),
        breakout_count=("is_breakout", "sum"),
    )

    trend = trend.rename(columns={"industry_name": "industry"})

    trend["up_count"] = trend["up_count"].astype(int)
    trend["down_count"] = trend["down_count"].astype(int)
    trend["volume_spike_count"] = trend["volume_spike_count"].astype(int)
    trend["breakout_count"] = trend["breakout_count"].astype(int)
    trend["up_ratio"] = trend["up_count"] / trend["stock_count"].replace(0, pd.NA)

    trend = remove_duplicate_columns(
        trend.sort_values("total_turnover", ascending=False)
    )
    return trend.reindex(columns=INDUSTRY_TREND_COLUMNS)


def get_subsector_trend(filtered: pd.DataFrame) -> pd.DataFrame:
    if filtered.empty:
        return pd.DataFrame(columns=SUBSECTOR_TREND_COLUMNS)

    df = apply_sector_mapping(filtered.copy())

    if "return_pct" in df.columns:
        returns = pd.to_numeric(df["return_pct"], errors="coerce")
    else:
        returns = pd.Series(np.nan, index=df.index, dtype=float)

    df["is_up"] = returns.notna() & (returns > 0)
    df["is_down"] = returns.notna() & (returns < 0)
    df["is_volume_spike"] = volume_spike_mask(df)
    df["is_breakout"] = breakout_mask(df)

    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    trend = df.groupby("sub_sector", dropna=False, as_index=False).agg(
        stock_count=("stock_id", "nunique"),
        up_count=("is_up", "sum"),
        down_count=("is_down", "sum"),
        avg_return_pct=("return_pct", "mean"),
        median_return_pct=("return_pct", "median"),
        total_turnover=("amount", "sum"),
        volume_spike_count=("is_volume_spike", "sum"),
        breakout_count=("is_breakout", "sum"),
    )

    trend["up_count"] = trend["up_count"].astype(int)
    trend["down_count"] = trend["down_count"].astype(int)
    trend["volume_spike_count"] = trend["volume_spike_count"].astype(int)
    trend["breakout_count"] = trend["breakout_count"].astype(int)
    trend["up_ratio"] = trend["up_count"] / trend["stock_count"].replace(0, pd.NA)

    trend = remove_duplicate_columns(trend.sort_values("total_turnover", ascending=False))
    return remove_duplicate_columns(trend.reindex(columns=SUBSECTOR_TREND_COLUMNS))


LLM_PRICE_COLUMNS = [
    "date", "stock_id", "stock_name", "close", "return_pct",
    "volume_ratio_20d", "amount",
]
LLM_VALUATION_COLUMNS = [
    "date", "stock_id", "stock_name", "pe", "pb", "div_yield",
]


def _round_for_llm(value):
    if pd.api.types.is_number(value) and not isinstance(value, bool):
        if pd.isna(value):
            return None
        return round(float(value), 2)
    return value


def _df_top_records(
    df: pd.DataFrame, limit: int, columns: list[str] | None = None
) -> list[dict]:
    """Return at most `limit` row dicts for LLM context (never the full dataframe)."""
    if df is None or df.empty:
        return []

    subset = df.head(limit).copy()
    if columns:
        subset = subset[[c for c in columns if c in subset.columns]]

    if "date" in subset.columns:
        subset["date"] = (
            pd.to_datetime(subset["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        )

    records = subset.to_dict(orient="records")
    for row in records:
        for key, value in list(row.items()):
            row[key] = _round_for_llm(value)
    return records


def build_llm_market_context(
    snapshot: dict,
    filtered: pd.DataFrame,
    valuation: pd.DataFrame,
    latest_date,
    min_amount: int,
    keyword: str,
) -> dict:
    signal_summary = {
        "volume_spike_count": 0,
        "breakout_count": 0,
    }
    if not filtered.empty:
        signal_summary["volume_spike_count"] = int(volume_spike_mask(filtered).sum())
        signal_summary["breakout_count"] = int(breakout_mask(filtered).sum())

    return {
        "market_summary": {
            "date": latest_date.strftime("%Y-%m-%d"),
            "stock_count": int(snapshot["stock_count"]),
            "up_count": (
                int(snapshot["up_count"])
                if snapshot.get("up_count") is not None
                else None
            ),
            "down_count": (
                int(snapshot["down_count"])
                if snapshot.get("down_count") is not None
                else None
            ),
            "total_turnover": _round_for_llm(snapshot["total_turnover"]),
            "median_return_pct": _round_for_llm(snapshot.get("median_return")),
            "has_valid_returns": bool(snapshot.get("has_valid_returns", False)),
            "filtered_stock_count": (
                int(filtered["stock_id"].nunique()) if not filtered.empty else 0
            ),
            "industry_profile_loaded": bool(
                snapshot.get("industry_profile_loaded", False)
            ),
            "industry_unknown_count": int(
                snapshot.get("industry_unknown_count", 0)
            ),
            "filters": {
                "min_amount": int(min_amount),
                "keyword": keyword.strip(),
            },
            "signal_summary": signal_summary,
        },
        "industry_trend": _df_top_records(
            get_industry_trend(filtered) if not filtered.empty else pd.DataFrame(),
            5,
            INDUSTRY_TREND_COLUMNS,
        ),
        "volume_spike": _df_top_records(
            get_volume_spike(filtered, limit=10) if not filtered.empty else pd.DataFrame(),
            10,
            LLM_PRICE_COLUMNS,
        ),
        "breakout": _df_top_records(
            get_breakout(filtered, limit=10) if not filtered.empty else pd.DataFrame(),
            10,
            LLM_PRICE_COLUMNS,
        ),
        "top_turnover": _df_top_records(
            get_top_turnover(filtered, limit=10) if not filtered.empty else pd.DataFrame(),
            10,
            LLM_PRICE_COLUMNS,
        ),
        "cheap_value": _df_top_records(
            get_cheap_value(valuation, limit=10),
            10,
            LLM_VALUATION_COLUMNS,
        ),
        "high_dividend": _df_top_records(
            get_high_dividend(valuation, limit=10),
            10,
            LLM_VALUATION_COLUMNS,
        ),
    }
