==================================================================
  bp-tracker  -  Windows 安裝步驟 (請先讀)
==================================================================

這個 zip 包含完整 source code + 你的血壓資料 (bp.db, 校對 Excel)。
PyInstaller 不能在 Mac 上產出 Windows .exe,所以 .exe 必須在 Windows
上 build。流程如下:


第 1 步: 安裝 Python 3.10 以上
------------------------------------------------------------------
1. 打開 https://www.python.org/downloads/
2. 下載最新版 Python (3.10+ 都可)
3. 跑安裝程式時,**第一個畫面下方務必勾選**:
   [v] Add python.exe to PATH
4. 點 "Install Now"


第 2 步: 解壓 zip,進入資料夾
------------------------------------------------------------------
解壓後路徑類似:
    C:\Users\你的帳號\Desktop\bp-tracker\

進入這個資料夾,你會看到:
    build_windows.bat   <-- 等下要雙擊這個
    launcher.py
    bp_tracker.spec
    app\
    phase2_db\bp.db     <-- 你的血壓資料,已包進來
    ...


第 3 步: 雙擊 build_windows.bat
------------------------------------------------------------------
- 第一次跑會自動建 venv、裝套件、用 PyInstaller 打包
- 大約需要 1 - 3 分鐘 (視網速與電腦速度)
- 完成後資料夾內會多出:
    dist\
      bp-tracker.exe   <-- 主程式 (約 30-50 MB,單檔)
      bp.db            <-- 你的資料庫 (從 phase2_db\ 自動複製過來)


第 4 步: 啟動使用
------------------------------------------------------------------
雙擊 dist\bp-tracker.exe:
- 會跳出黑色 console 視窗顯示啟動訊息
- 瀏覽器自動開啟 http://localhost:5050
- 進入後即可看到儀表板、記錄、分析等功能

關閉:直接關掉 console 視窗。

之後使用,只要雙擊 bp-tracker.exe 就行,不需要再 build。


移動位置 / 備份
------------------------------------------------------------------
你想搬到別的位置 (例如 USB 隨身碟、其他電腦),整個 dist\ 資料夾
複製過去就行 (要連同 bp.db 一起搬,資料才會跟著走)。


常見問題
------------------------------------------------------------------
Q: Windows Defender 跳警告 "未識別的 app"
A: 因為 exe 沒簽章。點「其他資訊」→「仍要執行」即可。
   或在 Defender 設定加例外。

Q: 雙擊 build_windows.bat 後一閃就關掉了
A: 通常是 Python 沒裝好或沒加入 PATH。打開 cmd 跑:
       python --version
   應顯示 3.10+。沒顯示就重裝 Python 並勾選 PATH。

Q: 想換 port (例如 5050 被佔用)
A: 開 cmd 跑:
       set PORT=5099
       cd path\to\dist
       bp-tracker.exe

Q: 不想自動開瀏覽器
A: 開 cmd 跑:
       set BP_NO_BROWSER=1
       bp-tracker.exe

更詳細說明見 WINDOWS.md。
