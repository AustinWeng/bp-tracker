#!/bin/bash
# 為 Windows 部署打包 source + 既有資料庫 + 校對 Excel。
# 產生的 zip 帶到 Windows 解壓後,雙擊 build_windows.bat 即可產出 bp-tracker.exe。
#
# 用法:
#   ./package_for_windows.sh                # 預設輸出到 ~/Desktop
#   OUT_DIR=/somewhere ./package_for_windows.sh

set -e
cd "$(dirname "$0")"

OUT_DIR="${OUT_DIR:-$HOME/Desktop}"
TIMESTAMP=$(date +%Y%m%d_%H%M)
STAGE="$(mktemp -d)/bp-tracker"
ZIP_NAME="bp-tracker_windows_${TIMESTAMP}.zip"
ZIP_PATH="$OUT_DIR/$ZIP_NAME"

echo "→ 準備 staging directory: $STAGE"
mkdir -p "$STAGE"

# rsync 把專案複製進 staging,排除不需要的
rsync -a \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='**/__pycache__/' \
    --exclude='**/*.pyc' \
    --exclude='build/' \
    --exclude='dist/' \
    --exclude='phase1_ocr/pages/' \
    --exclude='phase1_ocr/ocr_raw/' \
    --exclude='phase2_db/uploads/' \
    --exclude='phase2_db/backups/' \
    --exclude='phase2_db/*.db-wal' \
    --exclude='phase2_db/*.db-shm' \
    --exclude='phase2_db/*.db.bak' \
    --exclude='phase1_ocr/output/~$*' \
    --exclude='**/.DS_Store' \
    --exclude='*.zip' \
    --exclude='exports/*' \
    ./ "$STAGE/"

# 確認關鍵檔都在
echo "→ 檢查關鍵檔案..."
REQUIRED=(
    "$STAGE/launcher.py"
    "$STAGE/bp_tracker.spec"
    "$STAGE/build_windows.bat"
    "$STAGE/requirements.txt"
    "$STAGE/app/analytics.py"
    "$STAGE/app/templates/analytics.html"
    "$STAGE/phase2_db/schema.sql"
)
for f in "${REQUIRED[@]}"; do
    if [ ! -f "$f" ]; then
        echo "  [X] 缺少: $f"
        exit 1
    fi
done

# bp.db 與校對 Excel 是核心資料,確認存在
[ -f "$STAGE/phase2_db/bp.db" ] && echo "  [OK] bp.db ($(du -h "$STAGE/phase2_db/bp.db" | cut -f1))" \
    || echo "  [!] phase2_db/bp.db 不存在 (Windows 啟動時會建立空 DB)"
[ -f "$STAGE/phase1_ocr/output/bp_ocr_review.xlsx" ] && \
    echo "  [OK] bp_ocr_review.xlsx ($(du -h "$STAGE/phase1_ocr/output/bp_ocr_review.xlsx" | cut -f1))" \
    || echo "  [!] phase1_ocr/output/bp_ocr_review.xlsx 不存在"

# 先讀取一遍 README_WINDOWS_FIRST.txt (在專案內),如果有就會被 rsync 帶進來
if [ ! -f "$STAGE/README_WINDOWS_FIRST.txt" ]; then
    echo "  [!] 找不到 README_WINDOWS_FIRST.txt — 仍然繼續"
fi

# 打包
echo "→ 打包 $ZIP_PATH ..."
mkdir -p "$OUT_DIR"
(cd "$(dirname "$STAGE")" && zip -rq "$ZIP_PATH" "bp-tracker")

# 清理 staging
rm -rf "$(dirname "$STAGE")"

SIZE=$(du -h "$ZIP_PATH" | cut -f1)
echo ""
echo "═══════════════════════════════════════════════"
echo "  [OK] 打包完成"
echo "═══════════════════════════════════════════════"
echo ""
echo "  檔案: $ZIP_PATH"
echo "  大小: $SIZE"
echo ""
echo "  Windows 端使用步驟:"
echo "    1. 把 $ZIP_NAME 複製到 Windows 機器 (USB / AirDrop / 雲端)"
echo "    2. 解壓縮 → 進入 bp-tracker\\ 資料夾"
echo "    3. 雙擊 build_windows.bat (第一次需 1-3 分鐘建 venv 並打包)"
echo "    4. 完成後雙擊 dist\\bp-tracker.exe 即可使用"
echo ""
