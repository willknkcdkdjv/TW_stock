#!/usr/bin/env python3
"""Backfill historical TWSE daily stock data into STOCK_DAY_ALL.parquet."""

from __future__ import annotations

import argparse
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
PARQUET_PATH = BASE_DIR / "quant_data" / "securities_trading" / "STOCK_DAY_ALL.parquet"
MI_INDEX_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

DEFAULT_DAYS = 90
REQUEST_SLEEP_SECONDS = 1
MAX_RETRIES = 3

STANDARD_COLUMNS = [
    "date",
    "stock_id",
    "stock_name",
    "volume",
    "amount",
    "open",
    "high",
    "low",
    "close",
    "change",
    "transactions",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def clean_numeric_value(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "--", "X", "nan", "None", "<NA>"):
        return None
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace(",", "").strip()
    if text in ("", "--", "X"):
        return None
    numeric = pd.to_numeric(text, errors="coerce")
    if pd.isna(numeric):
        return None
    return float(numeric)


def normalize_stock_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    text = text.replace('="', "").replace('"', "")
    text = re.sub(r"\.0$", "", text)
    if text in ("", "--", "nan", "None", "<NA>"):
        return None
    return text


def is_valid_stock_id(stock_id: str) -> bool:
    """Keep normal listed stock/ETF codes (same rule as twse_crawler)."""
    if not stock_id:
        return False
    if len(stock_id) > 4:
        return False
    return stock_id.isalnum()


def parse_change(direction, change_diff) -> float | None:
    diff = clean_numeric_value(change_diff)
    if diff is None:
        return None
    direction_text = re.sub(r"<[^>]+>", "", str(direction)).strip()
    if "green" in str(direction) or direction_text == "-":
        return -abs(diff)
    if "red" in str(direction) or direction_text == "+":
        return abs(diff)
    if diff == 0:
        return 0.0
    return diff


def _is_stock_daily_table(fields: list[str] | None) -> bool:
    if not fields:
        return False
    required = {"證券代號", "證券名稱", "成交股數", "成交金額", "收盤價"}
    return required.issubset(set(fields))


def parse_mi_index_response(payload: dict, trade_date: date) -> pd.DataFrame | None:
    if payload.get("stat") != "OK":
        return None

    stock_table = None
    for table in payload.get("tables", []):
        if _is_stock_daily_table(table.get("fields")):
            stock_table = table
            break

    if stock_table is None:
        return None

    fields = stock_table["fields"]
    rows = stock_table.get("data") or []
    if not rows:
        return None

    field_index = {name: idx for idx, name in enumerate(fields)}
    records: list[dict] = []

    for row in rows:
        stock_id = normalize_stock_id(row[field_index["證券代號"]])
        if not is_valid_stock_id(stock_id):
            continue

        direction_idx = field_index.get("漲跌(+/-)")
        diff_idx = field_index.get("漲跌價差")
        direction = row[direction_idx] if direction_idx is not None else ""
        change_diff = row[diff_idx] if diff_idx is not None else None

        records.append(
            {
                "date": pd.Timestamp(trade_date),
                "stock_id": stock_id,
                "stock_name": str(row[field_index["證券名稱"]]).strip(),
                "volume": clean_numeric_value(row[field_index["成交股數"]]),
                "amount": clean_numeric_value(row[field_index["成交金額"]]),
                "open": clean_numeric_value(row[field_index["開盤價"]]),
                "high": clean_numeric_value(row[field_index["最高價"]]),
                "low": clean_numeric_value(row[field_index["最低價"]]),
                "close": clean_numeric_value(row[field_index["收盤價"]]),
                "change": parse_change(direction, change_diff),
                "transactions": clean_numeric_value(row[field_index["成交筆數"]]),
            }
        )

    if not records:
        return None

    return pd.DataFrame(records, columns=STANDARD_COLUMNS)


def fetch_mi_index(trade_date: date) -> pd.DataFrame | None:
    date_str = trade_date.strftime("%Y%m%d")
    params = {"response": "json", "date": date_str, "type": "ALLBUT0999"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                MI_INDEX_URL,
                params=params,
                headers=HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            parsed = parse_mi_index_response(payload, trade_date)
            if parsed is not None and not parsed.empty:
                return parsed
            return None
        except Exception as exc:
            print(f"  [{date_str}] attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_SLEEP_SECONDS)
    return None


def iter_calendar_dates(days: int) -> list[date]:
    end = datetime.now().date()
    start = end - timedelta(days=days - 1)
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def load_existing_parquet() -> pd.DataFrame:
    if not PARQUET_PATH.exists():
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_parquet(PARQUET_PATH)
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["stock_id"] = df["stock_id"].apply(normalize_stock_id)
    for col in ["volume", "amount", "open", "high", "low", "close", "change", "transactions"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[[c for c in STANDARD_COLUMNS if c in df.columns]]


def merge_and_save(existing: pd.DataFrame, new_frames: list[pd.DataFrame]) -> tuple[pd.DataFrame, int]:
    before_count = len(existing)

    if new_frames:
        downloaded = pd.concat(new_frames, ignore_index=True)
    else:
        downloaded = pd.DataFrame(columns=STANDARD_COLUMNS)

    if existing.empty:
        merged = downloaded.copy()
    elif downloaded.empty:
        merged = existing.copy()
    else:
        merged = pd.concat([existing, downloaded], ignore_index=True)

    if merged.empty:
        PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(PARQUET_PATH, compression="zstd", index=False)
        return merged, 0

    merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
    merged["stock_id"] = merged["stock_id"].apply(normalize_stock_id)
    merged = merged.dropna(subset=["date", "stock_id"])
    merged = merged.drop_duplicates(subset=["date", "stock_id"], keep="last")
    merged = merged.sort_values(["date", "stock_id"]).reset_index(drop=True)
    merged = merged[STANDARD_COLUMNS]

    PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(PARQUET_PATH, compression="zstd", index=False)

    rows_added = len(merged) - before_count
    return merged, rows_added


def backfill(days: int) -> dict:
    dates = iter_calendar_dates(days)
    existing = load_existing_parquet()
    before_count = len(existing)

    downloaded_frames: list[pd.DataFrame] = []
    dates_successful = 0

    print(f"Backfilling {days} calendar days into {PARQUET_PATH}")
    print(f"Date range: {dates[0]} to {dates[-1]}")

    for index, trade_date in enumerate(dates):
        date_label = trade_date.strftime("%Y-%m-%d")
        print(f"[{index + 1}/{len(dates)}] Fetching {date_label} ...", end=" ")

        frame = fetch_mi_index(trade_date)
        if frame is None or frame.empty:
            print("skipped (non-trading day or empty response)")
        else:
            downloaded_frames.append(frame)
            dates_successful += 1
            print(f"ok ({len(frame):,} rows)")

        if index < len(dates) - 1:
            time.sleep(REQUEST_SLEEP_SECONDS)

    merged, rows_added = merge_and_save(existing, downloaded_frames)

    return {
        "dates_attempted": len(dates),
        "dates_successfully_downloaded": dates_successful,
        "rows_added": rows_added,
        "final_row_count": len(merged),
        "previous_row_count": before_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill TWSE historical daily stock data into STOCK_DAY_ALL.parquet"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Number of calendar days to backfill (default: {DEFAULT_DAYS})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.days <= 0:
        raise SystemExit("--days must be a positive integer")

    summary = backfill(args.days)

    print("\n========== Backfill Summary ==========")
    print(f"Dates attempted: {summary['dates_attempted']:,}")
    print(f"Dates successfully downloaded: {summary['dates_successfully_downloaded']:,}")
    print(f"Rows added: {summary['rows_added']:,}")
    print(f"Final row count: {summary['final_row_count']:,}")
    print(f"Saved to: {PARQUET_PATH}")


if __name__ == "__main__":
    main()
