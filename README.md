# 血壓記錄系統

家庭血壓量測記錄與趨勢分析,本機 Web 應用。

## 快速啟動

### Mac

```bash
./start.sh
```

第一次會自動建立 venv、安裝套件、初始化資料庫,之後直接啟動。
啟動後瀏覽器自動開啟 http://localhost:5050

### Windows / Linux

確保安裝 Python 3.10+ 後:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # Linux/Mac
.venv\Scripts\pip install -r requirements.txt  # Windows
.venv/bin/python run.py
```

開瀏覽器到 http://localhost:5050

## 功能

- **儀表板** — 血壓分級、趨勢圖 (8 種組合可獨立切換顯示)、當日變異區間 (股票風格)、**點圖跳記錄**(任一資料點 → 該日記錄高亮)、**📊 分析洞察卡片**(晨/昏對比、左右手差、週趨勢、達標率)+ **📝 規則式自動摘要**
- **進階分析** (`/analytics`) — 血壓分級分布、達標率、變異係數、週平均線性回歸、季節性、8 組箱形圖、Pearson 相關係數 (收縮 vs 舒張 / 心跳 / 氣溫)
- **記錄** — 全部歷史記錄,支援搜尋、編輯、刪除;支援 `?focus=YYYY-MM-DD` 聚焦該日(從儀表板自動帶入)
- **新增** — 雙手 4 筆讀數 + 氣溫 + 備註,手機友善
- **匯出** — Apple Health XML 格式,可匯入 iPhone「健康」App
- **重匯入** — 上傳校對版 Excel,整批替換 OCR 資料但保留手動輸入

## 專案結構

```
bp-tracker/
├── start.sh                # 一鍵啟動 (Mac)
├── package.sh              # 打包成 zip 給其他電腦
├── run.py                  # 開發伺服器入口
├── requirements.txt
├── app/                    # Flask 應用
│   ├── __init__.py
│   ├── routes.py
│   ├── db.py
│   ├── health_export.py
│   ├── templates/
│   └── static/
├── phase1_ocr/
│   ├── output/
│   │   └── bp_ocr_review.xlsx   # OCR 校對檔
│   └── scripts/                  # OCR 腳本
├── phase2_db/
│   ├── schema.sql
│   ├── import_excel_to_db.py    # Excel → SQLite
│   └── bp.db                    # SQLite 資料庫
├── docker/                       # Docker 部署 (NAS 用)
└── .gitignore
```

## 校對流程

1. 開啟 `phase1_ocr/output/bp_ocr_review.xlsx`
2. 在「校對檢視」分頁修正 OCR 錯誤的數值/日期/時刻
3. 把該列「校對狀態」改為「已確認」或「已修正」(下拉)
4. 儲存 Excel
5. 開啟 web 系統的「重匯入」分頁,上傳該 Excel
6. 選「校對版」模式,點上傳並重新匯入

系統會:
- 刪除所有現有 OCR 資料 (source = ocr_v1 / ocr_v2)
- 從 Excel 重新匯入「已確認/已修正」的列,標 source = ocr_v2
- **手動輸入的記錄完全保留** (source = manual / edit)

## 移到另一台電腦

### Mac / Linux:zip + Python
```bash
./package.sh                            # 打包到桌面
# 把產生的 .zip 複製到目標電腦
# 解壓 → cd 進去 → ./start.sh
```

### Windows:單檔 exe(雙擊即跑,不需 Python)
詳見 [WINDOWS.md](WINDOWS.md)。在 Windows 機器上 git clone 後雙擊 `build_windows.bat`,
產生 `dist\bp-tracker.exe` (~30 MB) + `dist\bp.db`。整包複製即可移植。

## 部署到 NAS (Synology)

見 `docker/README.md`。基本步驟:

```bash
docker build -f docker/Dockerfile -t bp-tracker .
# 上傳 image 到 NAS,用 Container Manager 部署 docker-compose.yml
```

## 技術棧

- Python 3.10+ + Flask
- SQLite
- Tailwind CSS (CDN) + Chart.js (CDN)
- 支援 macOS / Linux / Windows / Docker

## DB Schema (重點)

```sql
bp_records:  id, user_id, measure_date, period (AM/PM), measure_time,
             sequence (1/2), arm (L/R), systolic, diastolic, pulse,
             notes, source (ocr_v1/ocr_v2/manual/edit), source_ref,
             created_at, updated_at
             UNIQUE(user_id, measure_date, period, sequence, arm)

daily_context: user_id, measure_date, temperature_c, weather_notes
```

每天完整 8 筆讀數 (AM/PM × 第1/2次 × L/R)。
