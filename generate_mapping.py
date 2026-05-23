import requests
import pandas as pd
import json

# 此檔案會產生出twse_api_links.csv 跟 mapping_table.md

tag_mapping = {
    "公司治理": "corporate_governance",
    "證券交易": "securities_trading",
    "財務報表": "financial_statements",
    "指數": "indices",
    "權證": "warrants",
    "其他": "others",
    "券商資料": "broker_data"
}

def generate_reports():
    try:
        print("Fetching OpenAPI Swagger JSON...")
        resp = requests.get("https://openapi.twse.com.tw/v1/swagger.json", timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # =========== 產生 Markdown 對照表 ===========
        markdown = "## 📚 TWSE OpenAPI 中英文對照與端點總表 (全 70+ 項目)\n"
        markdown += "以下為依據您要求，將證交所網站完整目錄之「中文分類與資料名稱」，完美對應至本地端「英文資料夾與檔名」的對照表：\n\n"
        markdown += "| 網站分類 | 本地資料夾 (Folder) | 網站資料名稱 (Chinese) | 本地檔名 (File) | 對應的 OpenAPI 網址 |\n"
        markdown += "| :--- | :--- | :--- | :--- | :--- |\n"

        # =========== 準備產出 CSV 的字典資料 ===========
        # 建立一個 dictionary 裝載各分類底下的所有連結，確保具備表頭
        category_links = {en_name: [] for en_name in tag_mapping.values()}

        for path, methods in data['paths'].items():
            if 'get' in methods:
                info = methods['get']
                tag_zh = info['tags'][0] if info.get('tags') else "其他"
                tag_en = tag_mapping.get(tag_zh, "others")
                summary = info.get('summary', '').replace('\n', '').strip()
                
                file_name = path.strip('/').split('/')[-1]
                if not file_name: file_name = "data"
                
                full_url = f"https://openapi.twse.com.tw/v1{path}"
                
                # 更新 Markdown 文字
                markdown += f"| {tag_zh} | `{tag_en}` | {summary} | `{file_name}` | `{full_url}` |\n"
                
                # 放入對應類別的陣列中 (準備寫入 CSV)
                if tag_en not in category_links:
                    category_links[tag_en] = []
                category_links[tag_en].append(full_url)

        # 輸出 Markdown 到檔案
        md_file = r'c:\Users\Kuan Yu\Desktop\Antigravity_tw\mapping_table.md'
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(markdown)
        print(f"[Done] Mapping Markdown generated at {md_file}")

        # =========== 處理並輸出 CSV ===========
        # 因為每個分類的連結數量不同 (有的十幾個，有的只有三四個)
        # 我們必須找出最多連結數的分類，並用空字串 ('') 填補其他數量較少的分類
        # 這樣才能構造出欄列整齊完美的 DataFrame
        max_len = max(len(links) for links in category_links.values())
        
        for category in category_links:
            category_links[category] += [''] * (max_len - len(category_links[category]))
            
        df = pd.DataFrame(category_links)
        
        # 輸出成 CSV 檔案 (每個儲存格只會有一個 Link)
        csv_file = r'c:\Users\Kuan Yu\Desktop\Antigravity_tw\twse_api_links.csv'
        # 使用 utf-8-sig 讓使用者直接打開 Excel 不會顯示亂碼
        df.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        print(f"[Done] CSV generated at {csv_file}")
        print("所有轉換已成功完成！")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_reports()
