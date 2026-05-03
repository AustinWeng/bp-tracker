"""血壓資料統計分析模組。

純 Python 實作所有統計運算,不依賴 numpy / scipy,避免增加部署負擔。
所有函式皆接受 row dicts (來自 db.query) 並回傳純 dict / list,
便於在 Jinja 模板與 JS 圖表中使用。
"""

from datetime import date, datetime, timedelta
from math import sqrt


# ---------- 通用工具 ----------

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _quantile(xs, q):
    """Linear-interpolation quantile (q in [0,1])."""
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def _linear_regression(points):
    """Least-squares slope & intercept on (x, y) points. Returns (slope, intercept, r2) or (None, None, None)."""
    points = [(x, y) for x, y in points if y is not None]
    n = len(points)
    if n < 2:
        return None, None, None
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    sxx = sum(x * x for x, _ in points)
    sxy = sum(x * y for x, y in points)
    syy = sum(y * y for _, y in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None, None, None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    ss_tot = syy - sy * sy / n
    if ss_tot == 0:
        r2 = 1.0
    else:
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in points)
        r2 = 1 - ss_res / ss_tot
    return slope, intercept, r2


def _pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    mx, my = sx / n, sy / n
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den_x = sum((x - mx) ** 2 for x, _ in pairs)
    den_y = sum((y - my) ** 2 for _, y in pairs)
    if den_x == 0 or den_y == 0:
        return None
    return num / sqrt(den_x * den_y)


def _classify(sys_v, dia_v):
    """AHA/ACC 2017,任一達標即歸該級。回傳 key。"""
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


# ---------- 各項分析 ----------

def morning_evening_compare(rows):
    """晨/昏對比:平均、超標率、樣本數。"""
    am = [r for r in rows if r["period"] == "AM"]
    pm = [r for r in rows if r["period"] == "PM"]

    def stats(group):
        sys_xs = [r["systolic"] for r in group if r["systolic"] is not None]
        dia_xs = [r["diastolic"] for r in group if r["diastolic"] is not None]
        n_high = sum(1 for r in group if _classify(r["systolic"], r["diastolic"]) in ("stage1", "stage2", "crisis"))
        return {
            "n": len(group),
            "sys_mean": _mean(sys_xs),
            "dia_mean": _mean(dia_xs),
            "high_rate": (n_high / len(group)) if group else None,
        }

    return {
        "AM": stats(am),
        "PM": stats(pm),
        "diff_sys": (stats(am)["sys_mean"] - stats(pm)["sys_mean"])
                    if stats(am)["sys_mean"] is not None and stats(pm)["sys_mean"] is not None else None,
        "diff_dia": (stats(am)["dia_mean"] - stats(pm)["dia_mean"])
                    if stats(am)["dia_mean"] is not None and stats(pm)["dia_mean"] is not None else None,
    }


def left_right_diff(rows):
    """左右手差:差距 >10 mmHg 是臨床警訊。"""
    left = [r for r in rows if r["arm"] == "L"]
    right = [r for r in rows if r["arm"] == "R"]
    l_sys = _mean([r["systolic"] for r in left])
    r_sys = _mean([r["systolic"] for r in right])
    l_dia = _mean([r["diastolic"] for r in left])
    r_dia = _mean([r["diastolic"] for r in right])
    diff_sys = (l_sys - r_sys) if l_sys is not None and r_sys is not None else None
    diff_dia = (l_dia - r_dia) if l_dia is not None and r_dia is not None else None
    return {
        "L": {"n": len(left), "sys": l_sys, "dia": l_dia},
        "R": {"n": len(right), "sys": r_sys, "dia": r_dia},
        "diff_sys": diff_sys,
        "diff_dia": diff_dia,
        "warning": (abs(diff_sys) > 10 if diff_sys is not None else False)
                   or (abs(diff_dia) > 10 if diff_dia is not None else False),
    }


def weekly_regression(rows, weeks_back=12):
    """近 N 週的週平均收縮 / 舒張 + 線性回歸 slope (mmHg/week)。"""
    if not rows:
        return None
    cutoff = date.today() - timedelta(weeks=weeks_back)
    weekly = {}  # week_start (Monday) -> [sys list, dia list]
    for r in rows:
        d = r["measure_date"] if isinstance(r["measure_date"], date) else date.fromisoformat(str(r["measure_date"]))
        if d < cutoff:
            continue
        week_start = d - timedelta(days=d.weekday())
        weekly.setdefault(week_start, {"sys": [], "dia": []})
        if r["systolic"] is not None:
            weekly[week_start]["sys"].append(r["systolic"])
        if r["diastolic"] is not None:
            weekly[week_start]["dia"].append(r["diastolic"])

    if not weekly:
        return None
    sorted_weeks = sorted(weekly.keys())
    # x = week index (0,1,2...)
    sys_points = [(i, _mean(weekly[w]["sys"])) for i, w in enumerate(sorted_weeks)]
    dia_points = [(i, _mean(weekly[w]["dia"])) for i, w in enumerate(sorted_weeks)]
    sys_slope, sys_intercept, sys_r2 = _linear_regression(sys_points)
    dia_slope, dia_intercept, dia_r2 = _linear_regression(dia_points)
    return {
        "weeks": [w.isoformat() for w in sorted_weeks],
        "sys_means": [y for _, y in sys_points],
        "dia_means": [y for _, y in dia_points],
        "sys_slope": sys_slope,
        "dia_slope": dia_slope,
        "sys_r2": sys_r2,
        "dia_r2": dia_r2,
        "n_weeks": len(sorted_weeks),
    }


def seasonal_pattern(rows):
    """按月分組:看是否冬季偏高。回傳每月平均 sys/dia + 樣本數。"""
    by_month = {}  # 1..12 -> [sys, dia, count]
    for r in rows:
        d = r["measure_date"] if isinstance(r["measure_date"], date) else date.fromisoformat(str(r["measure_date"]))
        m = d.month
        by_month.setdefault(m, {"sys": [], "dia": []})
        if r["systolic"] is not None:
            by_month[m]["sys"].append(r["systolic"])
        if r["diastolic"] is not None:
            by_month[m]["dia"].append(r["diastolic"])

    months = []
    for m in range(1, 13):
        v = by_month.get(m, {"sys": [], "dia": []})
        months.append({
            "month": m,
            "sys_mean": _mean(v["sys"]),
            "dia_mean": _mean(v["dia"]),
            "n": len(v["sys"]),
        })
    has_data = sum(1 for m in months if m["n"] > 0)
    return {"months": months, "months_with_data": has_data}


def classification_distribution(rows):
    """每筆讀數的血壓分級分布(全期 + 近 30 天)。"""
    levels = ["normal", "elevated", "stage1", "stage2", "crisis"]
    cutoff = (date.today() - timedelta(days=30)).isoformat()

    def count(group):
        c = {k: 0 for k in levels}
        for r in group:
            k = _classify(r["systolic"], r["diastolic"])
            if k in c:
                c[k] += 1
        return c

    all_c = count(rows)
    recent = [r for r in rows if str(r["measure_date"]) >= cutoff]
    recent_c = count(recent)

    return {
        "levels": levels,
        "all": all_c,
        "all_total": sum(all_c.values()),
        "recent": recent_c,
        "recent_total": sum(recent_c.values()),
    }


def achievement_rate(rows, days=30):
    """達標率:近 N 天當日平均落在 <130/80 的天數比例。"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    by_date = {}
    for r in rows:
        d = str(r["measure_date"])
        if d < cutoff:
            continue
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

    return {
        "days_with_data": n_days,
        "days_in_target": n_ok,
        "rate": (n_ok / n_days) if n_days else None,
        "window_days": days,
    }


def variability_coefficient(rows, days=30):
    """變異係數 (CV = SD/mean) — 血壓穩定度指標。<10% 穩定, 10-15% 中, >15% 高。"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    sys_xs = [r["systolic"] for r in rows if r["systolic"] is not None and str(r["measure_date"]) >= cutoff]
    dia_xs = [r["diastolic"] for r in rows if r["diastolic"] is not None and str(r["measure_date"]) >= cutoff]
    sys_mean = _mean(sys_xs)
    dia_mean = _mean(dia_xs)
    sys_sd = _std(sys_xs)
    dia_sd = _std(dia_xs)
    return {
        "sys_cv": (sys_sd / sys_mean) if sys_mean and sys_sd else None,
        "dia_cv": (dia_sd / dia_mean) if dia_mean and dia_sd else None,
        "sys_mean": sys_mean,
        "dia_mean": dia_mean,
        "sys_sd": sys_sd,
        "dia_sd": dia_sd,
        "n": len(sys_xs),
        "window_days": days,
    }


def boxplot_by_combo(rows):
    """每組 (period × arm × seq) 的 [min, q1, median, q3, max] for systolic."""
    groups = {}
    for r in rows:
        if r["systolic"] is None:
            continue
        key = f"{r['period']}-{r['arm']}{r['sequence']}"
        groups.setdefault(key, []).append(r["systolic"])
    out = []
    for key in sorted(groups.keys()):
        xs = sorted(groups[key])
        if not xs:
            continue
        out.append({
            "label": key,
            "min": xs[0],
            "q1": _quantile(xs, 0.25),
            "median": _quantile(xs, 0.5),
            "q3": _quantile(xs, 0.75),
            "max": xs[-1],
            "n": len(xs),
        })
    return out


def correlations(rows, contexts):
    """收縮 vs 舒張、收縮 vs 心跳、收縮 vs 氣溫的 Pearson r。

    contexts: list of daily_context dicts {measure_date, temperature_c}
    """
    sys_dia = _pearson(
        [r["systolic"] for r in rows],
        [r["diastolic"] for r in rows],
    )
    sys_pulse = _pearson(
        [r["systolic"] for r in rows],
        [r["pulse"] for r in rows],
    )
    # 氣溫:把每筆讀數依日期 join daily_context.temperature_c
    temp_map = {str(c["measure_date"]): c["temperature_c"] for c in contexts}
    sys_xs = []
    temp_xs = []
    for r in rows:
        t = temp_map.get(str(r["measure_date"]))
        if t is not None and r["systolic"] is not None:
            sys_xs.append(r["systolic"])
            temp_xs.append(t)
    sys_temp = _pearson(sys_xs, temp_xs)
    return {
        "sys_dia": sys_dia,
        "sys_pulse": sys_pulse,
        "sys_temp": sys_temp,
        "temp_n": len(sys_xs),
    }


# ---------- 規則式自然語言摘要 ----------

def rule_based_summary(rows, contexts=None):
    """根據規則產生中文摘要句子列表。每句獨立、可挑選顯示。"""
    contexts = contexts or []
    sentences = []

    if not rows:
        return ["目前資料庫無血壓紀錄,請先匯入或新增。"]

    # 1. 整體量測規模
    n_total = len(rows)
    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()
    recent_rows = [r for r in rows if str(r["measure_date"]) >= cutoff_30]
    n_recent = len(recent_rows)
    sentences.append(f"資料庫共 {n_total} 筆讀數,近 30 天 {n_recent} 筆。")

    # 2. 近 30 天平均 + 分級
    if recent_rows:
        sys_m = _mean([r["systolic"] for r in recent_rows])
        dia_m = _mean([r["diastolic"] for r in recent_rows])
        if sys_m and dia_m:
            cls = _classify(sys_m, dia_m)
            label = {"normal": "正常", "elevated": "血壓偏高",
                     "stage1": "高血壓 1 級", "stage2": "高血壓 2 級",
                     "crisis": "高血壓危象"}.get(cls, cls)
            sentences.append(f"近 30 天平均 {sys_m:.0f}/{dia_m:.0f} mmHg → 分級「{label}」。")

    # 3. 晨/昏對比
    me = morning_evening_compare(recent_rows or rows)
    if me["diff_sys"] is not None:
        diff = me["diff_sys"]
        if diff > 5:
            sentences.append(f"晨間平均比傍晚高 {diff:.1f} mmHg,符合典型血壓晝夜節律。")
        elif diff < -5:
            sentences.append(f"傍晚平均反而比晨間高 {abs(diff):.1f} mmHg,值得留意。")
        else:
            sentences.append(f"晨/昏平均接近(差 {abs(diff):.1f} mmHg)。")

    # 4. 左右手差
    lr = left_right_diff(recent_rows or rows)
    if lr["diff_sys"] is not None:
        diff = lr["diff_sys"]
        side = "左手" if diff > 0 else "右手"
        if abs(diff) > 10:
            sentences.append(
                f"⚠ {side}收縮壓比另一側高 {abs(diff):.1f} mmHg(>10 mmHg 臨床警訊,建議向醫師反映)。"
            )
        else:
            sentences.append(f"左右手收縮壓差 {abs(diff):.1f} mmHg(<10 mmHg 屬正常範圍)。")

    # 5. 週趨勢
    wr = weekly_regression(rows, weeks_back=8)
    if wr and wr["sys_slope"] is not None and wr["n_weeks"] >= 3:
        slope = wr["sys_slope"]
        if abs(slope) < 0.3:
            sentences.append(f"近 {wr['n_weeks']} 週收縮壓走勢平穩(週變化 {slope:+.2f} mmHg)。")
        elif slope > 0:
            sentences.append(f"近 {wr['n_weeks']} 週收縮壓週均呈上升趨勢(每週 +{slope:.2f} mmHg)。")
        else:
            sentences.append(f"近 {wr['n_weeks']} 週收縮壓週均呈下降趨勢(每週 {slope:.2f} mmHg)。")

    # 6. 達標率
    ar = achievement_rate(rows, days=30)
    if ar["rate"] is not None:
        sentences.append(
            f"近 30 天達標率(當日平均 <130/80) {ar['rate']*100:.0f}% "
            f"({ar['days_in_target']}/{ar['days_with_data']} 天)。"
        )

    # 7. 變異係數
    cv = variability_coefficient(rows, days=30)
    if cv["sys_cv"] is not None:
        cv_pct = cv["sys_cv"] * 100
        if cv_pct < 10:
            level = "穩定"
        elif cv_pct < 15:
            level = "中等"
        else:
            level = "偏大"
        sentences.append(f"近 30 天收縮壓變異係數 {cv_pct:.1f}% ({level})。")

    # 8. 氣溫相關
    if contexts:
        corr = correlations(rows, contexts)
        if corr["sys_temp"] is not None and corr["temp_n"] >= 10:
            r = corr["sys_temp"]
            if abs(r) >= 0.3:
                direction = "正相關" if r > 0 else "負相關"
                sentences.append(f"收縮壓與氣溫呈{direction} (r={r:+.2f}),樣本 {corr['temp_n']} 筆。")

    return sentences
