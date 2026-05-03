"""PyInstaller launcher for bp-tracker.

Behaves identically when run with `python launcher.py` and when run as a
PyInstaller-frozen executable. In frozen mode the DB lives next to the .exe
(so the user can see/back-up/move it), while bundled assets (templates,
static files, schema.sql) come from sys._MEIPASS.
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resolve_paths():
    """Return (db_path, schema_path, project_root) for both frozen & dev modes."""
    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)  # PyInstaller temp extract dir
        exe_dir = Path(sys.executable).parent
        db_path = exe_dir / "bp.db"
        schema_path = bundle_dir / "phase2_db" / "schema.sql"
        project_root = bundle_dir
    else:
        project_root = Path(__file__).resolve().parent
        db_path = project_root / "phase2_db" / "bp.db"
        schema_path = project_root / "phase2_db" / "schema.sql"
    return db_path, schema_path, project_root


def _init_db_if_missing(db_path: Path, schema_path: Path):
    if db_path.exists():
        return False
    import sqlite3
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
    return True


def main():
    db_path, schema_path, _ = _resolve_paths()

    # Tell app.db where the database is.
    os.environ["BP_DB_PATH"] = str(db_path)

    created = _init_db_if_missing(db_path, schema_path)
    if created:
        print(f"[+] 已建立空資料庫 {db_path}")
    else:
        print(f"[i] 使用現有資料庫 {db_path}")

    from app import create_app
    app = create_app()

    port = int(os.environ.get("PORT", "5050"))
    url = f"http://localhost:{port}"

    def _open_browser():
        time.sleep(1.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if os.environ.get("BP_NO_BROWSER", "").lower() not in ("1", "true", "yes"):
        threading.Thread(target=_open_browser, daemon=True).start()

    print()
    print("═══════════════════════════════════════════")
    print(f"  血壓記錄系統  →  {url}")
    print("  停止: 關閉本視窗 或 按 Ctrl+C")
    print("═══════════════════════════════════════════")
    print()

    # In frozen mode prefer waitress (production WSGI), fall back to Flask dev server.
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=4)
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
