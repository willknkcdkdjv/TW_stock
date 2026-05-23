import os
from pathlib import Path
from datetime import datetime

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
QUANT_DIR = BASE_DIR / "quant_data"
OUTPUT_DIR = BASE_DIR / "trader_dashboard"
OUTPUT_DIR.mkdir(exist_ok=True)


def read_parquet_safe(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as e:
        print(f"[Skip] Cannot read {path}: {e}")
        return pd.DataFrame()


def clean_stock_id(df: pd.DataFrame) -> pd.DataFrame:
    if "stock_id" in df.columns:
        df["stock_id"] = df["stock_id"].astype(str).str.replace('="', "", regex=False).str.replace('"', "", regex=False)
    return df


def load_price_data() -> pd.DataFrame:
    candidates = list(QUANT_DIR.rglob("STOCK_DAY_ALL.parquet"))
    if not candidates:
        print("[Warning] Cannot find STOCK_DAY_ALL.parquet")
        return pd.DataFrame()

    df = read_parquet_safe(candidates[0])
    if df.empty:
        return df

    df = clean_stock_id(df)

    needed = ["date", "stock_id", "stock_name", "volume", "amount", "open", "high", "low", "close", "change", "transactions"]
    for col in needed:
        if col not in df.columns:
            df[col] = pd.NA

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["volume", "amount", "open", "high", "low", "close", "change", "transactions"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "stock_id"])
    return df


def load_valuation_data() -> pd.DataFrame:
    candidates = list(QUANT_DIR.rglob("BWIBBU_ALL.parquet"))
    if not candidates:
        print("[Warning] Cannot find BWIBBU_ALL.parquet")
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
    return df


def get_latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    latest_date = df["date"].max()
    return df[df["date"] == latest_date].copy()


def build_price_signals(price: pd.DataFrame) -> dict:
    if price.empty:
        return {
            "market_summary": pd.DataFrame(),
            "volume_spike": pd.DataFrame(),
            "price_breakout": pd.DataFrame(),
            "top_turnover": pd.DataFrame(),
            "top_gainers": pd.DataFrame(),
            "top_losers": pd.DataFrame(),
        }

    price = price.sort_values(["stock_id", "date"]).copy()

    price["prev_close"] = price.groupby("stock_id")["close"].shift(1)
    price["return_pct"] = (price["close"] / price["prev_close"] - 1) * 100

    price["vol_ma5"] = price.groupby("stock_id")["volume"].transform(lambda x: x.rolling(5, min_periods=3).mean())
    price["vol_ma20"] = price.groupby("stock_id")["volume"].transform(lambda x: x.rolling(20, min_periods=5).mean())
    price["volume_ratio_20d"] = price["volume"] / price["vol_ma20"]

    price["ma5"] = price.groupby("stock_id")["close"].transform(lambda x: x.rolling(5, min_periods=3).mean())
    price["ma20"] = price.groupby("stock_id")["close"].transform(lambda x: x.rolling(20, min_periods=5).mean())
    price["high_20d_prev"] = price.groupby("stock_id")["high"].transform(lambda x: x.shift(1).rolling(20, min_periods=5).max())

    latest = get_latest_snapshot(price)
    if latest.empty:
        return {}

    latest_date = latest["date"].max()

    market_summary = pd.DataFrame([{
        "dashboard_date": latest_date.strftime("%Y-%m-%d"),
        "stock_count": latest["stock_id"].nunique(),
        "up_count": int((latest["return_pct"] > 0).sum()),
        "down_count": int((latest["return_pct"] < 0).sum()),
        "flat_count": int((latest["return_pct"] == 0).sum()),
        "total_turnover": latest["amount"].sum(),
        "median_return_pct": latest["return_pct"].median(),
    }])

    columns = [
        "date", "stock_id", "stock_name", "close", "return_pct", "volume", "vol_ma20",
        "volume_ratio_20d", "amount", "ma5", "ma20", "high_20d_prev"
    ]

    volume_spike = latest[
        (latest["volume_ratio_20d"] >= 2) &
        (latest["amount"] > 0)
    ].sort_values(["volume_ratio_20d", "amount"], ascending=[False, False])[columns].head(50)

    price_breakout = latest[
        (latest["close"] > latest["high_20d_prev"]) &
        (latest["volume_ratio_20d"] >= 1.5)
    ].sort_values(["return_pct", "volume_ratio_20d"], ascending=[False, False])[columns].head(50)

    top_turnover = latest.sort_values("amount", ascending=False)[columns].head(50)
    top_gainers = latest.sort_values("return_pct", ascending=False)[columns].head(50)
    top_losers = latest.sort_values("return_pct", ascending=True)[columns].head(50)

    return {
        "market_summary": market_summary,
        "volume_spike": volume_spike,
        "price_breakout": price_breakout,
        "top_turnover": top_turnover,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }


def build_valuation_signals(valuation: pd.DataFrame) -> dict:
    if valuation.empty:
        return {
            "cheap_value": pd.DataFrame(),
            "high_dividend": pd.DataFrame(),
        }

    latest = get_latest_snapshot(valuation)
    if latest.empty:
        return {
            "cheap_value": pd.DataFrame(),
            "high_dividend": pd.DataFrame(),
        }

    columns = ["date", "stock_id", "stock_name", "pe", "pb", "div_yield"]

    cheap_value = latest[
        (latest["pe"] > 0) &
        (latest["pe"] <= 15) &
        (latest["pb"] > 0) &
        (latest["pb"] <= 1.5)
    ].sort_values(["pe", "pb"], ascending=[True, True])[columns].head(50)

    high_dividend = latest[
        (latest["div_yield"] >= 4) &
        (latest["pe"] > 0)
    ].sort_values(["div_yield", "pe"], ascending=[False, True])[columns].head(50)

    return {
        "cheap_value": cheap_value,
        "high_dividend": high_dividend,
    }


def format_excel(writer, sheet_name: str, df: pd.DataFrame):
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]

    header_format = workbook.add_format({
        "bold": True,
        "bg_color": "#D9EAF7",
        "border": 1,
        "align": "center",
    })
    number_format = workbook.add_format({"num_format": "#,##0.00"})
    integer_format = workbook.add_format({"num_format": "#,##0"})
    percent_format = workbook.add_format({"num_format": "0.00"})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)

    for idx, col in enumerate(df.columns):
        width = min(max(len(str(col)) + 2, 12), 24)
        if col in ["stock_name"]:
            width = 18
        elif col in ["date", "dashboard_date"]:
            width = 14
        worksheet.set_column(idx, idx, width)

        if col in ["date", "dashboard_date"]:
            worksheet.set_column(idx, idx, width, date_format)
        elif col in ["volume", "amount", "transactions", "stock_count", "up_count", "down_count", "flat_count", "total_turnover"]:
            worksheet.set_column(idx, idx, width, integer_format)
        elif col in ["return_pct", "volume_ratio_20d", "pe", "pb", "div_yield", "ma5", "ma20", "close", "high_20d_prev", "vol_ma20"]:
            worksheet.set_column(idx, idx, width, number_format)

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))


def export_dashboard(all_sheets: dict):
    today = datetime.now().strftime("%Y%m%d")
    output_file = OUTPUT_DIR / f"daily_trader_dashboard_{today}.xlsx"

    with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
        for sheet_name, df in all_sheets.items():
            safe_name = sheet_name[:31]
            if df is None or df.empty:
                df = pd.DataFrame({"message": ["No data available for this sheet."]})
            df.to_excel(writer, sheet_name=safe_name, index=False)
            format_excel(writer, safe_name, df)

    print(f"[Done] Dashboard exported: {output_file}")
    return output_file


def main():
    if not QUANT_DIR.exists():
        print("[Error] Cannot find quant_data/. Please run: python3 main.py first")
        return

    print("[Step 1] Loading price data...")
    price = load_price_data()

    print("[Step 2] Loading valuation data...")
    valuation = load_valuation_data()

    print("[Step 3] Building dashboard signals...")
    price_sheets = build_price_signals(price)
    valuation_sheets = build_valuation_signals(valuation)

    all_sheets = {}
    all_sheets.update(price_sheets)
    all_sheets.update(valuation_sheets)

    print("[Step 4] Exporting Excel dashboard...")
    export_dashboard(all_sheets)


if __name__ == "__main__":
    main()
