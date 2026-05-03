#!/bin/bash
# 打包腳本 — 產出可攜式 zip 檔
# 包含: app 程式碼、目前資料庫、Excel 校對檔、啟動腳本
# 排除: venv、git、PNG 圖片、JSON 中間檔、input PDF (這些可從原專案重建)

set -e
cd "$(dirname "$0")"

OUT_DIR="${OUT_DIR:-$HOME/Desktop}"
TIMESTAMP=$(date +%Y%m%d_%H%M)
ZIP_NAME="bp-tracker_${TIMESTAMP}.zip"
ZIP_PATH="$OUT_DIR/$ZIP_NAME"

echo "→ 打包 bp-tracker..."

zip -rq "$ZIP_PATH" . \
    -x ".git/*" \
    -x ".git" \
    -x ".venv/*" \
    -x "**/__pycache__/*" \
    -x "**/__pycache__" \
    -x "**/*.pyc" \
    -x ".env" \
    -x ".env.*" \
    -x "phase1_ocr/pages/*" \
    -x "phase1_ocr/ocr_raw/*" \
    -x "phase1_ocr/input/*" \
    -x "phase2_db/uploads/*" \
    -x "phase2_db/backups/*" \
    -x "phase2_db/*.db.bak" \
    -x "phase2_db/*.db-wal" \
    -x "phase2_db/*.db-shm" \
    -x "phase1_ocr/output/~\$*" \
    -x ".DS_Store" \
    -x "**/.DS_Store" \
    -x "*.zip" \
    -x "phase1_ocr/output/*.bak"

SIZE=$(du -h "$ZIP_PATH" | cut -f1)

echo ""
echo "✓ 打包完成"
echo "  路徑: $ZIP_PATH"
echo "  大小: $SIZE"
echo ""
echo "傳到另一台電腦的步驟:"
echo "  1. 把 $ZIP_NAME 複製到目標電腦"
echo "  2. 解壓縮 (雙擊或 unzip $ZIP_NAME)"
echo "  3. 進入解壓後的資料夾"
echo "  4. 在 Terminal 執行: ./start.sh"
echo "  5. 第一次需 Python 3.10+ (從 python.org 安裝)"
