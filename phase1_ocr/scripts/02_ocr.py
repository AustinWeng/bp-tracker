#!/usr/bin/env python3
"""OCR each page with `claude -p` (uses Max plan via OAuth) → JSON files."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "pages"
OUT = ROOT / "ocr_raw"
OUT.mkdir(parents=True, exist_ok=True)

MODEL = "opus"  # alias to claude-opus-4-7
PER_CALL_BUDGET = 1.0  # USD safety cap per page

SYSTEM_PROMPT = """你是手寫血壓記錄表的 OCR 專家。給你一頁手寫血壓記錄表的 PNG,你必須用 Read tool 讀取它然後輸出嚴格 JSON。

# 頁面結構
- 頁首可能有 DATE 欄寫民國年月,例如「114年9月」= 民國 114 年 9 月 = 西元 2025 年 9 月
- 民國轉西元:西元年 = 民國年 + 1911
- 版面可能單欄 (約 4 天/頁) 或雙欄 (約 8 天/頁)
- 雙欄頁:先讀完左欄上到下,再讀右欄上到下

# 每天的結構
- 日期標題格式「M/D」(例如 9/1) 後面接「當日氣溫°C」(例如「9/1 30」表示 9/1 氣溫 30 度)
- 後面可能有中文註記 (例如「(早起)」),歸入該天 notes
- 一天最多兩個 session:AM (上午)、PM (下午)
- 每個 session 有時間標記 (如 AM8:00、PM10:30) 和 4 筆讀數
- 一天可能只有 AM、只有 PM 或都沒 — 只輸出實際看到的,絕不編造

# 每個 Session 的 4 筆讀數 (2x2 網格)
讀取順序:
- 左上 = L1 (第一次左手)
- 右上 = R1 (第一次右手)
- 左下 = L2 (第二次左手)
- 右下 = R2 (第二次右手)
每筆讀數格式「收縮/舒張/心跳」(例如 137/92/76)

# 輸出 (嚴格 JSON,不要 ```json``` 標記,不要任何說明文字)
{
  "page_roc_year": <114 或 115 或 null>,
  "page_month": <1-12 或 null>,
  "page_confidence": "high" | "medium" | "low",
  "page_notes": "<整頁觀察>",
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
1. 字跡不清:猜測但欄位名加進 uncertain。除非完全無法判讀否則別 null
2. 完全無法判讀:該欄 null 並列入 uncertain
3. 範圍驗證:收縮 70-250、舒張 40-150、心跳 30-200。超出標 uncertain
4. 氣溫範圍:5-40°C。超出標 uncertain
5. session 不滿 4 筆讀數:只輸出實際看到的,readings 陣列可少於 4
6. session 附近的中文 (早起/飯後/頭暈/運動後) → 放該 session notes
7. 只輸出 JSON 物件本身,不要任何前後文字
"""


def extract_json_object(text: str) -> dict:
    """Extract JSON object from text that may have markdown fencing or prose."""
    text = text.strip()
    if text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    # Find first '{' and matching last '}'
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON object found in: {text[:200]}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced braces")


def ocr_page(page_path: Path, page_num: int) -> dict:
    user_prompt = (
        f"Use Read tool to load the image at this absolute path: {page_path.absolute()}\n"
        f"Then output the OCR JSON per the schema in your system prompt. "
        f"This is page {page_num} of 30. Output ONLY the JSON object, nothing else."
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

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        raise RuntimeError(f"claude CLI failed (rc={res.returncode}): {res.stderr[:500]}")

    try:
        envelope = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"failed to parse CLI envelope: {res.stdout[:500]}")

    if envelope.get("is_error"):
        raise RuntimeError(f"CLI returned error: {envelope.get('result')[:500]}")

    raw_result = envelope.get("result", "")
    try:
        data = extract_json_object(raw_result)
    except Exception as e:
        data = {"_raw": raw_result, "_error": f"json parse: {e}"}

    data["_page_num"] = page_num
    data["_cost_usd"] = envelope.get("total_cost_usd", 0)
    data["_duration_ms"] = envelope.get("duration_ms", 0)
    usage = envelope.get("usage", {})
    data["_usage"] = {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "cache_create": usage.get("cache_creation_input_tokens", 0),
    }
    return data


def main():
    pages = sorted(PAGES.glob("page_*.png"))
    if not pages:
        sys.exit(f"no pages found in {PAGES}")

    only = sys.argv[1] if len(sys.argv) > 1 else None
    total_cost = 0.0
    n_done = 0

    for p in pages:
        n = int(p.stem.split("_")[1])
        if only and only != f"{n:02d}":
            continue
        out_file = OUT / f"page_{n:02d}.json"
        if out_file.exists() and not only:
            print(f"page {n:02d}: already done, skip")
            continue

        print(f"page {n:02d}: OCR...", flush=True)
        t0 = time.time()
        try:
            data = ocr_page(p, n)
        except Exception as e:
            print(f"  ERROR page {n:02d}: {e}", flush=True)
            (OUT / f"page_{n:02d}.error.txt").write_text(str(e))
            continue
        dt = time.time() - t0

        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        n_sessions = len(data.get("sessions", []))
        conf = data.get("page_confidence", "?")
        cost = data.get("_cost_usd", 0)
        total_cost += cost
        n_done += 1
        u = data["_usage"]
        print(f"  ✓ {dt:.1f}s, sessions={n_sessions}, conf={conf}, "
              f"in={u['input']} out={u['output']} cache_r={u['cache_read']} cache_w={u['cache_create']}, "
              f"cost=${cost:.3f}, total=${total_cost:.2f}", flush=True)

    print(f"\nDone {n_done} pages. Total equivalent cost: ${total_cost:.2f} USD (Max plan: counts toward quota)")


if __name__ == "__main__":
    main()
