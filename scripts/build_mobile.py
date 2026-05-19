#!/usr/bin/env python3
"""完整版 mobile.html — 1:1 對齊現有 Flask web app 的 dashboard + analytics + records。

從 Flask test_client 抓現有 server-rendered HTML,把 fetch API 改為讀 inline data,
產出 self-contained 單檔 mobile.html (手機離線可用,內容跟主 web app 一致)。

執行方式:
    cd <bp-tracker root>
    python3 scripts/build_mobile.py
產出: <root>/mobile.html
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

OUT = ROOT / "mobile.html"


# 把 server-render 後的內容裡指向其他頁面的 link 改成 anchor (#section) 或 disabled
def fix_links(html: str) -> str:
    # 主頁面 anchor mapping
    html = re.sub(r'href="/"(?=[\s>])', 'href="#dashboard"', html)
    html = re.sub(r'href="/records[^"]*"', 'href="#records"', html)
    html = re.sub(r'href="/analytics[^"]*"', 'href="#analytics"', html)
    # 沒收進 mobile.html 的頁面 (add/edit/delete/export/reimport/settings) → 變成提示
    html = re.sub(
        r'<a href="/(add|export|reimport|settings|edit/\d+|delete/\d+)[^"]*"',
        r'<a href="#" data-disabled-mobile="1"',
        html,
    )
    return html


def extract_main(html: str) -> str:
    m = re.search(r'<main[^>]*>(.*?)</main>', html, re.DOTALL)
    return m.group(1).strip() if m else ""


def main():
    app = create_app()
    client = app.test_client()

    # 抓三頁 server-rendered HTML
    pages = {}
    for path in ("/", "/records", "/analytics"):
        r = client.get(path)
        if r.status_code != 200:
            print(f"[X] GET {path} failed: HTTP {r.status_code}", file=sys.stderr)
            sys.exit(1)
        pages[path] = r.get_data(as_text=True)

    dashboard_main = fix_links(extract_main(pages["/"]))
    records_main = fix_links(extract_main(pages["/records"]))
    analytics_main = fix_links(extract_main(pages["/analytics"]))

    # 抓所有需要的 API JSON (全量,讓 client-side filter 用)
    raw_all = json.loads(client.get("/api/raw?days=9999").data)
    date_range = json.loads(client.get("/api/date_range").data)
    recent_table = json.loads(client.get("/api/recent_table?days=30").data)
    sessions_all = json.loads(client.get("/api/sessions?days=9999").data)
    daily_all = json.loads(client.get("/api/daily?days=9999").data)
    analytics_data = json.loads(client.get("/api/analytics").data)

    inline = {
        "raw_all": raw_all,
        "date_range": date_range,
        "recent_table": recent_table,
        "sessions_all": sessions_all,
        "daily_all": daily_all,
        "analytics": analytics_data,
    }

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    template = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="血壓">
<meta name="theme-color" content="#dc2626">
<title>血壓記錄</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Microsoft JhengHei", sans-serif; }
  .num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }

  /* Filter chips */
  .filter-chip {
    padding: 4px 12px; border-radius: 9999px; border: 1px solid #cbd5e1;
    font-size: 0.75rem; background: #f8fafc; color: #475569; transition: all 0.15s;
  }
  .filter-chip.active { background: #2563eb; color: white; border-color: #2563eb; }

  /* row highlight (從 dashboard 跳到 records 用) */
  .row-focused {
    background: linear-gradient(90deg, rgba(251,191,36,0.35) 0%, rgba(251,191,36,0.18) 100%) !important;
    border-left: 4px solid #f59e0b;
    animation: rowPulse 1.4s ease-out 2;
  }
  @keyframes rowPulse {
    0%   { box-shadow: 0 0 0 0 rgba(245,158,11,0.6); }
    60%  { box-shadow: 0 0 0 8px rgba(245,158,11,0); }
    100% { box-shadow: 0 0 0 0 rgba(245,158,11,0); }
  }
  section[id] { scroll-margin-top: 56px; }

  /* ============================================================
     Mobile overrides — 強制覆蓋 Tailwind 的 md: breakpoints
     (Tailwind CDN 載入時序不穩,用 !important 確保排版正確)
     ============================================================ */
  @media (max-width: 767px) {
    body { font-size: 14px; }
    h1 { font-size: 1.25rem !important; line-height: 1.4 !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1rem !important; line-height: 1.4 !important; }
    h3 { font-size: 0.95rem !important; }

    /* 所有 grid 強制塌欄 (覆蓋 Tailwind md:grid-cols-N) */
    .grid.grid-cols-1 { grid-template-columns: 1fr !important; }
    [class*="md:grid-cols-2"] { grid-template-columns: 1fr !important; }
    [class*="md:grid-cols-3"] { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
    [class*="md:grid-cols-4"] { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
    [class*="md:grid-cols-5"] { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
    /* 5 級分級標準表 — 強制 2x3 而不是 5 並排 */
    .grid.grid-cols-2.md\:grid-cols-5 { grid-template-columns: repeat(2, 1fr) !important; }

    /* Padding 緊縮 */
    main { padding-left: 8px !important; padding-right: 8px !important; padding-top: 8px !important; }
    .max-w-6xl { padding-left: 0 !important; padding-right: 0 !important; }
    .p-4, .p-5, .p-6 { padding: 0.75rem !important; }
    .p-3 { padding: 0.625rem !important; }
    .mb-6 { margin-bottom: 1rem !important; }
    .gap-4 { gap: 0.5rem !important; }

    /* Cards 字體 */
    .text-2xl { font-size: 1.25rem !important; }
    .text-lg { font-size: 1rem !important; }
    .text-sm { font-size: 0.8rem !important; }
    .text-xs { font-size: 0.7rem !important; }

    /* 圖表高度縮小 */
    [style*="height: 380px"] { height: 240px !important; }
    [style*="height: 320px"] { height: 220px !important; }
    [style*="height: 280px"] { height: 200px !important; }
    [style*="height: 260px"] { height: 180px !important; }
    [style*="height: 240px"] { height: 180px !important; }
    [style*="height: 220px"] { height: 160px !important; }
    [style*="height: 130px"] { height: 110px !important; }

    /* Canvas 永遠不超寬 */
    canvas { max-width: 100% !important; }

    /* Filter chips 字小 */
    .filter-chip { font-size: 0.7rem !important; padding: 3px 8px !important; }

    /* Buttons 字小 */
    button { font-size: 0.75rem !important; }

    /* Tables — 含 records 與 dashboard 的最新一次量測 */
    table { font-size: 0.7rem !important; }
    th, td { padding: 3px 4px !important; }
    /* 超長 notes 折行 */
    .max-w-\[200px\] { max-width: 100px !important; }
    .truncate { white-space: normal !important; word-break: break-all; }

    /* Records table 不要 overflow,直接內滑 */
    .overflow-x-auto { overflow-x: auto !important; -webkit-overflow-scrolling: touch; }

    /* 分級標準表的彩色卡 padding 緊 */
    .grid-cols-2 > div.border-2 { padding: 0.375rem !important; }

    /* nav: 避免 nav 內元素換行,可橫滑 */
    nav .max-w-6xl { overflow-x: auto; -webkit-overflow-scrolling: touch; }

    /* 隱藏「離線 · datetime」之類非必要訊息以節省 nav 空間 */
    nav .ml-auto { display: none; }
  }

  /* 極小螢幕 (< 380px,iPhone Mini 之類) */
  @media (max-width: 380px) {
    body { font-size: 13px; }
    [class*="md:grid-cols-3"] { grid-template-columns: 1fr !important; }
    .text-2xl { font-size: 1.1rem !important; }
    /* 心跳圖跟最新量測 → 強制單欄 */
    .grid.grid-cols-1.md\:grid-cols-2 { grid-template-columns: 1fr !important; }
  }
</style>
<script>
  // 把 fetch API 改成讀 inline data,讓現有 server-render 出來的 JS 不用改也能跑
  const __INLINE = __INLINE_PLACEHOLDER__;
  const __origFetch = window.fetch;
  window.fetch = function(url, opts) {
    try {
      const u = new URL(url, location.href);
      const p = u.pathname;
      const q = u.searchParams;
      if (p === '/api/raw') {
        let rows = __INLINE.raw_all;
        const fr = q.get('from'), to = q.get('to');
        const days = parseInt(q.get('days') || '30');
        if (fr && to) {
          rows = rows.filter(r => r.measure_date >= fr && r.measure_date <= to);
        } else if (days > 0 && days < 9999) {
          // 從最新資料倒推 N 天 (不從 today,因為 mobile.html 是 snapshot)
          const dates = __INLINE.raw_all.map(r => r.measure_date).sort();
          if (dates.length) {
            const lastD = new Date(dates[dates.length - 1]);
            lastD.setDate(lastD.getDate() - days);
            const ci = lastD.toISOString().slice(0, 10);
            rows = rows.filter(r => r.measure_date >= ci);
          }
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => rows });
      }
      if (p === '/api/date_range') {
        return Promise.resolve({ ok: true, status: 200, json: async () => __INLINE.date_range });
      }
      if (p === '/api/recent_table') {
        return Promise.resolve({ ok: true, status: 200, json: async () => __INLINE.recent_table });
      }
      if (p === '/api/sessions') {
        return Promise.resolve({ ok: true, status: 200, json: async () => __INLINE.sessions_all });
      }
      if (p === '/api/daily') {
        return Promise.resolve({ ok: true, status: 200, json: async () => __INLINE.daily_all });
      }
      if (p === '/api/analytics') {
        return Promise.resolve({ ok: true, status: 200, json: async () => __INLINE.analytics });
      }
    } catch (e) {}
    return __origFetch(url, opts);
  };

  // 攔截「點圖表跳轉到記錄頁」改成 scroll 到 #records section + 高亮該日
  document.addEventListener('DOMContentLoaded', () => {
    // 把 window.location.href = '/records?focus=YYYY-MM-DD' 改成 anchor scroll
    const origHref = Object.getOwnPropertyDescriptor(window.Location.prototype, 'href');
    Object.defineProperty(window.location, 'href', {
      set: function(v) {
        if (typeof v === 'string' && v.startsWith('/records?focus=')) {
          const m = v.match(/focus=([0-9-]+)/);
          if (m) {
            const date = m[1];
            // 找對應 row 並高亮 + scroll
            document.querySelectorAll('#records tr.row-focused').forEach(t => t.classList.remove('row-focused'));
            const rows = document.querySelectorAll(`#records tr[data-date="${date}"]`);
            rows.forEach(r => r.classList.add('row-focused'));
            if (rows.length) rows[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
          }
        }
        origHref.set.call(this, v);
      },
      get: function() { return origHref.get.call(this); },
    });

    // 點 data-disabled-mobile 的 link 顯示提示
    document.querySelectorAll('[data-disabled-mobile]').forEach(a => {
      a.addEventListener('click', e => {
        e.preventDefault();
        alert('此功能(新增/編輯/匯出/重匯入/設定)僅限主 web app。\n請在 Mac 上啟動 server 後使用。');
      });
    });
  });
</script>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen">

<nav class="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
  <div class="max-w-6xl mx-auto px-3 py-2 flex items-center gap-2 text-sm">
    <span class="font-bold text-blue-700">📊 血壓</span>
    <a href="#dashboard" class="px-2 py-1 rounded bg-blue-50 text-blue-700">儀表板</a>
    <a href="#analytics" class="px-2 py-1 rounded hover:bg-blue-50">分析</a>
    <a href="#records" class="px-2 py-1 rounded hover:bg-blue-50">紀錄</a>
    <div class="ml-auto text-[10px] text-slate-400 hidden sm:block">__GENERATED_AT__</div>
  </div>
</nav>

<main class="max-w-6xl mx-auto px-3 py-3 space-y-6">

<section id="dashboard">
__DASHBOARD_MAIN__
</section>

<section id="analytics" class="border-t border-slate-200 pt-6">
<h1 class="text-2xl font-bold mb-3">📊 進階分析</h1>
__ANALYTICS_MAIN_INNER__
</section>

<section id="records" class="border-t border-slate-200 pt-6">
__RECORDS_MAIN__
</section>

</main>

<div class="text-center text-xs text-slate-400 py-4 border-t border-slate-200">
  bp-tracker · 離線單檔版 (mobile.html) · 產生於 __GENERATED_AT__
</div>

</body>
</html>"""

    # /analytics 頁面開頭已有 <h1>📊 進階分析</h1>,避免重複,改為「inner only」
    analytics_inner = re.sub(
        r'<div class="flex items-center justify-between mb-4">.*?</div>',
        '',
        analytics_main,
        count=1,
        flags=re.DOTALL,
    )

    # records.html 的 table 1575 行對手機渲染太重,加 default hidden + 「載入完整紀錄」按鈕
    # 在 records_main 的 <table> 之前 inject 一個 details 包起來
    records_main = re.sub(
        r'<div class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-x-auto">\s*<table',
        '<details><summary class="cursor-pointer bg-blue-50 hover:bg-blue-100 text-blue-800 '
        'rounded px-3 py-2 my-2 text-sm font-medium">點此載入完整紀錄表格 '
        '(<span class="num">1575+</span> 筆,需 1-2 秒)</summary>'
        '<div class="bg-white rounded-lg shadow-sm border border-slate-200 overflow-x-auto mt-2">'
        '<table',
        records_main,
        count=1,
    )
    records_main = records_main.replace('</table>\n</div>', '</table></div></details>', 1)

    html = template.replace(
        "__INLINE_PLACEHOLDER__",
        json.dumps(inline, ensure_ascii=False, separators=(",", ":")),
    )
    html = html.replace("__DASHBOARD_MAIN__", dashboard_main)
    html = html.replace("__ANALYTICS_MAIN_INNER__", analytics_inner)
    html = html.replace("__RECORDS_MAIN__", records_main)
    html = html.replace("__GENERATED_AT__", generated_at)

    OUT.write_text(html, encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"[OK] Wrote {OUT}")
    print(f"     size: {size_kb:.1f} KB")
    print(f"     dashboard main: {len(dashboard_main)} chars")
    print(f"     analytics main: {len(analytics_inner)} chars")
    print(f"     records main:   {len(records_main)} chars")
    print(f"     inline data:    {sum(len(json.dumps(v)) for v in inline.values())} chars")


if __name__ == "__main__":
    main()
