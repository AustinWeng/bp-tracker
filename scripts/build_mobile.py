#!/usr/bin/env python3
"""產生 self-contained mobile.html — 手機離線可用的血壓資料瀏覽頁。

從 phase2_db/bp.db 讀全部讀數,inline 進 HTML,使用者可:
  - AirDrop / 雲端 同步到手機
  - Safari 開啟 → 加到主畫面 → 隨時離線看

執行方式:
    cd <bp-tracker root>
    python3 scripts/build_mobile.py
產出: <root>/mobile.html
"""

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "phase2_db" / "bp.db"
OUT = ROOT / "mobile.html"


# ---------- 統計工具 (微型版,獨立於 app.analytics) ----------

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _classify_tw(sys_v, dia_v):
    """台灣高血壓學會 2022 / AHA 2017 (130/80)。"""
    if sys_v is None or dia_v is None:
        return "unknown"
    if sys_v >= 180 or dia_v >= 120:
        return "crisis"
    if sys_v >= 140 or dia_v >= 90:
        return "stage2"
    if sys_v >= 130 or dia_v >= 80:
        return "stage1"
    if sys_v >= 120:
        return "elevated"
    return "normal"


LEVEL_LABELS = {
    "normal": "正常", "elevated": "偏高",
    "stage1": "1 級", "stage2": "2 級", "crisis": "危象",
    "unknown": "未知",
}
LEVEL_COLORS = {
    "normal": "#16a34a", "elevated": "#facc15",
    "stage1": "#fb923c", "stage2": "#ef4444", "crisis": "#7f1d1d",
    "unknown": "#94a3b8",
}


# ---------- 讀 DB ----------

def load_data():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("""
        SELECT measure_date, period, measure_time, sequence, arm,
               systolic, diastolic, pulse, notes, source
        FROM bp_records
        WHERE systolic IS NOT NULL
        ORDER BY measure_date, period, sequence, arm
    """)]
    contexts = {r["measure_date"]: r["temperature_c"]
                for r in conn.execute(
                    "SELECT measure_date, temperature_c FROM daily_context "
                    "WHERE temperature_c IS NOT NULL")}
    conn.close()
    return rows, contexts


# ---------- 計算所有 stats ----------

def compute_stats(rows, contexts):
    today_iso = date.today().isoformat()
    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
    cutoff_90 = (date.today() - timedelta(days=90)).isoformat()

    recent30 = [r for r in rows if str(r["measure_date"]) >= cutoff_30]
    recent90 = [r for r in rows if str(r["measure_date"]) >= cutoff_90]

    # 整體規模
    lo = min((str(r["measure_date"]) for r in rows), default=None)
    hi = max((str(r["measure_date"]) for r in rows), default=None)

    # 近 30 天平均
    avg30_sys = _mean([r["systolic"] for r in recent30])
    avg30_dia = _mean([r["diastolic"] for r in recent30])
    avg30_pul = _mean([r["pulse"] for r in recent30])
    cls = _classify_tw(avg30_sys, avg30_dia)

    # 變異係數
    sd_sys = _std([r["systolic"] for r in recent30])
    cv_sys = (sd_sys / avg30_sys) if avg30_sys and sd_sys else None

    # 達標率(當日平均 < 130/80,30 天)
    by_date = {}
    for r in recent30:
        d = str(r["measure_date"])
        by_date.setdefault(d, {"sys": [], "dia": []})
        if r["systolic"] is not None:
            by_date[d]["sys"].append(r["systolic"])
        if r["diastolic"] is not None:
            by_date[d]["dia"].append(r["diastolic"])
    n_days = 0
    n_ok = 0
    for d, v in by_date.items():
        if not v["sys"] or not v["dia"]:
            continue
        n_days += 1
        if _mean(v["sys"]) < 130 and _mean(v["dia"]) < 80:
            n_ok += 1
    ach_rate = (n_ok / n_days) if n_days else None

    # 分級分布(全期 + 30 天)
    def count(group):
        c = {k: 0 for k in ("normal", "elevated", "stage1", "stage2", "crisis")}
        for r in group:
            k = _classify_tw(r["systolic"], r["diastolic"])
            if k in c:
                c[k] += 1
        return c
    dist_all = count(rows)
    dist_30 = count(recent30)

    # 晨/昏對比
    am30 = [r for r in recent30 if r["period"] == "AM"]
    pm30 = [r for r in recent30 if r["period"] == "PM"]
    am_sys = _mean([r["systolic"] for r in am30])
    pm_sys = _mean([r["systolic"] for r in pm30])
    am_dia = _mean([r["diastolic"] for r in am30])
    pm_dia = _mean([r["diastolic"] for r in pm30])

    # 左右手差
    left = [r for r in recent30 if r["arm"] == "L"]
    right = [r for r in recent30 if r["arm"] == "R"]
    l_sys = _mean([r["systolic"] for r in left])
    r_sys = _mean([r["systolic"] for r in right])
    diff_sys = (l_sys - r_sys) if l_sys is not None and r_sys is not None else None

    # 日均資料 (給趨勢圖) — 全期
    by_d = {}
    for r in rows:
        d = str(r["measure_date"])
        by_d.setdefault(d, {"sys": [], "dia": [], "pul": []})
        if r["systolic"] is not None:
            by_d[d]["sys"].append(r["systolic"])
        if r["diastolic"] is not None:
            by_d[d]["dia"].append(r["diastolic"])
        if r["pulse"] is not None:
            by_d[d]["pul"].append(r["pulse"])
    daily = [{
        "date": d,
        "sys": round(_mean(v["sys"]), 1) if v["sys"] else None,
        "dia": round(_mean(v["dia"]), 1) if v["dia"] else None,
        "pul": round(_mean(v["pul"]), 1) if v["pul"] else None,
    } for d, v in sorted(by_d.items())]

    # 規則式摘要
    summary = build_summary(
        rows, recent30, avg30_sys, avg30_dia,
        am_sys, pm_sys, diff_sys, ach_rate, n_ok, n_days, cv_sys,
    )

    return {
        "n_total": len(rows),
        "date_range": {"lo": lo, "hi": hi},
        "avg30": {
            "sys": round(avg30_sys, 1) if avg30_sys else None,
            "dia": round(avg30_dia, 1) if avg30_dia else None,
            "pul": round(avg30_pul, 1) if avg30_pul else None,
        },
        "classification": cls,
        "classification_label": LEVEL_LABELS[cls],
        "achievement": {
            "rate": ach_rate,
            "ok": n_ok, "days": n_days,
        },
        "cv_sys": cv_sys,
        "morning_evening": {
            "am_sys": round(am_sys, 1) if am_sys else None,
            "pm_sys": round(pm_sys, 1) if pm_sys else None,
            "am_dia": round(am_dia, 1) if am_dia else None,
            "pm_dia": round(pm_dia, 1) if pm_dia else None,
        },
        "left_right": {
            "l_sys": round(l_sys, 1) if l_sys else None,
            "r_sys": round(r_sys, 1) if r_sys else None,
            "diff_sys": round(diff_sys, 1) if diff_sys is not None else None,
            "warning": (abs(diff_sys) > 10) if diff_sys is not None else False,
        },
        "distribution": {"all": dist_all, "recent30": dist_30},
        "daily": daily,
        "summary": summary,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def build_summary(rows, recent30, avg_sys, avg_dia, am_sys, pm_sys,
                  diff_sys, ach_rate, n_ok, n_days, cv_sys):
    lines = []
    lines.append(f"資料庫共 {len(rows)} 筆,近 30 天 {len(recent30)} 筆 (TW 2022 指引)。")
    if avg_sys and avg_dia:
        cls = _classify_tw(avg_sys, avg_dia)
        lines.append(f"近 30 天平均 {avg_sys:.0f}/{avg_dia:.0f} mmHg → 分級「{LEVEL_LABELS[cls]}」。")
    if am_sys and pm_sys:
        diff = am_sys - pm_sys
        if diff > 5:
            lines.append(f"晨間比傍晚高 {diff:.1f} mmHg (符合典型晝夜節律)。")
        elif diff < -5:
            lines.append(f"傍晚比晨間高 {abs(diff):.1f} mmHg (值得留意)。")
        else:
            lines.append(f"晨/昏接近 (差 {abs(diff):.1f} mmHg)。")
    if diff_sys is not None:
        if abs(diff_sys) > 10:
            side = "左手" if diff_sys > 0 else "右手"
            lines.append(f"⚠ {side}收縮壓比另一側高 {abs(diff_sys):.1f} mmHg(>10 mmHg 臨床警訊)。")
        else:
            lines.append(f"左右手收縮壓差 {abs(diff_sys):.1f} mmHg (< 10 屬正常)。")
    if ach_rate is not None:
        lines.append(f"近 30 天達標率 (< 130/80) {ach_rate*100:.0f}% ({n_ok}/{n_days} 天)。")
    if cv_sys is not None:
        cv_pct = cv_sys * 100
        level = "穩定" if cv_pct < 10 else ("中等" if cv_pct < 15 else "偏大")
        lines.append(f"近 30 天收縮壓變異係數 {cv_pct:.1f}% ({level})。")
    return lines


# ---------- HTML 渲染 ----------

HTML_TEMPLATE = r"""<!DOCTYPE html>
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
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Microsoft JhengHei", sans-serif; }
  .num { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
  .stat-num { font-size: 1.75rem; line-height: 2rem; }
  .scroll-x { scrollbar-width: thin; -webkit-overflow-scrolling: touch; }
  details > summary { list-style: none; cursor: pointer; }
  details > summary::-webkit-details-marker { display: none; }
  .clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
</head>
<body class="bg-slate-50 text-slate-900 pb-12">

<header class="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200 px-4 py-3 flex items-center justify-between">
  <div>
    <div class="font-bold text-base">血壓記錄</div>
    <div class="text-xs text-slate-500">最近 30 天 · TW 2022 指引</div>
  </div>
  <div class="text-xs text-slate-400 text-right">
    <div>產生於</div><div class="num">__GENERATED_AT__</div>
  </div>
</header>

<main class="px-3 py-3 space-y-4 max-w-2xl mx-auto">

<!-- Hero stats 2x2 -->
<section class="grid grid-cols-2 gap-2">
  <div class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
    <div class="text-xs text-slate-500">近 30 天平均</div>
    <div class="stat-num num font-bold mt-1" id="card-avg">—</div>
    <div class="text-xs text-slate-400 num">心跳 <span id="card-pul">—</span> bpm</div>
  </div>
  <div class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
    <div class="text-xs text-slate-500">血壓分級</div>
    <div class="mt-1 inline-block rounded px-2 py-1 font-medium text-sm" id="card-cls">—</div>
    <div class="text-xs text-slate-400 mt-1">近 30 天</div>
  </div>
  <div class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
    <div class="text-xs text-slate-500">達標率 <span class="text-slate-400">&lt; 130/80</span></div>
    <div class="stat-num num font-bold mt-1" id="card-ach">—</div>
    <div class="text-xs text-slate-400 num"><span id="card-ach-days">—</span> 天</div>
  </div>
  <div class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
    <div class="text-xs text-slate-500">變異係數</div>
    <div class="stat-num num font-bold mt-1" id="card-cv">—</div>
    <div class="text-xs text-slate-400 num" id="card-cv-label">—</div>
  </div>
</section>

<!-- 自動摘要 -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
  <div class="font-medium text-sm mb-2 flex items-center gap-2">📝 自動摘要</div>
  <ul id="summary-list" class="text-sm space-y-1 text-slate-700"></ul>
</section>

<!-- 趨勢圖 -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
  <div class="flex items-center justify-between mb-2">
    <div class="font-medium text-sm">血壓趨勢</div>
    <div class="flex gap-1 text-xs">
      <button data-range="30" class="range-btn px-2 py-1 rounded bg-blue-100 text-blue-700 font-medium">30 天</button>
      <button data-range="90" class="range-btn px-2 py-1 rounded text-slate-500">90 天</button>
      <button data-range="all" class="range-btn px-2 py-1 rounded text-slate-500">全部</button>
    </div>
  </div>
  <div style="height: 240px;"><canvas id="trendChart"></canvas></div>
</section>

<!-- 晨 vs 昏 -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
  <div class="font-medium text-sm mb-2">晨 vs 昏</div>
  <div class="grid grid-cols-2 gap-3 text-sm">
    <div class="bg-orange-50 rounded p-2">
      <div class="text-xs text-orange-700 font-medium">AM 晨間</div>
      <div class="num text-lg font-bold mt-1" id="me-am">—</div>
    </div>
    <div class="bg-indigo-50 rounded p-2">
      <div class="text-xs text-indigo-700 font-medium">PM 傍晚</div>
      <div class="num text-lg font-bold mt-1" id="me-pm">—</div>
    </div>
  </div>
</section>

<!-- 左 vs 右 -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200" id="lr-section">
  <div class="font-medium text-sm mb-2">左 vs 右</div>
  <div class="text-sm" id="lr-content">—</div>
</section>

<!-- 分級分布 -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
  <div class="font-medium text-sm mb-2">分級分布</div>
  <div class="grid grid-cols-2 gap-3">
    <div>
      <div class="text-xs text-slate-500 mb-1">全期 (<span id="dist-all-n" class="num">0</span>)</div>
      <div style="height: 130px;"><canvas id="distAllChart"></canvas></div>
    </div>
    <div>
      <div class="text-xs text-slate-500 mb-1">近 30 天 (<span id="dist-30-n" class="num">0</span>)</div>
      <div style="height: 130px;"><canvas id="dist30Chart"></canvas></div>
    </div>
  </div>
</section>

<!-- 完整紀錄 (按日折疊) -->
<section class="bg-white rounded-xl p-3 shadow-sm border border-slate-200">
  <details>
    <summary class="font-medium text-sm flex items-center justify-between">
      <span>完整紀錄</span>
      <span class="text-xs text-slate-400">點開展開 <span id="recs-total" class="num">0</span> 筆</span>
    </summary>
    <div class="mt-3 max-h-[60vh] overflow-y-auto scroll-x divide-y divide-slate-100" id="recs-list"></div>
  </details>
</section>

<footer class="text-center text-xs text-slate-400 pt-2">
  <div>資料範圍: <span class="num" id="date-range">—</span></div>
  <div class="mt-1">bp-tracker · 離線單檔版 (mobile.html)</div>
</footer>

</main>

<script>
const DATA = __DATA_JSON__;
const LEVEL_LABELS = __LEVEL_LABELS__;
const LEVEL_COLORS = __LEVEL_COLORS__;
const COLOR_CLASS_FOR_LEVEL = {
  normal:'bg-green-500 text-white',
  elevated:'bg-yellow-400 text-slate-900',
  stage1:'bg-orange-400 text-white',
  stage2:'bg-red-500 text-white',
  crisis:'bg-red-700 text-white',
  unknown:'bg-slate-300 text-slate-700',
};

// --- Render hero stats ---
const avg = DATA.avg30;
document.getElementById('card-avg').textContent = (avg.sys && avg.dia) ? `${Math.round(avg.sys)}/${Math.round(avg.dia)}` : '—';
document.getElementById('card-pul').textContent = avg.pul ? Math.round(avg.pul) : '—';

const clsBadge = document.getElementById('card-cls');
clsBadge.textContent = DATA.classification_label;
clsBadge.className = 'mt-1 inline-block rounded px-2 py-1 font-medium text-sm ' + COLOR_CLASS_FOR_LEVEL[DATA.classification];

const ach = DATA.achievement;
const achPct = ach.rate !== null ? Math.round(ach.rate * 100) : null;
const achEl = document.getElementById('card-ach');
achEl.textContent = achPct !== null ? `${achPct}%` : '—';
achEl.className = 'stat-num num font-bold mt-1 ' + (
  achPct === null ? '' :
  achPct >= 70 ? 'text-green-600' :
  achPct >= 40 ? 'text-amber-600' : 'text-red-600'
);
document.getElementById('card-ach-days').textContent = `${ach.ok}/${ach.days}`;

const cv = DATA.cv_sys;
const cvPct = cv !== null ? (cv * 100) : null;
const cvEl = document.getElementById('card-cv');
cvEl.textContent = cvPct !== null ? `${cvPct.toFixed(1)}%` : '—';
cvEl.className = 'stat-num num font-bold mt-1 ' + (
  cvPct === null ? '' :
  cvPct < 10 ? 'text-green-600' :
  cvPct < 15 ? 'text-amber-600' : 'text-red-600'
);
document.getElementById('card-cv-label').textContent =
  cvPct === null ? '—' :
  cvPct < 10 ? '穩定' : cvPct < 15 ? '中等' : '偏大';

// --- Summary ---
const sumUl = document.getElementById('summary-list');
DATA.summary.forEach(s => {
  const li = document.createElement('li');
  li.className = 'flex gap-2';
  li.innerHTML = '<span class="text-slate-400 shrink-0">·</span><span>' + s.replace(/</g,'&lt;') + '</span>';
  sumUl.appendChild(li);
});

// --- 晨/昏 ---
const me = DATA.morning_evening;
document.getElementById('me-am').textContent = (me.am_sys && me.am_dia) ? `${Math.round(me.am_sys)}/${Math.round(me.am_dia)}` : '—';
document.getElementById('me-pm').textContent = (me.pm_sys && me.pm_dia) ? `${Math.round(me.pm_sys)}/${Math.round(me.pm_dia)}` : '—';

// --- 左右手 ---
const lr = DATA.left_right;
const lrEl = document.getElementById('lr-content');
const lrSection = document.getElementById('lr-section');
if (lr.l_sys !== null && lr.r_sys !== null) {
  const diff = lr.diff_sys;
  const side = diff > 0 ? '左手' : (diff < 0 ? '右手' : '');
  lrEl.innerHTML = `
    <div class="flex justify-around">
      <div class="text-center"><div class="text-xs text-slate-500">左手</div><div class="num text-lg font-bold">${Math.round(lr.l_sys)}</div></div>
      <div class="text-center"><div class="text-xs text-slate-500">右手</div><div class="num text-lg font-bold">${Math.round(lr.r_sys)}</div></div>
      <div class="text-center"><div class="text-xs text-slate-500">差</div><div class="num text-lg font-bold ${lr.warning?'text-red-600':''}">${diff > 0 ? '+' : ''}${Math.round(diff)}</div></div>
    </div>
    <div class="text-xs mt-2 ${lr.warning?'text-red-700 font-medium':'text-slate-500'}">${lr.warning ? `⚠ ${side}高 >10 mmHg (臨床警訊,請告知醫師)` : `差 ≤ 10 mmHg 屬正常`}</div>
  `;
  if (lr.warning) lrSection.className += ' bg-red-50 border-red-300';
} else {
  lrEl.textContent = '資料不足';
}

// --- 趨勢圖 ---
let trendChart = null;
function drawTrend(range) {
  let data = DATA.daily;
  if (range !== 'all') {
    const days = parseInt(range);
    data = data.slice(-days);
  }
  const labels = data.map(d => d.date.slice(5)); // MM-DD
  const sys = data.map(d => d.sys);
  const dia = data.map(d => d.dia);
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {label:'收縮', data:sys, borderColor:'#dc2626', backgroundColor:'#dc262633', tension:0.2, pointRadius:1.5, spanGaps:true, borderWidth:2},
        {label:'舒張', data:dia, borderColor:'#2563eb', backgroundColor:'#2563eb33', tension:0.2, pointRadius:1.5, spanGaps:true, borderWidth:2, borderDash:[4,2]},
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: {mode:'index', intersect:false},
      scales: {
        y: {min: 50, max: 180, ticks: {font: {size: 10}}},
        x: {ticks: {font: {size: 9}, maxTicksLimit: 8}},
      },
      plugins: {legend: {labels: {boxWidth: 12, font: {size: 11}}, position: 'bottom'}}
    }
  });
}
document.querySelectorAll('.range-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.range-btn').forEach(x => {
      x.classList.remove('bg-blue-100', 'text-blue-700', 'font-medium');
      x.classList.add('text-slate-500');
    });
    b.classList.remove('text-slate-500');
    b.classList.add('bg-blue-100', 'text-blue-700', 'font-medium');
    drawTrend(b.dataset.range);
  });
});
drawTrend('30');

// --- 分級分布 (donut) ---
function donut(canvasId, counts) {
  const order = ['normal','elevated','stage1','stage2','crisis'];
  const total = order.reduce((s,k) => s + (counts[k]||0), 0);
  document.getElementById(canvasId + '-n')?.appendChild;
  return new Chart(document.getElementById(canvasId), {
    type: 'doughnut',
    data: {
      labels: order.map(k => LEVEL_LABELS[k]),
      datasets: [{
        data: order.map(k => counts[k] || 0),
        backgroundColor: order.map(k => LEVEL_COLORS[k]),
        borderWidth: 1,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '60%',
      plugins: {
        legend: {display: false},
        tooltip: {callbacks: {label: (ctx) => {
          const pct = total ? (ctx.parsed * 100 / total).toFixed(0) : 0;
          return `${ctx.label}: ${ctx.parsed} (${pct}%)`;
        }}}
      }
    }
  });
}
document.getElementById('dist-all-n').textContent = Object.values(DATA.distribution.all).reduce((a,b)=>a+b,0);
document.getElementById('dist-30-n').textContent = Object.values(DATA.distribution.recent30).reduce((a,b)=>a+b,0);
donut('distAllChart', DATA.distribution.all);
donut('dist30Chart', DATA.distribution.recent30);

// --- 完整紀錄 (按日 group) ---
const recs = DATA.records;
document.getElementById('recs-total').textContent = recs.length;
const byDate = {};
recs.forEach(r => {
  (byDate[r.measure_date] = byDate[r.measure_date] || []).push(r);
});
const dates = Object.keys(byDate).sort().reverse();
const recsList = document.getElementById('recs-list');
dates.forEach(d => {
  const group = byDate[d];
  const div = document.createElement('div');
  div.className = 'py-2';
  const headerHtml = `<div class="font-medium text-sm num">${d} <span class="text-xs text-slate-400 font-normal">(${group.length} 筆)</span></div>`;
  const rowsHtml = group.map(r => {
    const k = (r.systolic && r.diastolic) ? (
      r.systolic >= 180 || r.diastolic >= 120 ? 'crisis' :
      r.systolic >= 140 || r.diastolic >= 90 ? 'stage2' :
      r.systolic >= 130 || r.diastolic >= 80 ? 'stage1' :
      r.systolic >= 120 ? 'elevated' : 'normal'
    ) : 'unknown';
    const dot = `<span class="inline-block w-2 h-2 rounded-full" style="background:${LEVEL_COLORS[k]}"></span>`;
    return `<div class="flex items-center gap-2 text-xs py-0.5">
      ${dot}
      <span class="text-slate-500 w-12">${r.period} ${r.arm}${r.sequence}</span>
      <span class="num font-medium">${r.systolic}/${r.diastolic}</span>
      <span class="text-slate-400 num">心 ${r.pulse}</span>
      <span class="text-slate-400 ml-auto text-[10px]">${r.source}</span>
    </div>`;
  }).join('');
  div.innerHTML = headerHtml + rowsHtml;
  recsList.appendChild(div);
});

// Footer
document.getElementById('date-range').textContent = `${DATA.date_range.lo} ~ ${DATA.date_range.hi}`;
</script>

</body>
</html>
"""


# ---------- 主流程 ----------

def main():
    if not DB.exists():
        print(f"[X] DB not found: {DB}", file=sys.stderr)
        sys.exit(1)

    rows, contexts = load_data()
    stats = compute_stats(rows, contexts)

    # 把 records 一起塞進 stats (給「完整紀錄」section)
    stats["records"] = rows

    html = HTML_TEMPLATE
    html = html.replace("__DATA_JSON__", json.dumps(stats, ensure_ascii=False, separators=(",", ":")))
    html = html.replace("__LEVEL_LABELS__", json.dumps(LEVEL_LABELS, ensure_ascii=False))
    html = html.replace("__LEVEL_COLORS__", json.dumps(LEVEL_COLORS))
    html = html.replace("__GENERATED_AT__", stats["generated_at"])

    OUT.write_text(html, encoding="utf-8")
    print(f"[OK] Wrote {OUT}")
    print(f"     size: {OUT.stat().st_size / 1024:.1f} KB")
    print(f"     records: {stats['n_total']}")
    print(f"     range: {stats['date_range']['lo']} ~ {stats['date_range']['hi']}")


if __name__ == "__main__":
    main()
