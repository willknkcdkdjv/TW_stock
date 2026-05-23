import os
import pandas as pd
from pathlib import Path

# 補充說明給我自己看：這份程式碼是專門把"quant_data"裡面的東西，一模一樣翻譯成human_readable_data裡面的內容，沒有其他功能。

# 將路徑定義得乾淨俐落，完全分離機器回測(quant_data)與人類閱讀(human_readable_data)
INPUT_DIR = Path('./quant_data')
OUTPUT_DIR = Path('./human_readable_data')

def convert_parquets_to_csv():
    """
    掃描 quant_data 底下的所有 Parquet 檔案。
    並在 human_readable_data 底下建立對應的子資料夾與 .csv 檔案，
    供人類使用 Excel 等軟體檢視。
    """
    print(f"========== 開始 Parquet -> CSV 轉換程序 ==========")
    
    if not INPUT_DIR.exists():
        print(f"錯誤：找不到 '{INPUT_DIR}' 資料夾！請先執行 twse_crawler.py。")
        return
        
    # 掃描所有包含子資料夾的 .parquet 檔案 (例如 securities_trading/twse_daily_price.parquet)
    parquet_files = list(INPUT_DIR.rglob("*.parquet"))
    
    if not parquet_files:
        print("未在資料庫中找到任何 Parquet 檔案。")
        return
        
    print(f"總共找到 {len(parquet_files)} 個可轉換檔案。\n")
    
    for pq_file in parquet_files:
        # 計算相對路徑，保持原本的分類資料夾結構
        rel_path = pq_file.relative_to(INPUT_DIR)
        
        # 準備匯出的 csv 檔案路徑
        csv_rel_path = rel_path.with_suffix('.csv')
        out_file = OUTPUT_DIR / csv_rel_path
        
        # 確保外層資料夾 (例如 human_readable_data/securities_trading) 已被自動建立
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            print(f"正在轉換: {rel_path} ...")
            df = pd.read_parquet(pq_file)
            
            # --- [Excel 股票代碼防呆模組] ---
            # 找出所有的文字型態欄位，如果內容正好是「純數字」(例如 0050, 2330)
            # 為了避免被 Excel 自作聰明轉成整數並拔掉前導的 0，我們強制將其轉為 Excel 函數格式 (="0050")
            for col in df.columns:
                if df[col].dtype.name in ['object', 'string', 'category']:
                    # 使用正則表達式尋找全是數字組成的字串
                    mask = df[col].astype(str).str.match(r'^\d+$', na=False)
                    if mask.any():
                        # 將原本的 "0050" 變成 ="0050"
                        df.loc[mask, col] = '="' + df.loc[mask, col].astype(str) + '"'
            
            # 使用 utf-8-sig 存檔，這是為了確保 Windows 環境下用 Excel 打開「中文不亂碼」的核心技巧
            df.to_csv(out_file, index=False, encoding='utf-8-sig')
            
            print(f"  -> [成功] 該檔案已儲存至: {out_file}")
            
        except Exception as e:
            print(f"  -> [失敗] 轉換 {rel_path} 時發生錯誤: {e}")
            
    print(f"\n==================== 轉換完畢 ====================")
    print(f"請前往 '{OUTPUT_DIR}' 資料夾查看以 Excel 開啟之資料。")

if __name__ == "__main__":
    convert_parquets_to_csv()
