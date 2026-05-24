"""Streamlit admin tool for classifying unmapped stocks into sector_mapping.csv."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
UNMAPPED_PATH = BASE_DIR / "unmapped_review.csv"
SECTOR_MAPPING_PATH = BASE_DIR / "sector_mapping.csv"

SUB_SECTOR_OPTIONS = [
    "AI Server",
    "伺服器代工",
    "IC設計",
    "晶圓代工",
    "封裝測試",
    "半導體設備材料",
    "記憶體",
    "MLCC",
    "被動元件",
    "PCB",
    "CCL",
    "連接器",
    "電源供應器",
    "散熱",
    "網通",
    "光通訊/CPO",
    "面板",
    "LED",
    "IPC工業電腦",
    "車用電子",
    "重電",
    "綠電/再生能源",
    "金融",
    "航運",
    "建設營造",
    "生技醫療",
    "觀光餐旅",
    "食品",
    "塑化",
    "鋼鐵",
    "紡織",
    "水泥",
    "貿易百貨",
    "其他電子",
    "其他",
    "未分類",
]

DEFAULT_DISPLAY_ROWS = 100
SESSION_APPLY_RESULT_KEY = "mapping_admin_apply_result"


def normalize_stock_id(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    normalized = (
        str(value)
        .replace('="', "")
        .replace('"', "")
        .strip()
    )
    if normalized.endswith(".0") and normalized[:-2].isdigit():
        normalized = normalized[:-2]
    return normalized


def _normalize_stock_id_series(series: pd.Series) -> pd.Series:
    return series.map(normalize_stock_id).astype(str)


def load_unmapped_review() -> pd.DataFrame | None:
    if not UNMAPPED_PATH.exists():
        return None
    df = pd.read_csv(UNMAPPED_PATH, dtype={"stock_id": str})
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if "stock_id" in df.columns:
        df["stock_id"] = _normalize_stock_id_series(df["stock_id"])
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def load_sector_mapping() -> pd.DataFrame:
    if not SECTOR_MAPPING_PATH.exists():
        return pd.DataFrame(columns=["stock_id", "sub_sector"])

    df = pd.read_csv(SECTOR_MAPPING_PATH, dtype={"stock_id": str})
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if "stock_id" not in df.columns:
        return pd.DataFrame(columns=["stock_id", "sub_sector"])
    if "sub_sector" not in df.columns:
        df["sub_sector"] = pd.NA

    mapping = df[["stock_id", "sub_sector"]].copy()
    mapping["stock_id"] = _normalize_stock_id_series(mapping["stock_id"])
    mapping["sub_sector"] = mapping["sub_sector"].astype(str).str.strip()
    mapping = mapping.dropna(subset=["stock_id"])
    mapping = mapping[mapping["stock_id"] != ""]
    mapping = mapping[mapping["sub_sector"] != ""]
    return mapping.drop_duplicates(subset=["stock_id"], keep="last").reset_index(drop=True)


def save_sector_mapping(mapping: pd.DataFrame) -> pd.DataFrame:
    out = mapping.copy()
    if "stock_id" not in out.columns:
        out["stock_id"] = pd.Series(dtype=str)
    if "sub_sector" not in out.columns:
        out["sub_sector"] = pd.Series(dtype=str)

    out = out[["stock_id", "sub_sector"]].copy()
    out["stock_id"] = _normalize_stock_id_series(out["stock_id"])
    out["sub_sector"] = out["sub_sector"].astype(str).str.strip()
    out = out.dropna(subset=["stock_id", "sub_sector"])
    out = out[(out["stock_id"] != "") & (out["sub_sector"] != "")]
    out = out.drop_duplicates(subset=["stock_id"], keep="last")
    out = out.sort_values("stock_id").reset_index(drop=True)
    out.to_csv(SECTOR_MAPPING_PATH, index=False, encoding="utf-8-sig")
    return out


def parse_stock_ids(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []

    parts = re.split(r"[\n\r,;]+", raw.strip())
    seen: set[str] = set()
    ids: list[str] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        stock_id = normalize_stock_id(token)
        if stock_id and stock_id not in seen:
            seen.add(stock_id)
            ids.append(stock_id)
    return ids


def apply_mapping(stock_ids: list[str], sub_sector: str) -> tuple[pd.DataFrame, int]:
    if not stock_ids:
        return pd.DataFrame(columns=["stock_id", "sub_sector"]), 0

    mapping = load_sector_mapping()
    if mapping.empty:
        combined = pd.DataFrame(columns=["stock_id", "sub_sector"])
    else:
        combined = mapping.copy()

    updates = pd.DataFrame(
        {"stock_id": stock_ids, "sub_sector": sub_sector},
    )
    updates["stock_id"] = _normalize_stock_id_series(updates["stock_id"])
    updates["sub_sector"] = updates["sub_sector"].astype(str).str.strip()

    combined = pd.concat([combined, updates], ignore_index=True)
    combined = combined.drop_duplicates(subset=["stock_id"], keep="last")
    save_sector_mapping(combined)

    recent = updates[["stock_id", "sub_sector"]].drop_duplicates(subset=["stock_id"], keep="last")
    return recent.reset_index(drop=True), len(recent)


def filter_unmapped(
    df: pd.DataFrame,
    search: str,
    industry: str,
    min_turnover: float,
) -> pd.DataFrame:
    filtered = df.copy()

    if search.strip():
        kw = search.strip()
        mask = pd.Series(False, index=filtered.index)
        if "stock_id" in filtered.columns:
            mask |= filtered["stock_id"].astype(str).str.contains(kw, case=False, na=False)
        if "stock_name" in filtered.columns:
            mask |= filtered["stock_name"].astype(str).str.contains(kw, case=False, na=False)
        filtered = filtered[mask]

    if industry != "All" and "industry" in filtered.columns:
        filtered = filtered[filtered["industry"].astype(str) == industry]

    if min_turnover > 0 and "amount" in filtered.columns:
        filtered = filtered[filtered["amount"].fillna(0) >= min_turnover]

    if "amount" in filtered.columns:
        filtered = filtered.sort_values("amount", ascending=False, na_position="last")
    elif "stock_id" in filtered.columns:
        filtered = filtered.sort_values("stock_id")

    return filtered.reset_index(drop=True)


def _render_apply_result() -> None:
    result = st.session_state.get(SESSION_APPLY_RESULT_KEY)
    if not result:
        return

    message_type = result.get("message_type")
    message_text = result.get("message_text", "")
    if message_type == "success" and message_text:
        st.success(message_text)
        total_count = result.get("total_mapping_count")
        if total_count is not None:
            st.info(f"Total mappings in sector_mapping.csv: {total_count:,}")
    elif message_type == "warning" and message_text:
        st.warning(message_text)

    recent = result.get("recent_updates")
    if isinstance(recent, pd.DataFrame) and not recent.empty:
        st.subheader("Recently updated mappings")
        st.dataframe(recent, use_container_width=True, hide_index=True)

    with st.expander("Apply mapping debug", expanded=False):
        st.write(f"sector_mapping.csv path: `{result.get('mapping_path', '')}`")
        st.write(f"File exists: {result.get('file_exists')}")
        st.write(f"Selected sub_sector: {result.get('selected_sub_sector')}")
        st.write(f"Updated count: {result.get('updated_count', 0)}")
        st.write("Parsed stock IDs:")
        st.code("\n".join(result.get("parsed_stock_ids", [])) or "(none)")


def main() -> None:
    st.set_page_config(page_title="Sub-sector Mapping Admin", layout="wide")
    st.title("Sub-sector Mapping Admin")
    st.caption("Classify unmapped stocks into sector_mapping.csv for the dashboard.")

    _render_apply_result()

    mapping = load_sector_mapping()
    st.subheader("Current sector_mapping.csv")
    c1, c2, c3 = st.columns(3)
    c1.metric("Mapped stocks", f"{len(mapping):,}")
    c2.metric("File exists", "Yes" if SECTOR_MAPPING_PATH.exists() else "No")
    c3.metric("File", SECTOR_MAPPING_PATH.name)

    if mapping.empty:
        st.info("sector_mapping.csv is empty or missing. New mappings will create the file.")
    else:
        st.dataframe(mapping.head(50), use_container_width=True, hide_index=True)

    st.divider()

    unmapped = load_unmapped_review()
    if unmapped is None:
        st.error("No unmapped_review.csv found. Please run auto_sector_mapper.py first.")
        return

    st.subheader("Unmapped stocks")
    st.caption(f"Loaded {len(unmapped):,} rows from unmapped_review.csv")

    industry_options = ["All"]
    if "industry" in unmapped.columns:
        industry_options += sorted(
            unmapped["industry"].dropna().astype(str).unique().tolist()
        )

    f1, f2, f3 = st.columns(3)
    with f1:
        search = st.text_input("Search stock_id or stock_name", "")
    with f2:
        industry_filter = st.selectbox("Industry", industry_options)
    with f3:
        min_turnover = st.number_input(
            "Minimum turnover",
            min_value=0,
            value=0,
            step=1_000_000,
        )

    display_limit = st.number_input(
        "Rows to display",
        min_value=1,
        max_value=500,
        value=DEFAULT_DISPLAY_ROWS,
        step=10,
    )

    filtered = filter_unmapped(unmapped, search, industry_filter, min_turnover)
    st.write(f"Showing top {min(display_limit, len(filtered)):,} of {len(filtered):,} filtered rows")
    st.dataframe(
        filtered.head(int(display_limit)),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.subheader("Apply mapping")

    stock_ids_text = st.text_area(
        "Stock IDs to update",
        placeholder="Paste stock IDs separated by comma or newline\nExample:\n2330\n2454,3711",
        height=120,
        key="stock_ids_to_update",
    )
    selected_sub_sector = st.selectbox("Sub-sector", SUB_SECTOR_OPTIONS, key="selected_sub_sector")

    parsed_preview = parse_stock_ids(stock_ids_text)
    with st.expander("Input debug preview", expanded=False):
        st.write(f"Parsed stock IDs ({len(parsed_preview)}):")
        st.code("\n".join(parsed_preview) if parsed_preview else "(none)")
        st.write(f"Selected sub_sector: {selected_sub_sector}")
        st.write(f"sector_mapping.csv path: `{SECTOR_MAPPING_PATH}`")
        st.write(f"File exists: {SECTOR_MAPPING_PATH.exists()}")

    if st.button("Apply mapping", type="primary", key="apply_mapping_button"):
        debug_base = {
            "mapping_path": str(SECTOR_MAPPING_PATH),
            "file_exists": SECTOR_MAPPING_PATH.exists(),
            "selected_sub_sector": selected_sub_sector,
            "parsed_stock_ids": parsed_preview,
            "updated_count": 0,
            "recent_updates": pd.DataFrame(columns=["stock_id", "sub_sector"]),
        }

        if not stock_ids_text.strip():
            st.session_state[SESSION_APPLY_RESULT_KEY] = {
                **debug_base,
                "message_type": "warning",
                "message_text": "Please enter at least one stock ID.",
            }
            st.rerun()

        if not selected_sub_sector or not str(selected_sub_sector).strip():
            st.session_state[SESSION_APPLY_RESULT_KEY] = {
                **debug_base,
                "message_type": "warning",
                "message_text": "Please select a sub-sector.",
            }
            st.rerun()

        stock_ids = parse_stock_ids(stock_ids_text)
        debug_base["parsed_stock_ids"] = stock_ids

        if not stock_ids:
            st.session_state[SESSION_APPLY_RESULT_KEY] = {
                **debug_base,
                "message_type": "warning",
                "message_text": "No valid stock IDs found.",
            }
            st.rerun()

        try:
            recent_updates, updated_count = apply_mapping(stock_ids, selected_sub_sector)
            reloaded = load_sector_mapping()
            st.session_state[SESSION_APPLY_RESULT_KEY] = {
                **debug_base,
                "message_type": "success",
                "message_text": f"Updated {updated_count} mappings.",
                "updated_count": updated_count,
                "recent_updates": recent_updates,
                "total_mapping_count": len(reloaded),
                "file_exists": SECTOR_MAPPING_PATH.exists(),
            }
            st.rerun()
        except Exception as exc:
            st.session_state[SESSION_APPLY_RESULT_KEY] = {
                **debug_base,
                "message_type": "warning",
                "message_text": f"Failed to save sector_mapping.csv: {exc}",
            }
            st.rerun()


if __name__ == "__main__":
    main()
