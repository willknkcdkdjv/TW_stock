"""
Generate sector_mapping_generated.csv and unmapped_review.csv for the dashboard.

Deterministic rule-based mapper (no LLM / external APIs).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_service import (
    BASE_DIR,
    QUANT_DIR,
    DEFAULT_SUB_SECTOR,
    clean_stock_id,
    map_industry_to_name,
    normalize_industry_code,
    read_parquet_safe,
)

OUTPUT_COLUMNS = [
    "stock_id",
    "stock_name",
    "industry",
    "sub_sector",
    "source",
    "confidence",
]

STOCK_DAY_CANDIDATES = [
    QUANT_DIR / "securities_trading" / "STOCK_DAY_ALL.parquet",
]
PROFILE_CANDIDATES = [
    QUANT_DIR / "corporate_governance" / "t187ap03_L.parquet",
]
MANUAL_MAPPING_PATH = BASE_DIR / "sector_mapping.csv"
GENERATED_PATH = BASE_DIR / "sector_mapping_generated.csv"
UNMAPPED_PATH = BASE_DIR / "unmapped_review.csv"

# (keywords in stock_name, sub_sector, confidence)
NAME_KEYWORD_RULES: list[tuple[list[str], str, str]] = [
    (["台積", "世界先進", "世界", "聯電", "力積", "茂矽", "漢磊", "元晶"], "晶圓代工", "high"),
    (["日月光", "矽品", "京元", "矽格", "頎邦", "南茂", "颀邦", "采鈺"], "封裝測試", "high"),
    (["國巨", "華新科", "禾伸堂", "信昌電", "凱美", "奇力新", "台庆", "台慶"], "MLCC", "high"),
    (["奇鋐", "雙鴻", "建準", "泰碩", "健策", "超眾", "超众"], "散熱", "high"),
    (["廣達", "緯創", "英業達", "仁寶", "和碩", "神達", "技嘉", "微星", "華擎"], "AI Server", "high"),
    (["鴻海", "富士康", "富智康", "雲智匯"], "伺服器代工", "high"),
    (["欣興", "景碩", "南電", "臻鼎", "華通", "健鼎", "金像電", "燿華", "定穎", "楠梓電"], "PCB", "high"),
    (["台光電", "聯茂", "騰輝", "台燿", "台耀", "明基材", "台燿-KY"], "CCL", "high"),
    (["台達電", "光寶", "群電", "康舒", "全漢", "明緯"], "電源供應器", "high"),
    (["中興電", "士電", "華城", "亞力", "大亞", "合機", "東元"], "重電", "high"),
    (["聯發科", "瑞昱", "聯詠", "創意", "世芯", "智原", "鈺創", "天鈺", "譜瑞"], "IC設計", "high"),
    (["華邦", "南亞科", "旺宏", "群聯", "威剛", "十銓", "宇瞻"], "記憶體", "medium"),
    (["應材", "科林", "科磊", "東京威力", "漢微", "帆宣", "京鼎", "辛耘", "弘塑", "萬潤"], "半導體設備材料", "medium"),
    (["正崴", "詮鼎", "鴻準", "佳世達", "和碩", "可成", "安克", "安克創"], "連接器", "medium"),
    (["研華", "樺漢", "新漢", "安勤", "融程", "友通", "威強電"], "IPC工業電腦", "medium"),
    (["宏碁", "和碩", "廣達", "仁寶", "緯創", "英業達", "華碩", "微星"], "NB/PC", "medium"),
    (["智邦", "明泰", "合勤", "中磊", "啟碁", "智易", "台灣大", "遠傳", "中華電"], "網通", "medium"),
    (["聯亞", "上詮", "光聖", "波若威", "聯鈞", "光通", "光環", "前鼎", "聯光"], "光通訊/CPO", "medium"),
    (["友達", "群創", "彩晶", "凌巨", "元太", "佳凌"], "面板", "medium"),
    (["億光", "光鋐", "光寶", "隆達", "晶電", "艾笛森", "一詮"], "LED", "medium"),
    (["特斯拉", "車", "鴻海", "裕隆", "和泰", "華域", "胡連", "為升", "車王", "德昌"], "電動車", "low"),
    (["車用", "德昌", "胡連", "為升", "車王電", "新日興", "奇鋐"], "車用電子", "medium"),
    (["台塑", "南亞", "台化", "奇美", "國喬", "台聚", "中石化", "三芳", "儒鴻"], "塑化", "medium"),
    (["中鋼", "豐興", "東和", "春雨", "中鴻", "第一銅", "中鋼構", "中鋼"], "鋼鐵", "medium"),
    (["台泥", "亞泥", "信大", "嘉泥", "環泥", "幸福", "東泥"], "水泥", "medium"),
    (["儒鴻", "聚陽", "宏碁", "儒鸿", "儒鴻企業", "儒鸿"], "紡織", "low"),
    (["長榮", "陽明", "萬海", "慧洋", "中航", "裕民", "台航"], "航運", "high"),
    (["富邦", "國泰", "中信", "兆豐", "玉山", "第一金", "合庫", "華南", "彰銀", "台新", "元大", "永豐", "開發金"], "金融", "medium"),
    (["長虹", "遠雄", "潤泰", "國建", "皇翔", "宏普", "華固", "興富", "冠德"], "建設營造", "medium"),
    (["統一", "味全", "黑松", "大成", "福壽", "聯華", "南僑", "德記", "佳格"], "食品", "medium"),
    (["台灣大車隊", "雄獅", "晶華", "寒舍", "王品", "瓦城", "美食-KY", "鳳凰", "晶華"], "觀光餐旅", "medium"),
    (["藥華", "台康", "浩泰", "中裕", "智擎", "美時", "生技", "藥", "醫"], "生技醫療", "low"),
    (["台塑化", "台塑", "南亞", "台化", "國喬", "台聚", "中石化"], "塑化", "medium"),
    (["風電", "太陽能", "綠能", "再生", "上曜", "元晶", "茂迪", "雲豹", "永鑫", "大世科"], "綠電/再生能源", "low"),
    (["被動", "電感", "電容", "晶片電阻", "達方", "九豪", "華容"], "被動元件", "medium"),
    (["EMS", "代工", "鴻海", "和碩", "廣達"], "伺服器代工", "low"),
]

# Known stock_id overrides from manual sector_mapping.csv patterns
STOCK_ID_RULES: dict[str, tuple[str, str]] = {
    "2330": ("晶圓代工", "high"),
    "2303": ("晶圓代工", "high"),
    "2454": ("IC設計", "high"),
    "2317": ("伺服器代工", "high"),
    "2382": ("AI Server", "high"),
    "3231": ("AI Server", "high"),
    "6669": ("AI Server", "high"),
}

# industry code -> (sub_sector, confidence)
INDUSTRY_CODE_RULES: dict[str, tuple[str, str]] = {
    "01": ("水泥", "medium"),
    "02": ("食品", "medium"),
    "03": ("塑化", "medium"),
    "04": ("紡織", "medium"),
    "10": ("鋼鐵", "medium"),
    "14": ("建設營造", "medium"),
    "15": ("航運", "medium"),
    "16": ("觀光餐旅", "medium"),
    "17": ("金融", "medium"),
    "21": ("塑化", "medium"),
    "22": ("生技醫療", "medium"),
    "24": ("其他電子", "low"),
    "25": ("NB/PC", "low"),
    "26": ("面板", "low"),
    "27": ("網通", "low"),
    "28": ("被動元件", "low"),
    "31": ("其他電子", "low"),
}

# industry Chinese name -> (sub_sector, confidence) fallback
INDUSTRY_NAME_RULES: dict[str, tuple[str, str]] = {
    "金融保險": ("金融", "medium"),
    "航運業": ("航運", "medium"),
    "建材營造": ("建設營造", "medium"),
    "食品工業": ("食品", "medium"),
    "生技醫療": ("生技醫療", "medium"),
    "觀光餐旅": ("觀光餐旅", "medium"),
    "鋼鐵工業": ("鋼鐵", "medium"),
    "塑膠工業": ("塑化", "medium"),
    "化學工業": ("塑化", "medium"),
    "紡織纖維": ("紡織", "medium"),
    "水泥工業": ("水泥", "medium"),
    "半導體業": ("其他電子", "low"),
    "電腦及週邊設備": ("NB/PC", "low"),
    "光電業": ("面板", "low"),
    "通信網路業": ("網通", "low"),
    "電子零組件": ("被動元件", "low"),
    "其他電子業": ("其他電子", "low"),
}


def _find_parquet(candidates: list[Path]) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    matches = []
    if candidates:
        pattern = candidates[0].name
        matches = list(QUANT_DIR.rglob(pattern))
    return matches[0] if matches else None


def _normalize_stock_id_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace('="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def load_manual_mapping() -> pd.DataFrame:
    if not MANUAL_MAPPING_PATH.exists():
        return pd.DataFrame(columns=["stock_id", "sub_sector"])

    df = pd.read_csv(MANUAL_MAPPING_PATH, dtype={"stock_id": str})
    if "stock_id" not in df.columns or "sub_sector" not in df.columns:
        return pd.DataFrame(columns=["stock_id", "sub_sector"])

    manual = df[["stock_id", "sub_sector"]].copy()
    manual["stock_id"] = _normalize_stock_id_series(manual["stock_id"])
    manual["sub_sector"] = manual["sub_sector"].astype(str).str.strip()
    manual = manual.dropna(subset=["stock_id"])
    manual = manual[manual["stock_id"] != ""]
    manual = manual[manual["sub_sector"] != ""]
    return manual.drop_duplicates(subset=["stock_id"], keep="last")


def load_latest_universe() -> pd.DataFrame:
    path = _find_parquet(STOCK_DAY_CANDIDATES)
    if path is None:
        raise FileNotFoundError("STOCK_DAY_ALL.parquet not found under quant_data/")

    df = read_parquet_safe(path)
    if df.empty:
        raise ValueError(f"{path.name} is empty")

    df = clean_stock_id(df)
    if "Date" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"Date": "date"})

    if "date" not in df.columns:
        raise ValueError("STOCK_DAY_ALL.parquet missing date column")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "stock_id"])

    for col in ("stock_name", "amount"):
        if col not in df.columns:
            df[col] = pd.NA
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    latest_date = df["date"].max()
    latest = df[df["date"] == latest_date].copy()
    latest = latest.sort_values("amount", ascending=False, na_position="last")
    latest = latest.drop_duplicates(subset=["stock_id"], keep="first")
    return latest[["stock_id", "stock_name", "amount"]].reset_index(drop=True)


def load_company_profile() -> pd.DataFrame:
    path = _find_parquet(PROFILE_CANDIDATES)
    if path is None:
        return pd.DataFrame(columns=["stock_id", "industry"])

    df = read_parquet_safe(path)
    if df.empty:
        return pd.DataFrame(columns=["stock_id", "industry"])

    df = clean_stock_id(df)
    stock_col = "stock_id" if "stock_id" in df.columns else "公司代號"
    industry_col = "industry" if "industry" in df.columns else "產業別"
    if stock_col not in df.columns or industry_col not in df.columns:
        return pd.DataFrame(columns=["stock_id", "industry"])

    profile = df[[stock_col, industry_col]].copy()
    profile = profile.rename(columns={stock_col: "stock_id", industry_col: "industry"})
    profile["stock_id"] = _normalize_stock_id_series(profile["stock_id"])
    profile["industry"] = profile["industry"].astype(str).str.strip()
    profile = profile.dropna(subset=["stock_id"])
    profile = profile[profile["stock_id"] != ""]
    return profile.drop_duplicates(subset=["stock_id"], keep="last")


def _match_name_keyword(stock_name: str) -> tuple[str, str, str] | None:
    if not stock_name or stock_name.lower() in {"nan", "none", "<na>"}:
        return None
    for keywords, sub_sector, confidence in NAME_KEYWORD_RULES:
        if any(kw in stock_name for kw in keywords):
            return sub_sector, "name_keyword", confidence
    return None


def _match_stock_id(stock_id: str) -> tuple[str, str, str] | None:
    rule = STOCK_ID_RULES.get(stock_id)
    if rule is None:
        return None
    sub_sector, confidence = rule
    return sub_sector, "stock_id_rule", confidence


def _match_industry(industry_raw: str, industry_name: str = "") -> tuple[str, str, str] | None:
    code = normalize_industry_code(industry_raw)
    if code and code in INDUSTRY_CODE_RULES:
        sub_sector, confidence = INDUSTRY_CODE_RULES[code]
        return sub_sector, "industry_code", confidence

    name = industry_name or map_industry_to_name(industry_raw)
    if name in INDUSTRY_NAME_RULES:
        sub_sector, confidence = INDUSTRY_NAME_RULES[name]
        return sub_sector, "industry_name", confidence

    if code == "24":
        return "其他電子", "industry_code", "low"
    return None


def apply_rule_mapping(row: pd.Series) -> tuple[str, str, str]:
    stock_id = str(row.get("stock_id", "")).strip()
    stock_name = str(row.get("stock_name", "")).strip()
    industry_code = str(row.get("industry_code", row.get("industry", ""))).strip()
    industry_name = str(row.get("industry_name", "")).strip()

    stock_match = _match_stock_id(stock_id)
    if stock_match:
        return stock_match

    name_match = _match_name_keyword(stock_name)
    if name_match:
        return name_match

    if "台積" in stock_name or (
        normalize_industry_code(industry_code) == "24" and "晶圓" in stock_name
    ):
        return "晶圓代工", "name_keyword", "high"

    industry_match = _match_industry(industry_code, industry_name)
    if industry_match:
        return industry_match

    return DEFAULT_SUB_SECTOR, "default", "low"


def build_sector_mapping() -> pd.DataFrame:
    universe = load_latest_universe()
    profile = load_company_profile()
    manual = load_manual_mapping()

    merged = universe.merge(profile.rename(columns={"industry": "industry_code"}), on="stock_id", how="left")
    merged["industry_name"] = merged["industry_code"].apply(map_industry_to_name)
    merged["industry"] = merged["industry_name"].where(
        merged["industry_name"].notna() & (merged["industry_name"] != "Unknown"),
        merged["industry_code"],
    )

    manual_lookup = manual.set_index("stock_id")["sub_sector"].to_dict() if not manual.empty else {}

    records: list[dict] = []
    for _, row in merged.iterrows():
        stock_id = str(row["stock_id"]).strip()
        stock_name = str(row.get("stock_name", "")).strip()

        if stock_id in manual_lookup:
            sub_sector = manual_lookup[stock_id]
            source = "manual_override"
            confidence = "high"
        else:
            sub_sector, source, confidence = apply_rule_mapping(row)

        industry_display = row.get("industry_name") or row.get("industry_code") or ""
        if pd.isna(industry_display) or str(industry_display) in {"", "Unknown", "nan"}:
            industry_display = map_industry_to_name(row.get("industry_code")) or ""

        records.append(
            {
                "stock_id": stock_id,
                "stock_name": stock_name,
                "industry": industry_display,
                "sub_sector": sub_sector,
                "source": source,
                "confidence": confidence,
            }
        )

    result = pd.DataFrame(records, columns=OUTPUT_COLUMNS)
    result = result.drop_duplicates(subset=["stock_id"], keep="last")
    return result.sort_values(["sub_sector", "stock_id"]).reset_index(drop=True)


def save_outputs(mapping: pd.DataFrame, universe: pd.DataFrame | None = None) -> None:
    mapping.to_csv(GENERATED_PATH, index=False, encoding="utf-8-sig")

    unmapped = mapping[mapping["sub_sector"] == DEFAULT_SUB_SECTOR].copy()
    if universe is not None and not universe.empty:
        unmapped = unmapped.merge(
            universe[["stock_id", "amount"]],
            on="stock_id",
            how="left",
        )
        unmapped = unmapped.sort_values("amount", ascending=False, na_position="last")
    else:
        unmapped = unmapped.sort_values("stock_id")

    review_cols = [c for c in OUTPUT_COLUMNS + ["amount"] if c in unmapped.columns]
    unmapped[review_cols].to_csv(UNMAPPED_PATH, index=False, encoding="utf-8-sig")


def main() -> None:
    print("Loading latest stock universe...")
    universe = load_latest_universe()
    print(f"  {len(universe):,} stocks on latest date")

    print("Building sector mapping...")
    mapping = build_sector_mapping()
    save_outputs(mapping, universe)

    mapped_count = int((mapping["sub_sector"] != DEFAULT_SUB_SECTOR).sum())
    manual_count = int((mapping["source"] == "manual_override").sum())
    unmapped_count = int((mapping["sub_sector"] == DEFAULT_SUB_SECTOR).sum())

    print(f"Wrote {GENERATED_PATH} ({len(mapping):,} rows)")
    print(f"Wrote {UNMAPPED_PATH} ({unmapped_count:,} rows)")
    print(f"  Mapped: {mapped_count:,} | Manual override: {manual_count:,} | 未分類: {unmapped_count:,}")


if __name__ == "__main__":
    main()
