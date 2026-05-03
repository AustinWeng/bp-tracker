"""PyInstaller launcher for bp-tracker.

Frozen / windowed mode:
    - Flask runs in a background thread (waitress preferred, fallback to dev server)
    - Main thread shows a system-tray icon (pystray): right-click → Open / Quit
    - stdout/stderr redirected to bp-tracker.log next to the .exe (no console window)

Dev / console mode:
    - Same logic; if pystray is unavailable, falls back to a sleep loop
      so you can Ctrl+C to stop.
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resolve_paths():
    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)
        exe_dir = Path(sys.executable).parent
        db_path = exe_dir / "bp.db"
        schema_path = bundle_dir / "phase2_db" / "schema.sql"
        log_path = exe_dir / "bp-tracker.log"
    else:
        proj_root = Path(__file__).resolve().parent
        db_path = proj_root / "phase2_db" / "bp.db"
        schema_path = proj_root / "phase2_db" / "schema.sql"
        log_path = proj_root / "bp-tracker.log"
    return db_path, schema_path, log_path


def _redirect_stdio_if_windowed(log_path: Path):
    """When --windowed/--noconsole, sys.stdout/stderr are None on Windows.
    Redirect both to a log file so errors don't vanish silently."""
    if sys.stdout is None or sys.stderr is None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f


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


def _make_tray_image():
    """Generate a 64×64 red circle with a white medical cross (in-memory)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(220, 38, 38, 255))      # red circle
    d.rectangle((30, 18, 34, 46), fill=(255, 255, 255, 255))  # vertical bar
    d.rectangle((18, 30, 46, 34), fill=(255, 255, 255, 255))  # horizontal bar
    return img


def _start_flask(app, port):
    """Run Flask in current thread (called from a daemon thread)."""
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=port, threads=4)
    except ImportError:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        print(f"[ERROR] Flask server crashed: {exc}", file=sys.stderr)


def _run_with_tray(url: str):
    """Show a system-tray icon. Blocking until Quit."""
    import pystray

    def on_open(icon, item):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        "bp-tracker",
        _make_tray_image(),
        "bp-tracker (running)",
        menu=pystray.Menu(
            pystray.MenuItem("開啟血壓系統", on_open, default=True),
            pystray.MenuItem("離開", on_quit),
        ),
    )
    icon.run()


def _run_console_loop(url: str):
    """Fallback when pystray is missing: keep server alive until Ctrl+C."""
    print()
    print("═══════════════════════════════════════════")
    print(f"  血壓記錄系統  →  {url}")
    print("  停止: 關閉本視窗 或 按 Ctrl+C")
    print("═══════════════════════════════════════════")
    print()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main():
    db_path, schema_path, log_path = _resolve_paths()
    _redirect_stdio_if_windowed(log_path)

    os.environ["BP_DB_PATH"] = str(db_path)

    if _init_db_if_missing(db_path, schema_path):
        print(f"[+] Created empty DB at {db_path}")
    else:
        print(f"[i] Using existing DB {db_path}")

    from app import create_app
    app = create_app()

    port = int(os.environ.get("PORT", "5050"))
    url = f"http://localhost:{port}"

    # Server runs in background thread (daemon = dies with main thread)
    server_thread = threading.Thread(
        target=_start_flask, args=(app, port), daemon=True, name="flask-server"
    )
    server_thread.start()

    # Auto-open browser once on startup
    if os.environ.get("BP_NO_BROWSER", "").lower() not in ("1", "true", "yes"):
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(url)),
            daemon=True, name="browser-opener",
        ).start()

    # Main thread: tray icon (preferred) or console loop (fallback)
    try:
        _run_with_tray(url)
    except ImportError:
        print("[i] pystray not available — running in console mode.")
        _run_console_loop(url)
    except Exception as exc:
        # Tray init failed — likely no display. Fall back to console.
        print(f"[!] Tray init failed ({exc}); falling back to console mode.")
        _run_console_loop(url)


if __name__ == "__main__":
    main()
