#!/usr/bin/env python3
"""Final OCR pass: re-OCR all non-high-confidence pages with adjacent-page context.

Reads current OCR results, sorts by page number, builds adjacent-page date context,
re-OCRs each medium/low page with maximum constraint + context.

Usage: python 02c_ocr_final_pass.py        # run on all medium/low pages
       python 02c_ocr_final_pass.py 10 11  # run on specific pages
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
PER_CALL_BUDGET = 1.5

SYSTEM_PROMPT_TEMPLATE = """你是手寫血壓記錄表的 OCR 專家。給你一頁手寫血壓記錄表的 PNG,你必須用 Read tool 讀取它然後輸出嚴格 JSON。

# 重要日期約束
此筆記本所有日期必須落在 **2025-09-01 到 2026-05-31** 之間。
合法 (年, 月) 組合: 2025-09/10/11/12, 2026-01/02/03/04/05

# 信心度標準 (重要!)
- **high**: 數值與日期都清楚可辨,即使少數幾個數字略有筆畫模糊
- **medium**: 整體可讀,但有 1-2 個欄位需要合理猜測
- **low**: 多處嚴重模糊或無法判讀
**請不要過度保守。只要絕大部分內容你能合理判讀,就標 high。**

# 日期數字辨識 (必須遵守)
日期格式 M/D。常見手寫誤判:
- 「16, 17, 18, 19」常被誤讀為「6, 7, 8, 9」(漏「1」)
- 「11, 12」(月) 常被誤讀為「1, 2」或漏「1」
- 「2」與「7」、「8」與「9」、「3」與「8」筆畫類似

**驗證:**
1. 同一頁日期應大致連續 (1, 2, 3, ...) 或 (15, 16, 17, ...)
2. 不應該跨月時跳號太多 (例如 11/4 後面跳到 11/16 中間缺 11/5-11/15 → 極不可能,使用者每天量)
3. 用氣溫驗證月份:9月 27°C、10月 24°C、11月 21°C、12月 17°C、1月 16°C、2月 17°C、3月 19°C、4月 23°C、5月 26°C
4. 民國 114年=2025、115年=2026

# 上下文 (前後頁的日期範圍)
{context}

請參考上下文判斷本頁應該覆蓋哪段日期。如果你的初步判讀與上下文不連續,請重新檢視。

# 頁面結構
- 頁首可能有 DATE 欄寫民國年月,例如「114年9月」、「115年1月」
- 版面可能單欄 (4 天/頁) 或雙欄 (8 天/頁)
- 雙欄頁:先讀完左欄上到下,再讀右欄上到下

# 每天的結構
- 日期標題格式「M/D」後接「當日氣溫°C」(例如 9/1 30)
- 一天最多兩 session: AM、PM
- 每 session 有時間 (AM8:00、PM10:30) 和 4 筆讀數

# 每 Session 的 4 筆讀數 (2x2 網格)
- 左上=L1、右上=R1、左下=L2、右下=R2
每筆「收縮/舒張/心跳」(例如 137/92/76)

# 輸出 (嚴格 JSON,不要 markdown,不要說明)
{{
  "page_roc_year": <114 或 115 或 null>,
  "page_month": <1-12>,
  "page_year_western": <2025 或 2026>,
  "page_confidence": "high" | "medium" | "low",
  "page_notes": "<整頁觀察>",
  "sessions": [
    {{
      "date": "YYYY-MM-DD",
      "period": "AM" | "PM",
      "time": "HH:MM" 或 null,
      "temperature_c": <數字 或 null>,
      "readings": [
        {{"seq": 1, "arm": "L", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []}},
        {{"seq": 1, "arm": "R", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []}},
        {{"seq": 2, "arm": "L", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []}},
        {{"seq": 2, "arm": "R", "systolic": <int>, "diastolic": <int>, "pulse": <int>, "uncertain": []}}
      ],
      "notes": "<該 session 附近中文文字>",
      "confidence": "high" | "medium" | "low",
      "raw_text": "<該 session 原始手寫文字>"
    }}
  ]
}}

# 規則
1. 字跡不清:猜測但欄位名加 uncertain
2. 完全無法判讀:該欄 null 並列入 uncertain
3. BP 範圍:收縮 70-250、舒張 40-150、心跳 30-200
4. session 不滿 4 筆讀數:只輸出實際看到的
5. 中文 (早起/飯後/頭暈/運動後) → session notes
6. 只輸出 JSON 物件,不要任何前後文字
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


def get_page_date_range(json_path: Path) -> str:
    """Return 'YYYY-MM-DD ~ YYYY-MM-DD' or '?' if not parseable."""
    try:
        data = json.loads(json_path.read_text())
        dates = sorted(set(s.get("date","") for s in data.get("sessions",[]) if s.get("date")))
        valid = [d for d in dates if len(d)==10 and d[0].isdigit()]
        if valid:
            return f"{valid[0]} ~ {valid[-1]}"
    except Exception:
        pass
    return "?"


def build_context(page_num: int) -> str:
    """Build 'previous and next page date range' context."""
    prev_n = page_num - 1
    next_n = page_num + 1
    parts = []
    if prev_n >= 1:
        prev_file = OUT / f"page_{prev_n:02d}.json"
        if prev_file.exists():
            parts.append(f"前一頁 (p{prev_n:02d}) 覆蓋: {get_page_date_range(prev_file)}")
    if next_n <= 30:
        next_file = OUT / f"page_{next_n:02d}.json"
        if next_file.exists():
            parts.append(f"後一頁 (p{next_n:02d}) 覆蓋: {get_page_date_range(next_file)}")
    return "\n".join(parts) if parts else "(無相鄰頁資訊)"


def ocr_page(page_path: Path, page_num: int) -> dict:
    context = build_context(page_num)
    sys_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context)
    user_prompt = (
        f"Use Read tool to load: {page_path.absolute()}\n"
        f"This is page {page_num} of 30. Re-examine carefully. "
        f"Use the adjacent-page context in the system prompt to validate your date inferences. "
        f"Aim for high confidence by reading values precisely. "
        f"Output ONLY the JSON object."
    )
    cmd = [
        "claude", "-p",
        "--model", MODEL,
        "--system-prompt", sys_prompt,
        "--output-format", "json",
        "--allowedTools", "Read",
        "--max-budget-usd", str(PER_CALL_BUDGET),
        "--no-session-persistence",
        user_prompt,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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
    data["_final_pass"] = True
    u = envelope.get("usage", {})
    data["_usage"] = {
        "input": u.get("input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "cache_create": u.get("cache_creation_input_tokens", 0),
    }
    return data


def main():
    if len(sys.argv) > 1:
        page_nums = [int(x) for x in sys.argv[1:]]
    else:
        # Auto-detect all non-high pages
        page_nums = []
        for jf in sorted(OUT.glob("page_*.json")):
            n = int(jf.stem.split("_")[1])
            try:
                data = json.loads(jf.read_text())
                if data.get("page_confidence") != "high":
                    page_nums.append(n)
            except Exception:
                page_nums.append(n)
        print(f"Auto-detected {len(page_nums)} non-high pages: {page_nums}")

    total_cost = 0.0
    confidence_after = []
    for n in page_nums:
        png = PAGES / f"page_{n:02d}.png"
        if not png.exists():
            continue
        prev_data = json.loads((OUT / f"page_{n:02d}.json").read_text()) if (OUT / f"page_{n:02d}.json").exists() else {}
        prev_conf = prev_data.get("page_confidence", "?")
        print(f"page {n:02d} (was: {prev_conf}): final pass...", flush=True)
        t0 = time.time()
        try:
            data = ocr_page(png, n)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            continue
        dt = time.time() - t0

        out_file = OUT / f"page_{n:02d}.json"
        backup = OUT / f"page_{n:02d}.json.prev"
        if not backup.exists() and out_file.exists():
            shutil.copy(out_file, backup)
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        cost = data.get("_cost_usd", 0)
        total_cost += cost
        new_conf = data.get("page_confidence", "?")
        confidence_after.append((n, prev_conf, new_conf))
        sample = sorted(set(s.get("date","") for s in data.get("sessions",[])))[:3]
        print(f"  ✓ {dt:.1f}s, sessions={len(data.get('sessions',[]))}, "
              f"conf: {prev_conf} -> {new_conf}, sample={sample}, cost=${cost:.3f}", flush=True)

    print(f"\nTotal cost: ${total_cost:.2f} USD")
    print(f"\nConfidence summary:")
    upgraded = sum(1 for _,p,n in confidence_after if p != "high" and n == "high")
    print(f"  Upgraded to high: {upgraded}/{len(confidence_after)}")
    for n, prev, new in confidence_after:
        marker = "↑" if (prev != "high" and new == "high") else ("→" if prev == new else "?")
        print(f"  p{n:02d}: {prev} {marker} {new}")


if __name__ == "__main__":
    main()
