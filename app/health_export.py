"""Generate Apple Health-compatible XML for blood pressure import."""
from datetime import datetime
from xml.sax.saxutils import escape

SOURCE_NAME = "BP Tracker"
SOURCE_VERSION = "1.0"


def _ts(date_str, time_str):
    """Combine 'YYYY-MM-DD' and 'HH:MM' into Apple Health format with timezone."""
    if time_str:
        try:
            dt = datetime.fromisoformat(f"{date_str}T{time_str}:00" if len(time_str) == 5 else f"{date_str}T{time_str}")
        except ValueError:
            dt = datetime.fromisoformat(f"{date_str}T08:00:00")
    else:
        dt = datetime.fromisoformat(f"{date_str}T08:00:00")
    return dt.strftime("%Y-%m-%d %H:%M:%S +0800")


def _record(rec_type, value, unit, date_str, time_str):
    ts = _ts(date_str, time_str)
    return (
        f'<Record type="{rec_type}" sourceName="{SOURCE_NAME}" '
        f'sourceVersion="{SOURCE_VERSION}" unit="{unit}" '
        f'creationDate="{ts}" startDate="{ts}" endDate="{ts}" '
        f'value="{value}"/>'
    )


def build_xml(rows):
    """rows: list of dicts with measure_date, period, measure_time, sequence, arm,
       systolic, diastolic, pulse."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<!DOCTYPE HealthData [',
             '<!ELEMENT HealthData (ExportDate?, Me?, Record*, Workout*)>',
             '<!ELEMENT ExportDate EMPTY>',
             '<!ATTLIST ExportDate value CDATA #REQUIRED>',
             '<!ELEMENT Record EMPTY>',
             '<!ATTLIST Record',
             '  type CDATA #REQUIRED',
             '  sourceName CDATA #REQUIRED',
             '  sourceVersion CDATA #IMPLIED',
             '  unit CDATA #IMPLIED',
             '  creationDate CDATA #IMPLIED',
             '  startDate CDATA #REQUIRED',
             '  endDate CDATA #REQUIRED',
             '  value CDATA #IMPLIED>',
             ']>',
             '<HealthData locale="zh_TW">',
             f'  <ExportDate value="{datetime.now().strftime("%Y-%m-%d %H:%M:%S +0800")}"/>']

    for r in rows:
        d = r["measure_date"]
        t = r.get("measure_time") or "08:00"
        if r.get("systolic"):
            parts.append("  " + _record(
                "HKQuantityTypeIdentifierBloodPressureSystolic",
                int(r["systolic"]), "mmHg", d, t))
        if r.get("diastolic"):
            parts.append("  " + _record(
                "HKQuantityTypeIdentifierBloodPressureDiastolic",
                int(r["diastolic"]), "mmHg", d, t))
        if r.get("pulse"):
            parts.append("  " + _record(
                "HKQuantityTypeIdentifierHeartRate",
                int(r["pulse"]), "count/min", d, t))

    parts.append('</HealthData>')
    return "\n".join(parts)
