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

    # 算 mobile compact summary 用的 stats (TW 2022 指引)
    all_dates = sorted({r["measure_date"] for r in raw_all})
    if all_dates:
        from datetime import timedelta
        latest_d = date.fromisoformat(all_dates[-1])
        cutoff = (latest_d - timedelta(days=30)).isoformat()
        recent30 = [r for r in raw_all if r["measure_date"] >= cutoff and r.get("systolic")]
    else:
        recent30 = []

    sys_m = sum(r["systolic"] for r in recent30) / len(recent30) if recent30 else None
    dia_m = sum(r["diastolic"] for r in recent30) / len(recent30) if recent30 else None

    def classify_tw(s, d):
        if not s or not d:
            return ("unknown", "未知", "bg-slate-300 text-slate-700")
        if s >= 180 or d >= 120:
            return ("crisis", "高血壓危象", "bg-red-700 text-white")
        if s >= 140 or d >= 90:
            return ("stage2", "高血壓 2 級", "bg-red-500 text-white")
        if s >= 130 or d >= 80:
            return ("stage1", "高血壓 1 級", "bg-orange-400 text-white")
        if s >= 120:
            return ("elevated", "血壓偏高", "bg-yellow-400 text-slate-900")
        return ("normal", "正常", "bg-green-500 text-white")

    _cls_key, cls_label, cls_bg = classify_tw(sys_m, dia_m)
    avg_display = f"{round(sys_m)}/{round(dia_m)}" if sys_m and dia_m else "—"
    n_total = len(raw_all)
    date_range_str = f"{all_dates[0][:7]} ~ {all_dates[-1][:7]}" if all_dates else "—"

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
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.2.0/dist/chartjs-plugin-zoom.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/nouislider@15.7.1/dist/nouislider.min.css">
<script src="https://cdn.jsdelivr.net/npm/nouislider@15.7.1/dist/nouislider.min.js"></script>
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

  /* Compact summary card — 預設顯示,desktop 才隱藏 */
  .mobile-summary { display: block; }
  @media (min-width: 768px) {
    .mobile-summary { display: none !important; }
  }
  @media (max-width: 767px) {
    /* 隱藏 dashboard 的 4 stat cards (與「分析洞察」grid-cols-2 md:grid-cols-4 區隔) */
    section#dashboard > div.grid.grid-cols-1.md\:grid-cols-4 { display: none !important; }
    /* 隱藏分級標準表 (用 p-3 的 card),保留 mobile-summary (有 .mobile-summary class) */
    section#dashboard > div.bg-white.p-3:not(.mobile-summary) { display: none !important; }
  }

  /* Chart 區域:不啟用拖曳互動 (避免手機 scroll 干擾),範圍控制透過下方 brush */
  canvas { touch-action: auto; }

  /* Brush slider (chart 下方範圍選擇器,套用於 trend/pulse/varSys/varDia) */
  .chart-brush-wrap { margin-top: 26px; padding: 0 6px; }  /* 騰出空間給 handle tooltip,左右留邊避免 tooltip 溢出 */
  .chart-brush {
    margin: 0 24px 4px;  /* 左右 margin 加大讓 handle tooltip 不超出卡片 */
    height: 14px;
  }
  .chart-brush .noUi-connect { background: #2563eb; }
  .chart-brush .noUi-handle {
    background: #fff;
    border: 2px solid #2563eb;
    border-radius: 50%;
    width: 22px !important;
    height: 22px !important;
    right: -11px !important;
    top: -6px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    cursor: ew-resize;
  }
  .chart-brush .noUi-handle::before,
  .chart-brush .noUi-handle::after { display: none; }
  /* noUiSlider 內建 tooltip — 顯示精準日期 */
  .chart-brush .noUi-tooltip {
    background: rgba(37, 99, 235, 0.95);
    color: #fff;
    border: none;
    padding: 1px 6px;
    font-size: 9px;
    border-radius: 3px;
    bottom: 130%;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    font-weight: 600;
  }
  .chart-brush .noUi-tooltip::after {
    content: '';
    position: absolute;
    bottom: -4px;
    left: 50%;
    margin-left: -3px;
    border-width: 4px 3px 0;
    border-style: solid;
    border-color: rgba(37, 99, 235, 0.95) transparent transparent;
  }
  .chart-brush-label {
    display: flex; justify-content: space-between;
    font-size: 0.65rem; color: #64748b;
    padding: 0 6px;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
  }

  /* Brush 快速範圍 chip (在 mobile-summary 內,聯動所有 brush) */
  .brush-quick {
    padding: 2px 8px;
    border-radius: 9999px;
    border: 1px solid #cbd5e1;
    background: #fff;
    color: #475569;
    font-size: 11px;
    line-height: 1.2;
    cursor: pointer;
    transition: all 0.12s;
  }
  .brush-quick:hover { background: #f1f5f9; }
  .brush-quick.active {
    background: #2563eb;
    color: white;
    border-color: #2563eb;
  }
  @media (max-width: 767px) {
    .chart-brush .noUi-handle { width: 26px !important; height: 26px !important; right: -13px !important; top: -8px !important; }
    .chart-brush .noUi-tooltip { font-size: 10px; padding: 2px 6px; }
  }

  /* ============================================================
     Mobile overrides — 強制覆蓋 Tailwind 的 md: breakpoints
     (Tailwind CDN 載入時序不穩,用 !important 確保排版正確)
     ============================================================ */
  @media (max-width: 767px) {
    body { font-size: 14px; }
    h1 { font-size: 1.25rem !important; line-height: 1.4 !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1rem !important; line-height: 1.4 !important; }
    h3 { font-size: 0.95rem !important; }

    /* 隱藏血壓趨勢上方的 30/90/180/全部 範圍按鈕 + 自訂日期區間
       (mobile 用 mobile-summary 內的快速 chip + brush 統一管理範圍) */
    .trend-range-btn { display: none !important; }
    /* parent div 包了所有 trend-range-btn,直接整層藏 */
    .trend-range-btn:first-child,
    div:has(> .trend-range-btn) { display: none !important; }
    /* 「自訂區間」日期 picker 列也藏 */
    #dateFrom, #dateTo, #dateApplyBtn, #dateClearBtn { display: none !important; }
    div:has(> #dateFrom) { display: none !important; }

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

    /* 圖表高度 — 縱軸拉長,Y 軸資訊更明顯 */
    [style*="height: 380px"] { height: 360px !important; }
    [style*="height: 320px"] { height: 300px !important; }
    [style*="height: 280px"] { height: 260px !important; }
    [style*="height: 260px"] { height: 240px !important; }
    [style*="height: 240px"] { height: 220px !important; }
    [style*="height: 220px"] { height: 200px !important; }
    [style*="height: 130px"] { height: 130px !important; }

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
        // Mobile: 一律回全部資料 (brush + 快速 chip 控制視覺範圍,
        // 不靠 server side filter)
        if (window.matchMedia('(max-width: 767px)').matches) {
          return Promise.resolve({ ok: true, status: 200, json: async () => rows });
        }
        // Desktop: 仍照 days/from/to 過濾 (因 trend-range-btn 仍顯示)
        const fr = q.get('from'), to = q.get('to');
        const days = parseInt(q.get('days') || '30');
        if (fr && to) {
          rows = rows.filter(r => r.measure_date >= fr && r.measure_date <= to);
        } else if (days > 0 && days < 9999) {
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

  // 設定 Chart.js 全域 zoom/pan plugin 預設 (chartjs-plugin-zoom 載入後自動 register)
  function __applyChartDefaults() {
    if (typeof Chart === 'undefined') return setTimeout(__applyChartDefaults, 30);
    // chartjs-plugin-zoom UMD 載入後會自動 register,我們只設 defaults
    Chart.defaults.plugins = Chart.defaults.plugins || {};

    // Mobile: 縮小 chart 字型 (X/Y axis ticks, legend, tooltip)
    const isMobile = window.matchMedia('(max-width: 767px)').matches;
    if (isMobile) {
      Chart.defaults.font.size = 9;
      // legend 與 tooltip 字略大,易讀
      Chart.defaults.plugins.legend = Chart.defaults.plugins.legend || {};
      Chart.defaults.plugins.legend.labels = Chart.defaults.plugins.legend.labels || {};
      Chart.defaults.plugins.legend.labels.boxWidth = 10;
      Chart.defaults.plugins.legend.labels.font = { size: 10 };
      Chart.defaults.plugins.tooltip = Chart.defaults.plugins.tooltip || {};
      Chart.defaults.plugins.tooltip.titleFont = { size: 11 };
      Chart.defaults.plugins.tooltip.bodyFont = { size: 11 };
    }

    // 全部 disable — 手機上 pinch/wheel/pan 會干擾頁面 scroll
    // 範圍控制全部交由底下 brush slider 處理
    Chart.defaults.plugins.zoom = {
      pan: { enabled: false },
      zoom: {
        wheel: { enabled: false },
        pinch: { enabled: false },
        drag: { enabled: false },
      },
    };
    // 雙擊 chart → 4 個 brush 全部 reset 到完整範圍 (透過聯動自動同步)
    document.addEventListener('dblclick', (e) => {
      const canvas = e.target.closest && e.target.closest('canvas');
      if (!canvas) return;
      const brushEl = document.getElementById(canvas.id + '-brush');
      const chart = Chart.getChart(canvas);
      if (brushEl && brushEl.noUiSlider && chart) {
        const total = chart.data.labels.length;
        brushEl.noUiSlider.set([0, total - 1]); // 觸發聯動 → 其他 brush 也 reset
      }
    });
  }
  __applyChartDefaults();

  // ----- Brush range slider 通用 inject -----
  // 套用於所有 X 軸是時序的 chart (dashboard + analytics 的 weeklyChart)
  const __BRUSH_CHARTS = ['trendChart', 'pulseChart', 'varSysChart', 'varDiaChart', 'weeklyChart'];
  let __brushSyncing = false;

  // 按「日曆天」找出 labels 中對應「最後 N 天」起點 index
  // (而非「最後 N 個 data points」,避免資料稀疏時誤判)
  function __dateIndexCutoff(labels, daysFromEnd) {
    if (!labels || !labels.length) return 0;
    const lastIso = labels[labels.length - 1];
    const cutoff = new Date(lastIso);
    cutoff.setDate(cutoff.getDate() - daysFromEnd + 1);
    const cutoffIso = cutoff.toISOString().slice(0, 10);
    const idx = labels.findIndex(l => l >= cutoffIso);
    return idx < 0 ? 0 : idx;
  }

  // 即時更新 mobile-summary 內的「目前範圍」狀態
  function __updateBrushStatus() {
    const brushEl = document.getElementById('trendChart-brush');
    const canvas = document.getElementById('trendChart');
    if (!brushEl || !brushEl.noUiSlider || !canvas) return;
    const chart = Chart.getChart(canvas);
    if (!chart) return;
    const values = brushEl.noUiSlider.get(true);
    const s = Math.round(values[0]);
    const e = Math.round(values[1]);
    const labels = chart.data.labels;
    const fromLabel = labels[s];
    const toLabel = labels[e];
    if (!fromLabel || !toLabel) return;
    const fromD = new Date(fromLabel);
    const toD = new Date(toLabel);
    const dayCount = Math.round((toD - fromD) / 86400000) + 1;
    const statusEl = document.getElementById('brush-status');
    if (statusEl) {
      statusEl.textContent = `${fromLabel.slice(5)} ~ ${toLabel.slice(5)} (${dayCount} 天)`;
    }
    // 更新 quick chip active 狀態 (按日曆天比對)
    const total = labels.length;
    document.querySelectorAll('.brush-quick').forEach(btn => {
      const d = parseInt(btn.dataset.days);
      const expectS = d === 0 ? 0 : __dateIndexCutoff(labels, d);
      btn.classList.toggle('active', s === expectS && e === total - 1);
    });
  }

  function __injectBrush(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return false;
    const chart = Chart.getChart(canvas);
    if (!chart || !chart.data.labels || chart.data.labels.length < 2) return false;
    if (document.getElementById(canvasId + '-brush')) return true; // 已 inject

    const container = canvas.closest('div[style*="height"]') || canvas.parentElement;
    if (!container) return false;

    const labels = chart.data.labels;
    const total = labels.length;
    // 預設「最近 30 天日曆」對應 index (非最後 30 個 data points)
    const initStart = __dateIndexCutoff(labels, 30);

    const wrap = document.createElement('div');
    wrap.id = canvasId + '-brush-wrap';
    wrap.className = 'chart-brush-wrap';
    wrap.innerHTML = `
      <div id="${canvasId}-brush" class="chart-brush"></div>
      <div class="chart-brush-label">
        <span id="${canvasId}-brush-from">${labels[initStart] || ''}</span>
        <span class="text-blue-600">↔ 拖兩端把手選範圍</span>
        <span id="${canvasId}-brush-to">${labels[total - 1] || ''}</span>
      </div>
    `;
    container.parentNode.insertBefore(wrap, container.nextSibling);

    const brushEl = document.getElementById(canvasId + '-brush');
    noUiSlider.create(brushEl, {
      start: [initStart, total - 1],
      connect: true,
      range: { min: 0, max: total - 1 },
      step: 1,
      margin: 1,
      behaviour: 'tap-drag',
      tooltips: [
        { to: i => (labels[Math.round(i)] || '').slice(5), from: Number },  // MM-DD 短格式
        { to: i => (labels[Math.round(i)] || '').slice(5), from: Number },
      ],
    });

    function applyRange() {
      const values = brushEl.noUiSlider.get(true);
      let s = Math.round(values[0]);
      let e = Math.round(values[1]);
      const lbls = chart.data.labels;
      if (s < 0) s = 0;
      if (e > lbls.length - 1) e = lbls.length - 1;
      const fromEl = document.getElementById(canvasId + '-brush-from');
      const toEl = document.getElementById(canvasId + '-brush-to');
      if (fromEl) fromEl.textContent = lbls[s] || '';
      if (toEl) toEl.textContent = lbls[e] || '';
      __brushSyncing = true;
      chart.options.scales.x.min = s;
      chart.options.scales.x.max = e;
      chart.update('none');
      __brushSyncing = false;

      // 聯動:把目前範圍同步到其他 chart 的 brush
      // 用 label (日期字串) 對應,避免不同 chart labels 長度不一
      if (!__activeBrushSync) {
        __activeBrushSync = true;
        const fromLabel = lbls[s];
        const toLabel = lbls[e];
        __BRUSH_CHARTS.forEach(otherId => {
          if (otherId === canvasId) return;
          const otherBrushEl = document.getElementById(otherId + '-brush');
          const otherCanvas = document.getElementById(otherId);
          if (!otherBrushEl || !otherBrushEl.noUiSlider || !otherCanvas) return;
          const otherChart = Chart.getChart(otherCanvas);
          if (!otherChart) return;
          const otherLabels = otherChart.data.labels;
          const otherTotal = otherLabels.length;
          if (otherTotal < 2) return;
          // 先試直接 indexOf,失敗 fallback 到比例對應
          let otherS = otherLabels.indexOf(fromLabel);
          let otherE = otherLabels.indexOf(toLabel);
          if (otherS < 0 || otherE < 0) {
            otherS = Math.max(0, Math.min(Math.round((s / lbls.length) * otherTotal), otherTotal - 1));
            otherE = Math.max(0, Math.min(Math.round((e / lbls.length) * otherTotal), otherTotal - 1));
          }
          if (otherS >= otherE) otherE = Math.min(otherS + 1, otherTotal - 1);
          otherBrushEl.noUiSlider.set([otherS, otherE]);
        });
        __activeBrushSync = false;
      }
    }

    brushEl.noUiSlider.on('update', () => {
      applyRange();
      __updateBrushStatus();
    });
    applyRange();
    return true;
  }

  // 聯動 flag — 避免無窮迴圈:當一個 brush 被聯動觸發時,其 handler 不再 propagate
  let __activeBrushSync = false;

  // 註冊快速範圍 chip 點擊 (聯動所有 brush)
  function __registerQuickChips() {
    document.querySelectorAll('.brush-quick').forEach(btn => {
      btn.addEventListener('click', () => {
        const days = parseInt(btn.dataset.days);
        const brushEl = document.getElementById('trendChart-brush');
        const canvas = document.getElementById('trendChart');
        if (!brushEl || !brushEl.noUiSlider || !canvas) return;
        const chart = Chart.getChart(canvas);
        if (!chart) return;
        const labels = chart.data.labels;
        const total = labels.length;
        const e = total - 1;
        // 按「最後 N 天日曆」找對應 index (非最後 N 個 data points)
        const s = days <= 0 ? 0 : __dateIndexCutoff(labels, days);
        brushEl.noUiSlider.set([s, e]); // 透過聯動帶動其他 brush
      });
    });
  }
  setTimeout(__registerQuickChips, 800);
  setTimeout(__updateBrushStatus, 1000);
  // (mobile 不再需要 force loadData(9999):fetch override 已直接回全部資料)

  // 啟動完成後 force 一次 brush 預設範圍 (最近 30 天日曆),
  // 避免 chart loadData race condition 讓 brushSync 設到不完整範圍
  setTimeout(() => {
    if (!window.matchMedia('(max-width: 767px)').matches) return;
    const brushEl = document.getElementById('trendChart-brush');
    const canvas = document.getElementById('trendChart');
    if (!brushEl || !brushEl.noUiSlider || !canvas) return;
    const chart = Chart.getChart(canvas);
    if (!chart) return;
    const labels = chart.data.labels;
    if (labels.length < 2) return;
    brushEl.noUiSlider.set([__dateIndexCutoff(labels, 30), labels.length - 1]);
  }, 1800);

  function __injectAllBrushes() {
    if (typeof Chart === 'undefined' || typeof noUiSlider === 'undefined') {
      return setTimeout(__injectAllBrushes, 100);
    }
    let allDone = true;
    __BRUSH_CHARTS.forEach(id => {
      if (!__injectBrush(id)) allDone = false;
    });
    if (!allDone) setTimeout(__injectAllBrushes, 300);
  }

  // 監聽 chart afterUpdate, 當 labels 變化時 (例如切 30/90/180/全部) 自動同步 brush
  function __registerBrushSync() {
    if (typeof Chart === 'undefined') return setTimeout(__registerBrushSync, 50);
    Chart.register({
      id: 'brushSync',
      afterUpdate(chart) {
        if (__brushSyncing) return;
        const canvasId = chart.canvas.id;
        if (!__BRUSH_CHARTS.includes(canvasId)) return;
        const brushEl = document.getElementById(canvasId + '-brush');
        if (!brushEl || !brushEl.noUiSlider) return;
        const total = chart.data.labels.length;
        if (total < 2) return;
        const opts = brushEl.noUiSlider.options;
        if (opts.range.max !== total - 1) {
          // labels 變了, update slider range + tooltip formatter (用日曆 30 天)
          const newLabels = chart.data.labels;
          brushEl.noUiSlider.updateOptions({
            start: [__dateIndexCutoff(newLabels, 30), total - 1],
            range: { min: 0, max: total - 1 },
            tooltips: [
              { to: i => (newLabels[Math.round(i)] || '').slice(5), from: Number },
              { to: i => (newLabels[Math.round(i)] || '').slice(5), from: Number },
            ],
          }, true);
        }
      },
    });
  }
  __registerBrushSync();
  setTimeout(__injectAllBrushes, 600);

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

<!-- Mobile compact summary (取代原本 4 stat cards + 分級標準表) -->
<div class="mobile-summary bg-white rounded-lg p-3 mb-3 border border-slate-200">
  <div class="flex items-center justify-between gap-3">
    <div>
      <div class="text-3xl font-bold num leading-none">__AVG_DISPLAY__</div>
      <div class="text-[10px] text-slate-400 mt-1">近 30 天平均 mmHg</div>
    </div>
    <div class="text-right">
      <div class="inline-block rounded px-2 py-1 text-xs font-medium __CLS_BG__">__CLS_LABEL__</div>
      <div class="text-[10px] text-slate-400 num mt-1">__N_TOTAL__ 筆 · __DATE_RANGE__</div>
    </div>
  </div>
  <details class="mt-2 text-xs border-t border-slate-100 pt-2">
    <summary class="text-slate-500 cursor-pointer">📐 查看血壓分級標準 (TW 2022)</summary>
    <div class="mt-2 grid grid-cols-2 gap-1 text-[10px]">
      <div class="rounded p-1.5 bg-green-500 text-white"><b>正常</b><br>&lt; 120 / &lt; 80</div>
      <div class="rounded p-1.5 bg-yellow-400"><b>偏高</b><br>120-129 / &lt; 80</div>
      <div class="rounded p-1.5 bg-orange-400 text-white"><b>1 級</b><br>130-139 / 80-89</div>
      <div class="rounded p-1.5 bg-red-500 text-white"><b>2 級</b><br>≥ 140 / ≥ 90</div>
      <div class="rounded p-1.5 bg-red-700 text-white col-span-2 text-center"><b>危象</b> ≥ 180 / ≥ 120</div>
    </div>
  </details>
  <!-- Brush 快速範圍 chip + 即時狀態 (所有 chart 聯動) -->
  <div class="mt-2 pt-2 border-t border-slate-100">
    <div class="flex items-center flex-wrap gap-1.5 text-[11px]">
      <span class="text-slate-500">範圍:</span>
      <button type="button" class="brush-quick" data-days="7">7天</button>
      <button type="button" class="brush-quick" data-days="14">14天</button>
      <button type="button" class="brush-quick" data-days="30">30天</button>
      <button type="button" class="brush-quick" data-days="90">90天</button>
      <button type="button" class="brush-quick" data-days="0">全部</button>
      <span id="brush-status" class="ml-auto text-blue-600 font-medium num text-[10px]">—</span>
    </div>
    <div class="text-[10px] text-slate-400 mt-1.5">
      💡 拖任一圖表下方藍色 bar 兩端可改變範圍 (5 張圖聯動),雙擊圖表重置
    </div>
  </div>
</div>

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
    html = html.replace("__AVG_DISPLAY__", avg_display)
    html = html.replace("__CLS_LABEL__", cls_label)
    html = html.replace("__CLS_BG__", cls_bg)
    html = html.replace("__N_TOTAL__", f"{n_total:,}")
    html = html.replace("__DATE_RANGE__", date_range_str)

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
