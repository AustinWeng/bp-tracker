#!/bin/bash
# 血壓記錄系統 — 啟動腳本
# 第一次執行會自動建立 venv、安裝套件;之後直接啟動。

set -e
cd "$(dirname "$0")"

# 1. 找 Python
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "❌ 找不到 Python 3。請先到 https://www.python.org/downloads/ 安裝 Python 3.10 以上"
    read -p "按 Enter 結束..."
    exit 1
fi
echo "✓ 使用 $($PYTHON --version) at $PYTHON"

# 2. 建 venv (若不存在)
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "→ 建立虛擬環境 ($VENV_DIR)..."
    $PYTHON -m venv "$VENV_DIR"
fi

# 3. 安裝套件 (僅第一次)
DEPS_MARKER="$VENV_DIR/.deps_installed"
if [ ! -f "$DEPS_MARKER" ] || [ "requirements.txt" -nt "$DEPS_MARKER" ]; then
    echo "→ 安裝套件 (僅第一次需要)..."
    "$VENV_DIR/bin/pip" install -q --upgrade pip
    "$VENV_DIR/bin/pip" install -q -r requirements.txt
    touch "$DEPS_MARKER"
fi

# 4. 初始化 DB (若不存在)
if [ ! -f "phase2_db/bp.db" ]; then
    echo "→ 初始化資料庫..."
    "$VENV_DIR/bin/python" -c "
import sqlite3
from pathlib import Path
schema = Path('phase2_db/schema.sql').read_text()
conn = sqlite3.connect('phase2_db/bp.db')
conn.executescript(schema)
conn.close()
print('✓ 空資料庫已建立')
"
fi

# 5. 啟動伺服器,1 秒後自動開瀏覽器
PORT=${PORT:-5050}
echo ""
echo "═══════════════════════════════════════════"
echo "  血壓記錄系統啟動中..."
echo "  網址: http://localhost:$PORT"
echo "  停止: 按 Ctrl+C"
echo "═══════════════════════════════════════════"
echo ""

(sleep 2 && (command -v open >/dev/null && open "http://localhost:$PORT" || \
             command -v xdg-open >/dev/null && xdg-open "http://localhost:$PORT" || \
             echo "請手動開啟瀏覽器到 http://localhost:$PORT")) &

PORT=$PORT "$VENV_DIR/bin/python" run.py
