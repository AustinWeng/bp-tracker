# Windows 部署指南

把 bp-tracker 打包成單檔 `bp-tracker.exe`,雙擊即跑、不需安裝 Python。

## 在 Windows 機器上 build

> PyInstaller 不支援 cross-compile — Windows .exe 必須在 Windows 上 build。
> 如果你是在 Mac 上開發,先把整個專案 git clone 到 Windows 機器再 build。

1. **裝 Python 3.10+**
   - https://www.python.org/downloads/
   - 安裝時 **務必勾選**「Add python.exe to PATH」

2. **取得專案**
   ```cmd
   git clone <你的私有 repo URL>
   cd bp-tracker
   ```

3. **執行 build**
   - 雙擊 `build_windows.bat`,或在 cmd 跑:
     ```cmd
     build_windows.bat
     ```
   - 第一次會自動建 venv、裝套件、打包 (約 1-3 分鐘)

4. **產出**
   ```
   dist\
   ├── bp-tracker.exe    ← 單檔執行檔 (~30-50 MB)
   └── bp.db             ← 你的資料庫 (從 phase2_db\ 複製過來)
   ```

## 使用

把整個 `dist\` 資料夾複製到任何位置(USB、桌面、家人電腦),雙擊 `bp-tracker.exe`:

- console 視窗會顯示 URL
- 瀏覽器自動開啟 `http://localhost:5050`
- 關掉 console 視窗即停止
- **`bp.db` 永遠在 exe 同目錄** — 隨 exe 一起搬就帶著資料走

## 備份

- 整包複製 `dist\` 即備份所有資料
- 或單獨複製 `bp.db`(用 SQLite 工具如 DB Browser for SQLite 也能直接開)

## 校對 Excel 重匯入

從 web 介面「重匯入」上傳 Excel 即可,不需修改 exe。上傳檔會存在 `dist\phase2_db\uploads\`(自動建立)。

## 常見問題

**Q: Windows Defender / 防毒軟體警告?**
A: PyInstaller 打包的 exe 沒簽章,Defender 偶爾會誤判。spec 已停用 UPX 壓縮(誤判最常見來源)。如果仍被擋,在 Defender 加例外即可。如要徹底解決需 code signing 憑證(個人不必)。

**Q: 換 port?**
A: 開 cmd 跑:
```cmd
set PORT=5099
bp-tracker.exe
```

**Q: 不要自動開瀏覽器?**
A:
```cmd
set BP_NO_BROWSER=1
bp-tracker.exe
```

**Q: exe 太大怎麼辦?**
A: 已 exclude 大型套件(numpy / matplotlib / Qt 等),約 30-50 MB 是 PyInstaller 含 Python runtime 的最低水位。若需更小,可考慮 Nuitka 或 Briefcase(額外工程量)。

**Q: 我有 Mac,可以打包 Mac 版測試嗎?**
A: 可以。在 Mac 跑:
```bash
.venv/bin/pip install pyinstaller waitress
.venv/bin/pyinstaller bp_tracker.spec
```
產生 `dist/bp-tracker`(Mac 二進位),雙擊或從 Terminal 跑都行。
