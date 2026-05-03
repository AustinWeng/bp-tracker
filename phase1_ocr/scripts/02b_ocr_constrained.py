#!/usr/bin/env python3
"""Re-OCR specific pages with explicit date-range constraint.

Use when OCR misread the year/month due to ambiguous handwriting.
Pass page numbers as args, e.g.: python 02b_ocr_constrained.py 04 13 19 20 21 25 26 28 29
Output overwrites ocr_raw/page_NN.json (originals backed up to .orig).
"""
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
OUT = ROOT / "ocr_raw"

MODEL = "opus"
PER_CALL_BUDGET = 1.0

SYSTEM_PROMPT = """你是手寫血壓記錄表的 OCR 專家。給你一頁手寫血壓記錄表的 PNG,你必須用 Read tool 讀取它然後輸出嚴格 JSON。

# 重要日期約束 (必須遵守)
此筆記本的所有日期必須落在 **2025-09-01 到 2026-05-31** 之間。
合法的 (年, 月) 組合僅限:
- 2025: 9月、10月、11月、12月
- 2026: 1月、2月、3月、4月、5月

如果你判讀的日期/月份不在此範圍內,**必定是手寫字跡誤判**。常見混淆:
- 「2」可能被誤讀為「7」(應驗證:2 月在台灣氣溫 10-20°C,7 月 28-35°C)
- 「8」可能被誤讀為「9」(8 月已超出範圍,改為 9 月)
- 「4」與「9」、「3」與「8」也常混
請用以下線索校正:
1. 當日氣溫 (寫在日期後面) — 台灣月均溫:
   - 9月 27°C、10月 24°C、11月 21°C、12月 17°C
   - 1月 16°C、2月 17°C、3月 19°C、4月 23°C、5月 26°C
2. 頁面上下文連續性 (相鄰日期應接近)
3. 民國年:114年 = 2025、115年 = 2026

# 日期數字辨識 (極重要!)
日期格式為 M/D。日 (D) 可能是 1-31。常見錯誤:
- 「16, 17, 18, 19」常被誤讀為「6, 7, 8, 9」(漏掉前面的「1」)
- 「11, 12」(月份) 常被誤讀為「1, 2」或「8, 9」
- 「20, 21, 22, ..., 29」常被誤讀為「2X」中的 X
**檢查方式**:相鄰天數應遞增 (1, 2, 3, ... 或 15, 16, 17, ...),如果你讀到不連續的日期 (例如 11/2 後面跟 11/16 有跳躍),
請仔細確認是真的跳躍還是中間的 11/3, 11/4...11/15 都被略過 (極不可能,使用者每天都量)。
連續性建議按月排,左欄上到下,右欄上到下,日期應該是遞增的。

# 頁面結構
- 頁首可能有 DATE 欄寫民國年月,例如「114年9月」、「115年1月」
- 民國轉西元:西元年 = 民國年 + 1911
- 版面可能單欄 (約 4 天/頁) 或雙欄 (約 8 天/頁)
- 雙欄頁:先讀完左欄上到下,再讀右欄上到下

# 每天的結構
- 日期標題格式「M/D」(例如 9/1) 後接「當日氣溫°C」
- 一天最多兩個 session:AM (上午)、PM (下午)
- 每個 session 有時間標記 (如 AM8:00、PM10:30) 和 4 筆讀數

# 每個 Session 的 4 筆讀數 (2x2 網格)
- 左上 = L1、右上 = R1、左下 = L2、右下 = R2
每筆讀數格式「收縮/舒張/心跳」(例如 137/92/76)

# 輸出 (嚴格 JSON,不要 ```json``` 標記,不要任何說明文字)
{
  "page_roc_year": <114 或 115 或 null>,
  "page_month": <1-12>,
  "page_year_western": <2025 或 2026>,
  "page_confidence": "high" | "medium" | "low",
  "page_notes": "<整頁觀察,特別說明你如何決定年/月>",
  "sessions": [
    {
      "date": "YYYY-MM-DD",
      "period": "AM" | "PM",
      "time": "HH:MM" 或 null,
      "temperature_c": <數字 或 null>,
      "readings": [
        {"seq": 1, "arm": "L", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []},
        {"seq": 1, "arm": "R", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []},
        {"seq": 2, "arm": "L", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []},
        {"seq": 2, "arm": "R", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []}
      ],
      "notes": "<該 session 附近中文文字>",
      "confidence": "high" | "medium" | "low",
      "raw_text": "<該 session 原始手寫文字>"
    }
  ]
}

# 規則
1. 字跡不清:猜測但欄位名加進 uncertain
2. 完全無法判讀:該欄 null 並列入 uncertain
3. BP 範圍:收縮 70-250、舒張 40-150、心跳 30-200
4. 氣溫範圍:5-40°C
5. session 不滿 4 筆讀數:只輸出實際看到的
6. session 附近的中文 (早起/飯後/頭暈/運動後) → 放該 session notes
7. 只輸出 JSON 物件本身,不要任何前後文字
8. **所有 sessions 的日期必須在 2025-09-01 到 2026-05-31 範圍內**
"""


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON: {text[:200]}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced")


def ocr_page(page_path: Path, page_num: int) -> dict:
    user_prompt = (
        f"Use Read tool to load: {page_path.absolute()}\n"
        f"This is page {page_num}. The data MUST fall within 2025-09 to 2026-05. "
        f"If your initial read says otherwise, re-examine the handwriting carefully "
        f"(common misreads: 2↔7, 8↔9, 3↔8) and use temperature/context to pick the correct month/year. "
        f"Output ONLY the JSON object."
    )
    cmd = [
        "claude", "-p",
        "--model", MODEL,
        "--system-prompt", SYSTEM_PROMPT,
        "--output-format", "json",
        "--allowedTools", "Read",
        "--max-budget-usd", str(PER_CALL_BUDGET),
        "--no-session-persistence",
        user_prompt,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if res.returncode != 0:
        raise RuntimeError(f"CLI rc={res.returncode}: {res.stderr[:500]}")
    envelope = json.loads(res.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"CLI err: {envelope.get('result')[:500]}")
    data = extract_json_object(envelope.get("result", ""))
    data["_page_num"] = page_num
    data["_cost_usd"] = envelope.get("total_cost_usd", 0)
    data["_duration_ms"] = envelope.get("duration_ms", 0)
    data["_constrained"] = True
    u = envelope.get("usage", {})
    data["_usage"] = {
        "input": u.get("input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "cache_create": u.get("cache_creation_input_tokens", 0),
    }
    return data


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: 02b_ocr_constrained.py PAGE_NUM [PAGE_NUM ...]")
    page_nums = [int(x) for x in sys.argv[1:]]

    total_cost = 0.0
    for n in page_nums:
        png = PAGES / f"page_{n:02d}.png"
        if not png.exists():
            print(f"page {n:02d}: PNG not found, skip")
            continue
        print(f"page {n:02d}: re-OCR with constraint...", flush=True)
        t0 = time.time()
        try:
            data = ocr_page(png, n)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue
        dt = time.time() - t0

        # backup original
        out_file = OUT / f"page_{n:02d}.json"
        if out_file.exists():
            backup = OUT / f"page_{n:02d}.json.orig"
            if not backup.exists():
                shutil.copy(out_file, backup)

        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        n_sess = len(data.get("sessions", []))
        cost = data.get("_cost_usd", 0)
        total_cost += cost
        sample_dates = sorted(set(s.get("date","") for s in data.get("sessions",[])))[:3]
        print(f"  ✓ {dt:.1f}s, sessions={n_sess}, conf={data.get('page_confidence')}, "
              f"year={data.get('page_year_western')}, sample={sample_dates}, cost=${cost:.3f}", flush=True)

    print(f"\nTotal cost: ${total_cost:.2f} USD")


if __name__ == "__main__":
    main()
