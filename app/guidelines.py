"""血壓分級指引模組。

支援三套指引,皆為**居家量測**情境下的判讀。
classify(sys, dia) 回傳 level key,levels() 回傳該指引的分級表 (給 UI 渲染)。

居家量測門檻一般比診間嚴格 -5 mmHg (例如 ESC 診間 140/90 → 居家 135/85)。
本系統使用者皆為居家量測,故各指引的門檻在「分級顏色」與「分布計算」沿用
診間門檻(這在 OmronConnect / Apple Health / Withings 等家用 app 都是一樣作法),
讓視覺化結果跟使用者熟悉的 app 一致。
"""

# Internal level keys (順序 = 嚴重度遞增)
LEVELS_AHA = ["normal", "elevated", "stage1", "stage2", "crisis"]
LEVELS_ESC = ["optimal", "normal", "high_normal", "grade1", "grade2", "grade3"]
LEVELS_TW = ["normal", "elevated", "stage1", "stage2", "crisis"]


def _classify_aha2017(sys_v, dia_v):
    """AHA/ACC 2017 (US) — 130/80 threshold."""
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


def _classify_esc2018(sys_v, dia_v):
    """ESC/ESH 2018 (Europe) — 140/90 threshold for hypertension."""
    if sys_v is None or dia_v is None:
        return "unknown"
    if sys_v >= 180 or dia_v >= 110:
        return "grade3"
    if sys_v >= 160 or dia_v >= 100:
        return "grade2"
    if sys_v >= 140 or dia_v >= 90:
        return "grade1"
    if sys_v >= 130 or dia_v >= 85:
        return "high_normal"
    if sys_v >= 120 or dia_v >= 80:
        return "normal"
    return "optimal"


def _classify_tw2022(sys_v, dia_v):
    """台灣高血壓學會 2022 — 沿用 130/80 門檻 (與 AHA 一致)。

    與 AHA 主要差異在「治療目標」(高心血管風險族群目標 <120/80,SPRINT 證據),
    但分級門檻一致,故底層直接重用 AHA 函式。
    """
    return _classify_aha2017(sys_v, dia_v)


# Per-guideline metadata for UI rendering.
# Each entry: id, label, classifier, levels list (key/label/sys range/dia range/color class),
# and `target_systolic`/`target_diastolic` used for "達標率" calculation.

GUIDELINES = {
    "aha2017": {
        "id": "aha2017",
        "label": "AHA/ACC 2017 (美國)",
        "short": "AHA",
        "classify": _classify_aha2017,
        "target_sys": 130,
        "target_dia": 80,
        "levels": [
            ("normal",   "正常",         "< 120",     "< 80",      "bg-green-500 text-white"),
            ("elevated", "血壓偏高",     "120 – 129", "< 80",      "bg-yellow-400"),
            ("stage1",   "高血壓 1 級",  "130 – 139", "80 – 89",   "bg-orange-400 text-white"),
            ("stage2",   "高血壓 2 級",  "≥ 140",     "≥ 90",      "bg-red-500 text-white"),
            ("crisis",   "高血壓危象",   "≥ 180",     "≥ 120",     "bg-red-700 text-white"),
        ],
    },
    "esc2018": {
        "id": "esc2018",
        "label": "ESC/ESH 2018 (歐洲)",
        "short": "ESC",
        "classify": _classify_esc2018,
        "target_sys": 140,
        "target_dia": 90,
        "levels": [
            ("optimal",      "理想",         "< 120",     "< 80",      "bg-green-600 text-white"),
            ("normal",       "正常",         "120 – 129", "80 – 84",   "bg-green-400 text-white"),
            ("high_normal",  "正常偏高",     "130 – 139", "85 – 89",   "bg-yellow-400"),
            ("grade1",       "高血壓 1 級",  "140 – 159", "90 – 99",   "bg-orange-400 text-white"),
            ("grade2",       "高血壓 2 級",  "160 – 179", "100 – 109", "bg-red-500 text-white"),
            ("grade3",       "高血壓 3 級",  "≥ 180",     "≥ 110",     "bg-red-700 text-white"),
        ],
    },
    "tw2022": {
        "id": "tw2022",
        "label": "台灣高血壓學會 2022",
        "short": "TW",
        "classify": _classify_tw2022,
        "target_sys": 130,
        "target_dia": 80,
        "levels": [
            ("normal",   "正常",         "< 120",     "< 80",      "bg-green-500 text-white"),
            ("elevated", "血壓偏高",     "120 – 129", "< 80",      "bg-yellow-400"),
            ("stage1",   "高血壓 1 級",  "130 – 139", "80 – 89",   "bg-orange-400 text-white"),
            ("stage2",   "高血壓 2 級",  "≥ 140",     "≥ 90",      "bg-red-500 text-white"),
            ("crisis",   "高血壓危象",   "≥ 180",     "≥ 120",     "bg-red-700 text-white"),
        ],
    },
}

DEFAULT_GUIDELINE = "tw2022"


def get(guideline_id: str) -> dict:
    """Return guideline dict by id, falling back to default."""
    return GUIDELINES.get(guideline_id) or GUIDELINES[DEFAULT_GUIDELINE]


def classify(sys_v, dia_v, guideline_id: str = DEFAULT_GUIDELINE) -> str:
    """Classify a single (sys, dia) reading by the chosen guideline."""
    return get(guideline_id)["classify"](sys_v, dia_v)


def level_label(level_key: str, guideline_id: str = DEFAULT_GUIDELINE) -> str:
    """Look up the human label for a level key under a guideline."""
    g = get(guideline_id)
    for k, label, *_ in g["levels"]:
        if k == level_key:
            return label
    return level_key


def all_options():
    """For settings page dropdown: [(id, label), ...] in display order."""
    return [(gid, g["label"]) for gid, g in GUIDELINES.items()]
