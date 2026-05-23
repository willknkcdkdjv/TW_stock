import os
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

# 建立儲存資料的根目錄 (Data Lake)
DATA_DIR = Path("./quant_data")

def load_endpoints_from_csv() -> dict:
    """從 twse_api_links.csv 動態讀取所有的 API Endpoints"""
    csv_file = Path('./twse_api_links.csv')
    if not csv_file.exists():
        print(f"錯誤：找不到 '{csv_file}'。")
        return {}
        
    df = pd.read_csv(csv_file)
    api_dict = {}
    
    for category in df.columns:
        # 過濾空字串與 NaN
        valid_links = df[category].dropna()
        valid_links = valid_links[valid_links != ""]
        
        if not valid_links.empty:
            api_dict[category] = {}
            for url in valid_links:
                # 使用網址的最後一小段當作存檔的 Parquet 檔名
                dataset_name = url.strip('/').split('/')[-1]
                api_dict[category][dataset_name] = url
                
    return api_dict

def fetch_twse_data(endpoint_url: str) -> pd.DataFrame:
    """透過 Swagger Json 上的單一 Endpoint 下載資料"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    for attempt in range(3):
        try:
            print(f"  -> Requesting: {endpoint_url} ...")
            response = requests.get(endpoint_url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not data: return pd.DataFrame()
            return pd.DataFrame(data)
        except Exception as e:
            print(f"  Fetch failed (Attempt {attempt+1}/3): {e}")
            time.sleep(3)
    return pd.DataFrame()

def process_price_data(df: pd.DataFrame) -> pd.DataFrame:
    """清理與標準化價量資料"""
    if df.empty: return df
    rename_map = {
        'Code': 'stock_id', 'Name': 'stock_name', 'TradeVolume': 'volume', 
        'TradeValue': 'amount', 'OpeningPrice': 'open', 'HighestPrice': 'high',
        'LowestPrice': 'low', 'ClosingPrice': 'close', 'Change': 'change', 'Transaction': 'transactions'
    }
    df = df.rename(columns=rename_map)
    df['date'] = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
    for col in ['volume', 'amount', 'open', 'high', 'low', 'close', 'change', 'transactions']:
        if col in df.columns: df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    if 'stock_id' in df.columns: df = df[df['stock_id'].str.len() <= 4]
    return df

def process_valuation_data(df: pd.DataFrame) -> pd.DataFrame:
    """清理本益比、殖利率等 Valuation 資料"""
    if df.empty: return df
    rename_map = {'Code': 'stock_id', 'Name': 'stock_name', 'PEratio': 'pe', 'DividendYield': 'div_yield', 'PBratio': 'pb'}
    df = df.rename(columns=rename_map)
    df['date'] = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
    for col in ['pe', 'div_yield', 'pb']:
        if col in df.columns: df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    if 'stock_id' in df.columns: df = df[df['stock_id'].str.len() <= 4]
    return df

def update_historical_data(category: str, dataset_name: str, new_df: pd.DataFrame):
    """
    將資料存入以「分類名稱」建立的子資料夾中
    """
    if new_df.empty: return
    
    category_dir = DATA_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    file_path = category_dir / f"{dataset_name}.parquet"
    
    # 去重並 Append 資料
    if file_path.exists():
        historical_df = pd.read_parquet(file_path)
        if 'date' in historical_df.columns and 'stock_id' in historical_df.columns:
            historical_df = historical_df[~((historical_df['date'] == new_df['date'].iloc[0]) & 
                                            (historical_df['stock_id'].isin(new_df['stock_id'])))]
        final_df = pd.concat([historical_df, new_df], ignore_index=True)
    else:
        final_df = new_df
        
    if 'date' in final_df.columns and 'stock_id' in final_df.columns:
        final_df = final_df.sort_values(by=['date', 'stock_id']).reset_index(drop=True)
    
    final_df.to_parquet(file_path, compression='zstd')
    print(f"  [Saved] -> {file_path} (Rows: {len(final_df)})")

def main():
    print(f"========== Start TWSE Data Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==========")
    
    # 完全由 CSV 動態驅動 (Config-driven)
    api_endpoints = load_endpoints_from_csv()
    if not api_endpoints:
        return
        
    for category, endpoints in api_endpoints.items():
        print(f"\n--- Processing Category: [{category}] ---")
        for dataset_name, url in endpoints.items():
            raw_df = fetch_twse_data(url)
            
            # 特殊資料清理判斷 (以網址最後一階層作為判斷標的)
            if "STOCK_DAY_ALL" in dataset_name:
                clean_df = process_price_data(raw_df)
            elif "BWIBBU_ALL" in dataset_name:
                clean_df = process_valuation_data(raw_df)
            else:
                clean_df = raw_df
                # 如果該資料來源沒有加上時間，為了儲存格式統一，自動補上當日時間戳
                if not clean_df.empty and 'date' not in clean_df.columns:
                    clean_df['date'] = pd.to_datetime(datetime.now().strftime("%Y-%m-%d"))
                    
            update_historical_data(category, dataset_name, clean_df)
            time.sleep(2) # Api 限流緩衝 (超重要，避免抓 70 支 API 時被鎖 IP)
            
    print(f"\n========== Update Finished ==========")

if __name__ == "__main__":
    main()
