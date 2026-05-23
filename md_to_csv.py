import pandas as pd
from pathlib import Path
import re

# 這份程式碼是專門把.md檔案轉換成csv檔案的，因為原本被製造出來的"mapping_table.md"
# 有點亂，所以轉換成人類可以對照的形式"mapping_table_excel.csv"。

MD_FILE = Path("mapping_table.md")
CSV_FILE = Path("mapping_table_excel.csv")

def convert_md_to_csv():
    print("========== 開始 Markdown 表格轉換程式 ==========")
    if not MD_FILE.exists():
        print(f"錯誤：找不到 '{MD_FILE}' 檔案！請確保它在同一個目錄下。")
        return
        
    with open(MD_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # 篩選出 Markdown 文件中含有 '|' 的表格字串行
    table_lines = [line.strip() for line in lines if '|' in line]
    
    if len(table_lines) < 3:
        print("未在檔案中找到有效格式的 Markdown 表格 (至少需包含表頭、分隔線與資料)。")
        return
        
    # 1. 萃取表頭 (Header)
    # 把第一行前後的 '|' 拿掉，並用 '|' 切割欄位名稱
    header_line = table_lines[0].strip('|')
    headers = [col.strip() for col in header_line.split('|')]
    
    # 2. 逐行萃取資料 (Data)
    data = []
    # 略過第二行 (因為第二行是 :--- 分隔線)，從第三行開始讀取
    for line in table_lines[2:]:
        # 把每一行前後的 '|' 拿掉，再切割
        clean_line = line.strip('|')
        # 移除裡面的 Markdown 語法 (例如 反引號 `)
        row = [col.strip().replace('`', '') for col in clean_line.split('|')]
        
        # 確認欄位數量一致才寫入
        if len(row) == len(headers):
            # 加入 Excel 專屬數字防呆：若全為數字，包裝成 ="1234"
            for i in range(len(row)):
                if re.match(r'^\d+$', row[i]):
                    row[i] = f'="{row[i]}"'
            data.append(row)
            
    # 3. 轉存成 Dataframe 並輸出 CSV (加上 utf-8-sig 確保 Excel 中文正常)
    df = pd.DataFrame(data, columns=headers)
    df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
    
    print(f"成功轉換 {len(df)} 筆對照資料表！")
    print(f"請使用 Excel 開啟並檢閱: '{CSV_FILE}'")

if __name__ == "__main__":
    convert_md_to_csv()
