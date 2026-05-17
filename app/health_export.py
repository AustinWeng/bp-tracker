"""Apple Health 匯入相容的 XML 產生器。

格式重點(2026-05 升級):
- 收縮 + 舒張用 <Correlation type="HKCorrelationTypeIdentifierBloodPressure"> 包裝,
  讓 Apple 健康 app 顯示為一筆完整血壓(例如 120/80),而非分開的兩個獨立量值。
- 同一 session 的 4 筆讀數時間錯開 1 分鐘 (L1 / R1 / L2 / R2),
  避免「同一秒 4 筆」造成的圖表異常。
- 每筆 Record 附 <MetadataEntry>:arm / sequence / period / source,
  讓家人在「健康」App 點開每筆能看到「左手第 1 次 / AM / OCR」等註記。
"""
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

SOURCE_NAME = "BP Tracker"
SOURCE_VERSION = "1.2"
TIMEZONE = "+0800"   # 台灣時區,如需跨時區再做進階處理


def _attr(v):
    """Safely escape an attribute value (handles & < > ' " in metadata)."""
    return escape(str(v), {'"': "&quot;"})


def _arm_seq_offset_minutes(arm, seq):
    """Return minute offset within a session so each reading has a unique timestamp.

    Order within one session: L1 → R1 → L2 → R2 (0, 1, 2, 3 分鐘)
    """
    seq_i = int(seq) if seq is not None else 1
    base = (seq_i - 1) * 2
    return base + (0 if arm == "L" else 1)


def _session_ts(date_str, time_str):
    """Combine 'YYYY-MM-DD' and 'HH:MM' (or 'HH:MM:SS') into a datetime."""
    t = (time_str or "08:00").strip()
    if len(t) == 5:
        t = t + ":00"
    try:
        return datetime.fromisoformat(f"{date_str}T{t}")
    except ValueError:
        return datetime.fromisoformat(f"{date_str}T08:00:00")


def _fmt_ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S ") + TIMEZONE


def _metadata_entries(arm, seq, period, source, indent="      "):
    """Render <MetadataEntry> rows for a single reading."""
    entries = [
        ("HKMetadataKeyWasUserEntered", "1"),
        ("bp_arm", arm),
        ("bp_arm_label", "左手" if arm == "L" else "右手"),
        ("bp_sequence", str(int(seq)) if seq is not None else ""),
        ("bp_period", period or ""),
        ("bp_source", source or ""),
    ]
    out = []
    for k, v in entries:
        if v == "" or v is None:
            continue
        out.append(f'{indent}<MetadataEntry key="{_attr(k)}" value="{_attr(v)}"/>')
    return "\n".join(out)


def _record(rec_type, value, unit, ts_str, indent="      ", metadata_xml=""):
    """Render one <Record ...> element with optional metadata."""
    head = (
        f'{indent}<Record type="{rec_type}" sourceName="{SOURCE_NAME}" '
        f'sourceVersion="{SOURCE_VERSION}" unit="{unit}" '
        f'creationDate="{ts_str}" startDate="{ts_str}" endDate="{ts_str}" '
        f'value="{value}"'
    )
    if metadata_xml:
        return head + ">\n" + metadata_xml + f"\n{indent}</Record>"
    return head + "/>"


def build_xml(rows):
    """Build Apple Health-compatible XML.

    rows: iterable of dicts with measure_date, period, measure_time, sequence, arm,
          systolic, diastolic, pulse, source (optional).
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + TIMEZONE
    # DTD 對齊 Apple 健康 app 自己 export 出的 export.xml 格式 1:1
    # 重點:ExportDate 與 Me 為 REQUIRED (沒有 `?`),Lionheart Health Data Importer
    # 等第三方工具會嚴格檢查這兩個元素存在。
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE HealthData [',
        '<!-- HealthKit Export Version: 12 -->',
        '<!ELEMENT HealthData (ExportDate, Me, Record*, Correlation*, Workout*, ActivitySummary*, ClinicalRecord*, Audiogram*, VisionPrescription*)>',
        '<!ATTLIST HealthData',
        '  locale CDATA #REQUIRED>',
        '<!ELEMENT ExportDate EMPTY>',
        '<!ATTLIST ExportDate value CDATA #REQUIRED>',
        '<!ELEMENT Me EMPTY>',
        '<!ATTLIST Me',
        '  HKCharacteristicTypeIdentifierDateOfBirth         CDATA #IMPLIED',
        '  HKCharacteristicTypeIdentifierBiologicalSex       CDATA #IMPLIED',
        '  HKCharacteristicTypeIdentifierBloodType           CDATA #IMPLIED',
        '  HKCharacteristicTypeIdentifierFitzpatrickSkinType CDATA #IMPLIED',
        '  HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse CDATA #IMPLIED>',
        '<!ELEMENT Record (MetadataEntry|HeartRateVariabilityMetadataList)*>',
        '<!ATTLIST Record',
        '  type          CDATA #REQUIRED',
        '  unit          CDATA #IMPLIED',
        '  value         CDATA #IMPLIED',
        '  sourceName    CDATA #REQUIRED',
        '  sourceVersion CDATA #IMPLIED',
        '  device        CDATA #IMPLIED',
        '  creationDate  CDATA #IMPLIED',
        '  startDate     CDATA #REQUIRED',
        '  endDate       CDATA #REQUIRED>',
        '<!ELEMENT Correlation ((MetadataEntry|Record)*)>',
        '<!ATTLIST Correlation',
        '  type          CDATA #REQUIRED',
        '  sourceName    CDATA #REQUIRED',
        '  sourceVersion CDATA #IMPLIED',
        '  device        CDATA #IMPLIED',
        '  creationDate  CDATA #IMPLIED',
        '  startDate     CDATA #REQUIRED',
        '  endDate       CDATA #REQUIRED>',
        '<!ELEMENT MetadataEntry EMPTY>',
        '<!ATTLIST MetadataEntry',
        '  key   CDATA #REQUIRED',
        '  value CDATA #IMPLIED>',
        ']>',
        '<HealthData locale="zh_TW">',
        f' <ExportDate value="{now}"/>',
        ' <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"'
        ' HKCharacteristicTypeIdentifierBloodType="HKBloodTypeNotSet"'
        ' HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet"'
        ' HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse="None"/>',
    ]

    for r in rows:
        d = r["measure_date"]
        t = r.get("measure_time") or "08:00"
        arm = r.get("arm") or "L"
        seq = r.get("sequence") or 1
        period = r.get("period") or ""
        source = r.get("source") or ""

        session_dt = _session_ts(str(d), str(t))
        reading_dt = session_dt + timedelta(minutes=_arm_seq_offset_minutes(arm, seq))
        ts = _fmt_ts(reading_dt)

        meta_xml = _metadata_entries(arm, seq, period, source, indent="      ")

        sys_v = r.get("systolic")
        dia_v = r.get("diastolic")
        pul_v = r.get("pulse")

        # A. 收縮 + 舒張 用 Correlation 綁定為一筆完整血壓
        if sys_v is not None and dia_v is not None:
            sys_rec = _record(
                "HKQuantityTypeIdentifierBloodPressureSystolic",
                int(sys_v), "mmHg", ts, indent="      ", metadata_xml=meta_xml)
            dia_rec = _record(
                "HKQuantityTypeIdentifierBloodPressureDiastolic",
                int(dia_v), "mmHg", ts, indent="      ")
            parts.append(
                f'  <Correlation type="HKCorrelationTypeIdentifierBloodPressure" '
                f'sourceName="{SOURCE_NAME}" sourceVersion="{SOURCE_VERSION}" '
                f'creationDate="{ts}" startDate="{ts}" endDate="{ts}">'
            )
            parts.append(sys_rec)
            parts.append(dia_rec)
            parts.append("  </Correlation>")
        else:
            # 只有單邊資料 (罕見) — 退回獨立 Record
            if sys_v is not None:
                parts.append("  " + _record(
                    "HKQuantityTypeIdentifierBloodPressureSystolic",
                    int(sys_v), "mmHg", ts, indent="    ", metadata_xml=meta_xml))
            if dia_v is not None:
                parts.append("  " + _record(
                    "HKQuantityTypeIdentifierBloodPressureDiastolic",
                    int(dia_v), "mmHg", ts, indent="    ", metadata_xml=meta_xml))

        # 心跳:獨立 Record (Apple Health 規範上不放在 BP Correlation 內)
        if pul_v is not None:
            parts.append("  " + _record(
                "HKQuantityTypeIdentifierHeartRate",
                int(pul_v), "count/min", ts, indent="    ", metadata_xml=meta_xml))

    parts.append("</HealthData>")
    return "\n".join(parts)
