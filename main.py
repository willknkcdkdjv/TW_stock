import sys
import os
import traceback

# 確保當前目錄在系統路徑中，以便正確載入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import twse_crawler
import parquet_to_csv

def main():
    print("==================================================")
    print("      啟動 TWSE 終極自動化數據管線 (Data Pipeline)   ")
    print("==================================================")
    
    try:
        # ---------------------------------------------------------
        # 階段 1：啟動每日深層爬蟲引擎 (Data Ingestion)
        # 本階段將讀取 mapping 設定，抓取並自動更新所有的 Parquet 壓縮檔
        # ---------------------------------------------------------
        print("\n>>> [階段 1] 啟動自動化每日爬蟲...")
        twse_crawler.main()
        
    except Exception as e:
        print(f"\n[嚴重異常] 爬蟲執行階段發生錯誤：{e}")
        traceback.print_exc()
        print("==> 為確保資料庫一致性，已主動攔截錯誤並停止後續的報表轉換程序。")
        return  # 安全機制：前面的失敗了，就不執行後面，防止舊資料或破圖資料被轉換

    try:    
        # ---------------------------------------------------------
        # 階段 2：轉譯人類觀盤降級報表 (Data Export)
        # 當前面機房禁區的 Parquet 更新成功後，才安全地進行 CSV 格式降級轉譯
        # ---------------------------------------------------------
        print("\n>>> [階段 2] 啟動 Parquet 轉 CSV 人類報表降級程序...")
        parquet_to_csv.convert_parquets_to_csv()
        
    except Exception as e:
        print(f"\n[異常] 報表轉換階段發生錯誤：{e}")
        traceback.print_exc()
        return

    print("\n==================================================")
    print("           ✨ 所有資料管線任務已順利完成 ✨            ")
    print("==================================================")

if __name__ == "__main__":
    main()
