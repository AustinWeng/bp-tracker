# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for bp-tracker (Windows / macOS single-file build).

Build:
    pyinstaller bp_tracker.spec

Output:
    dist/bp-tracker.exe   (Windows)
    dist/bp-tracker       (macOS / Linux)
"""

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
        ('phase2_db/schema.sql', 'phase2_db'),
    ],
    hiddenimports=[
        'waitress',
        'app',
        'app.routes',
        'app.db',
        'app.analytics',
        'app.health_export',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'IPython', 'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bp-tracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 容易被 Windows Defender 誤判,關掉
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # 保留 console 視窗,讓使用者看到 URL 與停止指示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
