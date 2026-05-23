# TWSE Quant Data Engineering 證交所量化資料工程專案

## 🚀 專案最新進度 (Project Status)
*這裡將持續更新我們一同打造的 HFT/Quant 級資料庫進度：*
- **[2026-03]** 成功建立 `twse_crawler.py`，支援自動建立**「雙層分類資料夾 (Category)」**。
- **[2026-03]** 底層儲存全面轉向 **Parquet + ZSTD** 格式，具備零轉換成本與去重更新 (Idempotent) 功能。
- **[2026-03]** 新增 `parquet_to_csv.py`。將「機器回測資料」與「人類閱讀報表」物理隔絕，並新增 Excel 專利字串防呆設計 (`="0050"`)。
- **[2026-03]** 新增 `generate_mapping.py`，完美實現「Config-driven（設定驅動）」，將 70+ 端點轉成 CSV 提供爬蟲無限擴充。
- **[2026-03]** 整理並匯入 70+ TWSE OpenAPI 藍圖，將所有 API 知識庫建檔完畢。
- *(持續擴充中...)*

---

## 📂 專案核心架構與檔案功能 (Architecture & Files)
本項目捨棄了混亂單一的架構，採用三支高度解耦的核心 Python 腳本構築而成，分別處理「藍圖配置」、「資料擷取」、「轉譯報表」三大任務。請其他開發者依照以下邏輯理解系統架構：

### 第一部：架構定義引擎 (`generate_mapping.py`)
*   **功能定位**：本專案的「大腦藍圖」。負責直接連線至證交所底層系統 (Swagger JSON) 掃描所有的隱藏 API 節點，並將生硬的中文轉換為標準英文系統路徑。
*   **產出結果**：它會產生 `twse_api_links.csv`，將 70 幾項資料分為公司治理 (`corporate_governance`)、證券交易 (`securities_trading`) 等七大純正英文目錄。**這份 CSV 是整個系統的唯一設定檔 (Config)**。

### 第二部：全自動核心爬蟲 (`twse_crawler.py`)
*   **功能定位**：機房裡的「引擎」。這是一隻純設定驅動的聰明爬蟲，它會自己去讀取上述生成的 `twse_api_links.csv` 裡的網址挨個下載。內建防阻擋緩衝與去重機制的保護。
*   **產出結果**：抓下來的所有資料將壓縮為 **Parquet + ZSTD** 極速回測格式。封裝於 `quant_data/` 雙層資料夾，**這是極度純淨、專供機器跑演算法的禁止人類手動修改區。**

### 第三部：人類閱讀報表引擎 (`parquet_to_csv.py`)
*   **功能定位**：貼心的「專屬翻譯官」。為防範在開啟 CSV 檔時，因為人工手滑等原因損壞到機器模型使用的 `quant_data`；這支腳本採用降級拷貝策略。
*   **防呆設計**：內建 `utf-8-sig` (防中文亂碼) 與 `="0050"` 函數欺騙機制 (防止 Excel 自動吃掉 0050 前面的 0 並轉為數字)。
*   **產出結果**：將資料庫檔案完美降級並備份於 `human_readable_data/` 這個「人類專區」。任何人都可以放心地在此用 Excel 開啟資料並分析。

---

## ⚙️ 專案四步驟：終極自動化執行順序 (Execution Pipeline)
為確保數據流水線順暢且無誤，本專案已完全模組化。請必定**按照以下由上至下的順序**啟動腳本：

### 第 1 步：定義核心藍圖 (Setup & Config)
*(用途：抓取證交所 70 支隱藏 API，並翻譯成對照表，產出爬蟲設定檔供後續存取)*
```bash
python generate_mapping.py
```

### 第 2 步：輸出對照表給人類查閱 (Export Map to Excel)
*(用途：將第一步產生的 `mapping_table.md`，無損轉成 `mapping_table_excel.csv` 格式。讓你隨時可以用 Excel 開啟對譯字典而不亂碼)*
```bash
python md_to_csv.py
```

### 第 3 步：每日全自動深層爬蟲引擎 (Data Ingestion)
*(用途：這是**專案的心臟**。核心爬蟲會讀取第一步建立好的藍圖，自動開始分門別類向證交所發送 70 支微服務的請求。所有抓到的資料，均將自動疊加並存入嚴禁人類手動編輯的 **機房禁區 `quant_data/`** 之中)*
```bash
python twse_crawler.py
```

### 第 4 步：人類觀盤降級報表轉換 (Data Export)
*(用途：當你每天下班後想用 Excel 看看今天的資料，只需一鍵觸發此腳本。系統會自動前往機房禁區，把所有 Parquet 檔案完美複製、轉譯為防呆的 CSV，並放置在 `human_readable_data/` 這個獨立的展示台上供你觀測)*
```bash
python parquet_to_csv.py
```

---

## 📚 TWSE OpenAPI 中英文對照與端點總表 (全 70+ 項目)
以下為依據您要求，將證交所網站完整目錄之「中文分類與資料名稱」，完美對應至本地端「英文資料夾與檔名」的對照表：

| 網站分類 | 本地資料夾 (Folder) | 網站資料名稱 (Chinese) | 本地檔名 (File) | 對應的 OpenAPI 網址 |
| :--- | :--- | :--- | :--- | :--- |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-職業安全衛生 | `t187ap46_L_21` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_21` |
| 公司治理 | `corporate_governance` | 上市公司股利分派情形 | `t187ap45_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap45_L` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-反競爭行為法律訴訟 | `t187ap46_L_20` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_20` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-風險管理政策 | `t187ap46_L_19` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_19` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-持股及控制力 | `t187ap46_L_18` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_18` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-普惠金融 | `t187ap46_L_17` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_17` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-資訊安全 | `t187ap46_L_16` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_16` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-社區關係 | `t187ap46_L_15` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_15` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-產品品質與安全 | `t187ap46_L_14` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_14` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-供應鏈管理 | `t187ap46_L_13` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_13` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-食品安全 | `t187ap46_L_12` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_12` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-產品生命週期 | `t187ap46_L_11` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_11` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-燃料管理 | `t187ap46_L_10` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_10` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-功能性委員會 | `t187ap46_L_9` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_9` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-氣候相關議題管理 | `t187ap46_L_8` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_8` |
| 其他 | `others` | 基金基本資料彙總表 | `t187ap47_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap47_L` |
| 公司治理 | `corporate_governance` | 公開發行公司每月營業收入彙總表 | `t187ap05_P` | `https://openapi.twse.com.tw/v1/opendata/t187ap05_P` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-投資人溝通 | `t187ap46_L_7` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_7` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-董事會 | `t187ap46_L_6` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_6` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-人力發展 | `t187ap46_L_5` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_5` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-廢棄物管理 | `t187ap46_L_4` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_4` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-水資源管理 | `t187ap46_L_3` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_3` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-能源管理 | `t187ap46_L_2` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_2` |
| 公司治理 | `corporate_governance` | 上市公司企業ESG資訊揭露彙總資料-溫室氣體排放 | `t187ap46_L_1` | `https://openapi.twse.com.tw/v1/opendata/t187ap46_L_1` |
| 券商資料 | `broker_data` | 定期定額交易戶數統計排行月報表 | `ETFRank` | `https://openapi.twse.com.tw/v1/ETFReport/ETFRank` |
| 券商資料 | `broker_data` | 開辦定期定額業務證券商名單 | `secRegData` | `https://openapi.twse.com.tw/v1/brokerService/secRegData` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-一般業 | `t187ap07_X_ci` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_ci` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-異業 | `t187ap07_X_mim` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_mim` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-金融業 | `t187ap06_X_basi` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_basi` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-證券期貨業 | `t187ap06_X_bd` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_bd` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-一般業 | `t187ap06_X_ci` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_ci` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-金控業 | `t187ap06_X_fh` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_fh` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-保險業 | `t187ap06_X_ins` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_ins` |
| 財務報表 | `financial_statements` | 公發公司綜合損益表-異業 | `t187ap06_X_mim` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_X_mim` |
| 其他 | `others` | 證交所活動訊息 | `eventList` | `https://openapi.twse.com.tw/v1/news/eventList` |
| 公司治理 | `corporate_governance` | 外國公司向證交所申請第一上市之公司 | `applylistingForeign` | `https://openapi.twse.com.tw/v1/company/applylistingForeign` |
| 公司治理 | `corporate_governance` | 最近上市公司 | `newlisting` | `https://openapi.twse.com.tw/v1/company/newlisting` |
| 公司治理 | `corporate_governance` | 終止上市公司 | `suspendListingCsvAndHtml` | `https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml` |
| 券商資料 | `broker_data` | 證券商總公司基本資料 | `brokerList` | `https://openapi.twse.com.tw/v1/brokerService/brokerList` |
| 其他 | `others` | 證交所新聞 | `newsList` | `https://openapi.twse.com.tw/v1/news/newsList` |
| 證券交易 | `securities_trading` | 上市個股日本益比、殖利率及股價淨值比（依代碼查詢） | `BWIBBU_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL` |
| 證券交易 | `securities_trading` | 上市個股日收盤價及月平均價 | `STOCK_DAY_AVG_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL` |
| 證券交易 | `securities_trading` | 上市個股日成交資訊 | `STOCK_DAY_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` |
| 證券交易 | `securities_trading` | 上市個股月成交資訊 | `FMSRFK_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/FMSRFK_ALL` |
| 證券交易 | `securities_trading` | 上市個股年成交資訊 | `FMNPTK_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/FMNPTK_ALL` |
| 證券交易 | `securities_trading` | 每日收盤行情-大盤統計資訊 | `MI_INDEX` | `https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX` |
| 公司治理 | `corporate_governance` | 申請上市之本國公司 | `applylistingLocal` | `https://openapi.twse.com.tw/v1/company/applylistingLocal` |
| 證券交易 | `securities_trading` | 集中市場外資及陸資投資類股持股比率表 | `MI_QFIIS_cat` | `https://openapi.twse.com.tw/v1/fund/MI_QFIIS_cat` |
| 證券交易 | `securities_trading` | 集中市場外資及陸資持股前 20 名彙總表 | `MI_QFIIS_sort_20` | `https://openapi.twse.com.tw/v1/fund/MI_QFIIS_sort_20` |
| 其他 | `others` | 中央登錄公債補息資料表 | `BFI61U` | `https://openapi.twse.com.tw/v1/exchangeReport/BFI61U` |
| 證券交易 | `securities_trading` | 上市個股首五日無漲跌幅 | `TWT88U` | `https://openapi.twse.com.tw/v1/exchangeReport/TWT88U` |
| 證券交易 | `securities_trading` | 投資理財節目異常推介個股 | `BFZFZU_T` | `https://openapi.twse.com.tw/v1/Announcement/BFZFZU_T` |
| 證券交易 | `securities_trading` | 上市股票每日當日沖銷交易標的及統計 | `TWTB4U` | `https://openapi.twse.com.tw/v1/exchangeReport/TWTB4U` |
| 證券交易 | `securities_trading` | 集中市場暫停先賣後買當日沖銷交易標的預告表 | `TWTBAU1` | `https://openapi.twse.com.tw/v1/exchangeReport/TWTBAU1` |
| 證券交易 | `securities_trading` | 集中市場暫停先賣後買當日沖銷交易歷史查詢 | `TWTBAU2` | `https://openapi.twse.com.tw/v1/exchangeReport/TWTBAU2` |
| 指數 | `indices` | 每日上市上櫃跨市場成交資訊 | `MI_INDEX4` | `https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX4` |
| 指數 | `indices` | 寶島股價指數歷史資料 | `FRMSA` | `https://openapi.twse.com.tw/v1/indicesReport/FRMSA` |
| 指數 | `indices` | 臺灣 50 指數歷史資料 | `TAI50I` | `https://openapi.twse.com.tw/v1/indicesReport/TAI50I` |
| 證券交易 | `securities_trading` | 每 5 秒委託成交統計 | `MI_5MINS` | `https://openapi.twse.com.tw/v1/exchangeReport/MI_5MINS` |
| 證券交易 | `securities_trading` | 集中市場每日市場成交資訊 | `FMTQIK` | `https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK` |
| 證券交易 | `securities_trading` | 集中市場每日成交量前二十名證券 | `MI_INDEX20` | `https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX20` |
| 證券交易 | `securities_trading` | 集中市場零股交易行情單 | `TWT53U` | `https://openapi.twse.com.tw/v1/exchangeReport/TWT53U` |
| 證券交易 | `securities_trading` | 集中市場暫停交易證券 | `TWTAWU` | `https://openapi.twse.com.tw/v1/exchangeReport/TWTAWU` |
| 證券交易 | `securities_trading` | 集中市場盤後定價交易 | `BFT41U` | `https://openapi.twse.com.tw/v1/exchangeReport/BFT41U` |
| 證券交易 | `securities_trading` | 集中市場停資停券預告表 | `BFI84U` | `https://openapi.twse.com.tw/v1/exchangeReport/BFI84U` |
| 證券交易 | `securities_trading` | 集中市場融資融券餘額 | `MI_MARGN` | `https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN` |
| 指數 | `indices` | 發行量加權股價指數歷史資料 | `MI_5MINS_HIST` | `https://openapi.twse.com.tw/v1/indicesReport/MI_5MINS_HIST` |
| 證券交易 | `securities_trading` | 集中市場鉅額交易日成交量值統計 | `BFIAUU_d` | `https://openapi.twse.com.tw/v1/block/BFIAUU_d` |
| 證券交易 | `securities_trading` | 集中市場鉅額交易月成交量值統計 | `BFIAUU_m` | `https://openapi.twse.com.tw/v1/block/BFIAUU_m` |
| 證券交易 | `securities_trading` | 集中市場鉅額交易年成交量值統計 | `BFIAUU_y` | `https://openapi.twse.com.tw/v1/block/BFIAUU_y` |
| 證券交易 | `securities_trading` | 每日第一上市外國股票成交量值 | `STOCK_FIRST` | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_FIRST` |
| 證券交易 | `securities_trading` | 集中市場證券變更交易 | `TWT85U` | `https://openapi.twse.com.tw/v1/exchangeReport/TWT85U` |
| 證券交易 | `securities_trading` | 有價證券集中交易市場開（休）市日期 | `holidaySchedule` | `https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule` |
| 證券交易 | `securities_trading` | 上市個股日本益比、殖利率及股價淨值比（依日期查詢） | `BWIBBU_d` | `https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d` |
| 指數 | `indices` | 發行量加權股價報酬指數 | `MFI94U` | `https://openapi.twse.com.tw/v1/indicesReport/MFI94U` |
| 證券交易 | `securities_trading` | 上市上櫃股票當日可借券賣出股數 | `TWT96U` | `https://openapi.twse.com.tw/v1/SBL/TWT96U` |
| 證券交易 | `securities_trading` | 上市個股股價升降幅度 | `TWT84U` | `https://openapi.twse.com.tw/v1/exchangeReport/TWT84U` |
| 證券交易 | `securities_trading` | 集中市場漲跌證券數統計表 | `twtazu_od` | `https://openapi.twse.com.tw/v1/opendata/twtazu_od` |
| 公司治理 | `corporate_governance` | 上市公司每日重大訊息 | `t187ap04_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap04_L` |
| 公司治理 | `corporate_governance` | 上市公司基本資料 | `t187ap03_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap03_L` |
| 財務報表 | `financial_statements` | 上市公司每月營業收入彙總表 | `t187ap05_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` |
| 券商資料 | `broker_data` | 券商業務別人員數 | `t187ap01` | `https://openapi.twse.com.tw/v1/opendata/t187ap01` |
| 公司治理 | `corporate_governance` | 上市公司持股逾 10% 大股東名單 | `t187ap02_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap02_L` |
| 公司治理 | `corporate_governance` | 上市公司各產業EPS統計資訊 | `t187ap14_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap14_L` |
| 財務報表 | `financial_statements` | 上市公司截至各季綜合損益財測達成情形(簡式) | `t187ap15_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap15_L` |
| 財務報表 | `financial_statements` | 上市公司當季綜合損益經會計師查核(核閱)數與當季預測數差異達百分之十以上者，或截至當季累計差異達百分之二十以上者(簡式) | `t187ap16_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap16_L` |
| 財務報表 | `financial_statements` | 上市公司營益分析查詢彙總表(全體公司彙總報表) | `t187ap17_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap17_L` |
| 券商資料 | `broker_data` | 各券商每月月計表 | `t187ap20` | `https://openapi.twse.com.tw/v1/opendata/t187ap20` |
| 券商資料 | `broker_data` | 各券商收支概況表資料 | `t187ap21` | `https://openapi.twse.com.tw/v1/opendata/t187ap21` |
| 券商資料 | `broker_data` | 證券商基本資料 | `t187ap18` | `https://openapi.twse.com.tw/v1/opendata/t187ap18` |
| 證券交易 | `securities_trading` | 電子式交易統計資訊 | `t187ap19` | `https://openapi.twse.com.tw/v1/opendata/t187ap19` |
| 公司治理 | `corporate_governance` | 上市公司董事、監察人持股不足法定成數彙總表 | `t187ap08_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap08_L` |
| 公司治理 | `corporate_governance` | 上市公司董監事持股餘額明細資料 | `t187ap11_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap11_L` |
| 公司治理 | `corporate_governance` | 上市公司每日內部人持股轉讓事前申報表-持股轉讓日報表 | `t187ap12_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap12_L` |
| 公司治理 | `corporate_governance` | 上市公司每日內部人持股轉讓事前申報表-持股未轉讓日報表 | `t187ap13_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap13_L` |
| 公司治理 | `corporate_governance` | 上市公司金管會證券期貨局裁罰案件專區 | `t187ap22_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap22_L` |
| 公司治理 | `corporate_governance` | 上市公司獨立董監事兼任情形彙總表 | `t187ap30_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap30_L` |
| 公司治理 | `corporate_governance` | 上市公司董事酬金相關資訊 | `t187ap29_A_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap29_A_L` |
| 公司治理 | `corporate_governance` | 上市公司監察人酬金相關資訊 | `t187ap29_B_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap29_B_L` |
| 公司治理 | `corporate_governance` | 上市公司合併報表董事酬金相關資訊 | `t187ap29_C_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap29_C_L` |
| 公司治理 | `corporate_governance` | 上市公司合併報表監察人酬金相關資訊 | `t187ap29_D_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap29_D_L` |
| 公司治理 | `corporate_governance` | 上市公司違反資訊申報、重大訊息及說明記者會規定專區 | `t187ap23_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap23_L` |
| 財務報表 | `financial_statements` | 上市公司財務報告經監察人承認情形 | `t187ap31_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap31_L` |
| 權證 | `warrants` | 上市認購(售)權證年度發行量概況統計表 | `t187ap36_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap36_L` |
| 公司治理 | `corporate_governance` | 公開發行公司基本資料 | `t187ap03_P` | `https://openapi.twse.com.tw/v1/opendata/t187ap03_P` |
| 權證 | `warrants` | 上市認購(售)權證交易人數檔 | `t187ap43_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap43_L` |
| 權證 | `warrants` | 上市認購(售)權證每日成交資料檔 | `t187ap42_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap42_L` |
| 公司治理 | `corporate_governance` | 集中市場公布處置股票 | `punish` | `https://openapi.twse.com.tw/v1/announcement/punish` |
| 公司治理 | `corporate_governance` | 上市公司董事、監察人持股不足法定成數連續達3個月以上彙總表 | `t187ap10_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap10_L` |
| 公司治理 | `corporate_governance` | 上市公司股東會公告-召集股東常(臨時)會公告資料彙總表(95年度起適用) | `t187ap38_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap38_L` |
| 公司治理 | `corporate_governance` | 上市公司經營權及營業範圍異(變)動專區-經營權異動公司 | `t187ap24_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap24_L` |
| 證券交易 | `securities_trading` | 上市權證基本資料彙總表 | `t187ap37_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap37_L` |
| 公司治理 | `corporate_governance` | 上市公司經營權及營業範圍異(變)動專區-經營權異動且營業範圍重大變更停止買賣公司 | `t187ap26_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap26_L` |
| 公司治理 | `corporate_governance` | 上市公司召開股東常 (臨時) 會日期、地點及採用電子投票情形等資料彙總表 | `t187ap41_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap41_L` |
| 證券交易 | `securities_trading` | 集中市場公布注意累計次數異常資訊 | `notetrans` | `https://openapi.twse.com.tw/v1/announcement/notetrans` |
| 證券交易 | `securities_trading` | 集中市場當日公布注意股票 | `notice` | `https://openapi.twse.com.tw/v1/announcement/notice` |
| 公司治理 | `corporate_governance` | 上市公司經營權及營業範圍異(變)動專區-營業範圍重大變更公司 | `t187ap25_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap25_L` |
| 公司治理 | `corporate_governance` | 上市公司經營權及營業範圍異(變)動專區-經營權異動且營業範圍重大變更列為變更交易公司 | `t187ap27_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap27_L` |
| 公司治理 | `corporate_governance` | 上市公司公司治理之相關規程規則 | `t187ap32_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap32_L` |
| 公司治理 | `corporate_governance` | 上市公司董事長是否兼任總經理 | `t187ap33_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap33_L` |
| 公司治理 | `corporate_governance` | 上市公司董事、監察人質權設定占董事及監察人實際持有股數彙總表 | `t187ap09_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap09_L` |
| 券商資料 | `broker_data` | 證券商營業員男女人數統計資料 | `OpenData_BRK01` | `https://openapi.twse.com.tw/v1/opendata/OpenData_BRK01` |
| 券商資料 | `broker_data` | 證券商分公司基本資料 | `OpenData_BRK02` | `https://openapi.twse.com.tw/v1/opendata/OpenData_BRK02` |
| 公司治理 | `corporate_governance` | 上市公司採累積投票制、全額連記法、候選人提名制選任董監事及當選資料彙總表 | `t187ap34_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap34_L` |
| 公司治理 | `corporate_governance` | 上市公司股東行使提案權情形彙總表 | `t187ap35_L` | `https://openapi.twse.com.tw/v1/opendata/t187ap35_L` |
| 證券交易 | `securities_trading` | 上市股票除權除息預告表 | `TWT48U_ALL` | `https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(證券期貨業) | `t187ap06_L_bd` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_bd` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(一般業) | `t187ap06_L_ci` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(金控業) | `t187ap06_L_fh` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_fh` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(保險業) | `t187ap06_L_ins` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ins` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(異業) | `t187ap06_L_mim` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_mim` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(證券期貨業) | `t187ap07_L_bd` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_bd` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(一般業) | `t187ap07_L_ci` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ci` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(金控業) | `t187ap07_L_fh` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_fh` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(保險業) | `t187ap07_L_ins` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_ins` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(異業) | `t187ap07_L_mim` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_mim` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-金融業 | `t187ap07_X_basi` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_basi` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-證券期貨業 | `t187ap07_X_bd` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_bd` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-金控業 | `t187ap07_X_fh` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_fh` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-保險業 | `t187ap07_X_ins` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_ins` |
| 財務報表 | `financial_statements` | 公發公司資產負債表-異業 | `t187ap07_X_mim` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_X_mim` |
| 財務報表 | `financial_statements` | 公發公司董監事持股餘額明細 | `t187ap11_P` | `https://openapi.twse.com.tw/v1/opendata/t187ap11_P` |
| 財務報表 | `financial_statements` | 上市公司綜合損益表(金融業) | `t187ap06_L_basi` | `https://openapi.twse.com.tw/v1/opendata/t187ap06_L_basi` |
| 財務報表 | `financial_statements` | 上市公司資產負債表(金融業) | `t187ap07_L_basi` | `https://openapi.twse.com.tw/v1/opendata/t187ap07_L_basi` |
