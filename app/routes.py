import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for, Response

from . import db
from . import health_export
from . import analytics
from . import guidelines


def classify_bp(sys_v, dia_v, guideline_id=None):
    """Classify (sys, dia) using the chosen (or current) guideline."""
    gid = guideline_id or getattr(g, "guideline_id", guidelines.DEFAULT_GUIDELINE)
    key = guidelines.classify(sys_v, dia_v, gid)
    label = guidelines.level_label(key, gid) if key != "unknown" else "未知"
    return (key, label)


def get_session_means(days_back=None):
    """Return list of session means: one row per (date, period)."""
    where = ""
    params = []
    if days_back:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        where = "WHERE measure_date >= ?"
        params = [cutoff]
    sql = f"""
        SELECT measure_date, period, measure_time,
               AVG(systolic) AS systolic,
               AVG(diastolic) AS diastolic,
               AVG(pulse) AS pulse,
               COUNT(*) AS n_readings
        FROM bp_records
        {where}
        GROUP BY measure_date, period, measure_time
        ORDER BY measure_date, period
    """
    return db.query(sql, params)


def get_daily_means(days_back=None):
    where = ""
    params = []
    if days_back:
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        where = "WHERE measure_date >= ?"
        params = [cutoff]
    sql = f"""
        SELECT measure_date,
               AVG(systolic) AS systolic,
               AVG(diastolic) AS diastolic,
               AVG(pulse) AS pulse,
               MIN(systolic) AS min_sys,
               MAX(systolic) AS max_sys,
               COUNT(*) AS n_readings
        FROM bp_records
        WHERE systolic IS NOT NULL {('AND ' + where[6:]) if where else ''}
        GROUP BY measure_date
        ORDER BY measure_date
    """
    if where:
        sql = sql.replace(where[6:], "measure_date >= ?")
    return db.query(sql, params)


def register(app):

    @app.route("/")
    def dashboard():
        # Recent 30-day overview
        means = get_daily_means(days_back=30)
        if not means:
            # No data in last 30 days, fall back to most recent
            all_dates = db.query("SELECT MAX(measure_date) AS d FROM bp_records")
            latest = all_dates[0]["d"] if all_dates and all_dates[0]["d"] else None
            means = []

        # Latest reading
        latest = db.query("""
            SELECT measure_date, period, measure_time, systolic, diastolic, pulse, sequence, arm, source
            FROM bp_records
            ORDER BY measure_date DESC, period DESC, sequence DESC
            LIMIT 8
        """)
        latest_session = None
        if latest:
            d = latest[0]["measure_date"]
            p = latest[0]["period"]
            latest_session = [r for r in latest if r["measure_date"] == d and r["period"] == p]

        # Stats
        total = db.query("SELECT COUNT(*) AS n FROM bp_records")[0]["n"]
        days = db.query("SELECT COUNT(DISTINCT measure_date) AS n FROM bp_records")[0]["n"]
        date_range = db.query("SELECT MIN(measure_date) AS lo, MAX(measure_date) AS hi FROM bp_records")[0]
        ocr_v1_n = db.query("SELECT COUNT(*) AS n FROM bp_records WHERE source = 'ocr_v1'")[0]["n"]

        # Overall mean (last 30 days)
        recent_avg = db.query("""
            SELECT AVG(systolic) AS s, AVG(diastolic) AS d, AVG(pulse) AS p
            FROM bp_records
            WHERE measure_date >= date('now', '-30 days')
        """)
        avg = recent_avg[0] if recent_avg else {"s": None, "d": None, "p": None}
        cls, cls_label = classify_bp(avg["s"], avg["d"])
        gid = g.guideline_id

        # Phase 3 — 分析卡片資料 (近 30 天為主)
        recent_rows = db.query("""
            SELECT measure_date, period, sequence, arm, systolic, diastolic, pulse
            FROM bp_records
            WHERE measure_date >= date('now', '-30 days')
              AND systolic IS NOT NULL
            ORDER BY measure_date, period, sequence, arm
        """)
        all_rows = db.query("""
            SELECT measure_date, period, sequence, arm, systolic, diastolic, pulse
            FROM bp_records
            WHERE systolic IS NOT NULL
            ORDER BY measure_date
        """)
        contexts = db.query("SELECT measure_date, temperature_c FROM daily_context WHERE temperature_c IS NOT NULL")

        insights = {
            "morning_evening": analytics.morning_evening_compare(recent_rows, guideline_id=gid),
            "left_right": analytics.left_right_diff(recent_rows),
            "weekly_trend": analytics.weekly_regression(all_rows, weeks_back=12),
            "achievement": analytics.achievement_rate(all_rows, days=30, guideline_id=gid),
            "summary": analytics.rule_based_summary(all_rows, contexts, guideline_id=gid),
        }

        return render_template("dashboard.html",
                               total=total, days=days,
                               date_range=date_range,
                               ocr_v1_n=ocr_v1_n,
                               avg=avg, classification=cls, classification_label=cls_label,
                               latest_session=latest_session,
                               insights=insights)

    @app.route("/analytics")
    def analytics_page():
        all_rows = db.query("""
            SELECT measure_date, period, sequence, arm, systolic, diastolic, pulse
            FROM bp_records
            WHERE systolic IS NOT NULL
            ORDER BY measure_date, period, sequence, arm
        """)
        contexts = db.query("SELECT measure_date, temperature_c FROM daily_context WHERE temperature_c IS NOT NULL")
        gid = g.guideline_id

        data = {
            "morning_evening": analytics.morning_evening_compare(all_rows, guideline_id=gid),
            "left_right": analytics.left_right_diff(all_rows),
            "weekly_trend": analytics.weekly_regression(all_rows, weeks_back=24),
            "seasonal": analytics.seasonal_pattern(all_rows),
            "distribution": analytics.classification_distribution(all_rows, guideline_id=gid),
            "achievement_30": analytics.achievement_rate(all_rows, days=30, guideline_id=gid),
            "achievement_90": analytics.achievement_rate(all_rows, days=90, guideline_id=gid),
            "cv_30": analytics.variability_coefficient(all_rows, days=30),
            "cv_90": analytics.variability_coefficient(all_rows, days=90),
            "boxplot": analytics.boxplot_by_combo(all_rows),
            "correlations": analytics.correlations(all_rows, contexts),
            "summary": analytics.rule_based_summary(all_rows, contexts, guideline_id=gid),
            "n_total": len(all_rows),
        }
        return render_template("analytics.html", data=data)

    @app.route("/api/analytics")
    def api_analytics():
        """JSON 版,供其他工具或前端 dynamic refresh 使用。"""
        all_rows = db.query("""
            SELECT measure_date, period, sequence, arm, systolic, diastolic, pulse
            FROM bp_records WHERE systolic IS NOT NULL ORDER BY measure_date
        """)
        contexts = db.query("SELECT measure_date, temperature_c FROM daily_context WHERE temperature_c IS NOT NULL")
        gid = g.guideline_id
        return jsonify({
            "guideline": gid,
            "morning_evening": analytics.morning_evening_compare(all_rows, guideline_id=gid),
            "left_right": analytics.left_right_diff(all_rows),
            "weekly_trend": analytics.weekly_regression(all_rows, weeks_back=24),
            "seasonal": analytics.seasonal_pattern(all_rows),
            "distribution": analytics.classification_distribution(all_rows, guideline_id=gid),
            "achievement_30": analytics.achievement_rate(all_rows, days=30, guideline_id=gid),
            "cv_30": analytics.variability_coefficient(all_rows, days=30),
            "boxplot": analytics.boxplot_by_combo(all_rows),
            "correlations": analytics.correlations(all_rows, contexts),
            "summary": analytics.rule_based_summary(all_rows, contexts, guideline_id=gid),
        })

    @app.route("/settings", methods=["GET", "POST"])
    def settings_page():
        if request.method == "POST":
            new_gid = request.form.get("guideline", "").strip()
            if new_gid not in {gid for gid, _ in guidelines.all_options()}:
                abort(400, "未知的 guideline")
            db.set_setting("bp_guideline", new_gid)
            return redirect(url_for("settings_page", saved=1))
        saved = request.args.get("saved") == "1"
        return render_template("settings.html",
                               current_id=g.guideline_id,
                               current=g.guideline,
                               options=guidelines.all_options(),
                               all_guidelines_meta=guidelines.GUIDELINES,
                               saved=saved)

    @app.route("/records")
    def records_list():
        rows = db.query("""
            SELECT id, measure_date, period, measure_time, sequence, arm,
                   systolic, diastolic, pulse, notes, source, source_ref
            FROM bp_records
            ORDER BY measure_date DESC, period DESC, sequence ASC, arm ASC
        """)
        return render_template("records.html", rows=rows, total=len(rows))

    @app.route("/add", methods=["GET", "POST"])
    def add_record():
        if request.method == "POST":
            date_v = request.form["measure_date"]
            period = request.form["period"]
            time_v = request.form.get("measure_time") or None
            temp = request.form.get("temperature_c")
            notes = request.form.get("notes", "").strip()

            try:
                temp_f = float(temp) if temp else None
            except ValueError:
                temp_f = None

            inserted = 0
            for seq in (1, 2):
                for arm in ("L", "R"):
                    s_key = f"{arm}{seq}_sys"
                    d_key = f"{arm}{seq}_dia"
                    p_key = f"{arm}{seq}_pul"
                    sys_v = request.form.get(s_key)
                    dia_v = request.form.get(d_key)
                    pul_v = request.form.get(p_key)
                    if not (sys_v and dia_v and pul_v):
                        continue
                    db.execute("""
                        INSERT OR REPLACE INTO bp_records
                        (user_id, measure_date, period, measure_time, sequence, arm,
                         systolic, diastolic, pulse, notes, source)
                        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')
                    """, (date_v, period, time_v, seq, arm,
                          int(sys_v), int(dia_v), int(pul_v), notes))
                    inserted += 1

            if temp_f is not None:
                db.execute("""
                    INSERT INTO daily_context(user_id, measure_date, temperature_c)
                    VALUES (1, ?, ?)
                    ON CONFLICT(user_id, measure_date) DO UPDATE SET temperature_c = excluded.temperature_c
                """, (date_v, temp_f))

            return redirect(url_for("records_list"))

        # GET: prefill date/time, load last entry as quick-repeat option
        today = date.today().isoformat()
        last = db.query("""
            SELECT measure_date, period, measure_time
            FROM bp_records
            WHERE source IN ('manual','edit')
            ORDER BY id DESC LIMIT 1
        """)
        return render_template("add.html", today=today, last=last[0] if last else None)

    @app.route("/edit/<int:rid>", methods=["GET", "POST"])
    def edit_record(rid):
        if request.method == "POST":
            db.execute("""
                UPDATE bp_records
                SET systolic=?, diastolic=?, pulse=?, notes=?,
                    measure_time=?, source='edit', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                request.form.get("systolic") or None,
                request.form.get("diastolic") or None,
                request.form.get("pulse") or None,
                request.form.get("notes", ""),
                request.form.get("measure_time") or None,
                rid,
            ))
            return redirect(url_for("records_list"))

        rows = db.query("SELECT * FROM bp_records WHERE id=?", (rid,))
        if not rows:
            abort(404)
        return render_template("edit.html", row=rows[0])

    @app.route("/delete/<int:rid>", methods=["POST"])
    def delete_record(rid):
        db.execute("DELETE FROM bp_records WHERE id=?", (rid,))
        return redirect(url_for("records_list"))

    # ---- API endpoints (for chart data) ----

    @app.route("/api/daily")
    def api_daily():
        """Daily means for chart. Optional ?days=N (default 90)."""
        days = int(request.args.get("days", 90))
        rows = get_daily_means(days_back=days)
        return jsonify(rows)

    @app.route("/api/sessions")
    def api_sessions():
        """Per-session means (AM and PM as separate points)."""
        days = int(request.args.get("days", 30))
        rows = get_session_means(days_back=days)
        return jsonify(rows)

    @app.route("/api/raw")
    def api_raw():
        """Per-reading rows for client-side filtering.
        Either ?from=YYYY-MM-DD&to=YYYY-MM-DD, or ?days=N (default 30)."""
        from_d = request.args.get("from")
        to_d = request.args.get("to")
        if from_d and to_d:
            rows = db.query("""
                SELECT measure_date, period, sequence, arm,
                       systolic, diastolic, pulse
                FROM bp_records
                WHERE measure_date BETWEEN ? AND ?
                  AND systolic IS NOT NULL
                ORDER BY measure_date, period, sequence, arm
            """, (from_d, to_d))
        else:
            days = int(request.args.get("days", 30))
            rows = db.query("""
                SELECT measure_date, period, sequence, arm,
                       systolic, diastolic, pulse
                FROM bp_records
                WHERE measure_date >= date('now', ?)
                  AND systolic IS NOT NULL
                ORDER BY measure_date, period, sequence, arm
            """, (f"-{days} days",))
        return jsonify(rows)

    @app.route("/api/date_range")
    def api_date_range():
        """Return min/max dates in DB for date picker bounds."""
        r = db.query("SELECT MIN(measure_date) AS lo, MAX(measure_date) AS hi FROM bp_records")
        return jsonify(r[0] if r else {"lo": None, "hi": None})

    @app.route("/api/recent_table")
    def api_recent_table():
        """Recent N days, fully detailed."""
        days = int(request.args.get("days", 7))
        rows = db.query("""
            SELECT measure_date, period, measure_time, sequence, arm,
                   systolic, diastolic, pulse, notes, source
            FROM bp_records
            WHERE measure_date >= date('now', ?)
            ORDER BY measure_date DESC, period DESC, sequence ASC, arm ASC
        """, (f"-{days} days",))
        return jsonify(rows)

    # ---- Apple Health export ----

    @app.route("/export/health.xml")
    def export_health_xml():
        """匯出 Apple Health XML。

        可選參數:
          ?days=N           只匯出最近 N 天 (用於試水溫前先試小量)
          ?from=YYYY-MM-DD&to=YYYY-MM-DD  匯出自訂日期範圍
          (兩者都沒給 → 匯出全部)
        """
        days = request.args.get("days", type=int)
        from_d = request.args.get("from")
        to_d = request.args.get("to")
        limit = request.args.get("limit", type=int)

        params = []
        where = "WHERE (systolic IS NOT NULL OR pulse IS NOT NULL)"
        suffix = ""
        if from_d and to_d:
            where += " AND measure_date BETWEEN ? AND ?"
            params.extend([from_d, to_d])
            suffix = f"_{from_d}_to_{to_d}"
        elif days and days > 0:
            # 從「最新資料日期」倒推 N 天,而不是從今天 (避免資料未更新到今日時撈到空集合)
            latest = db.query(
                "SELECT MAX(measure_date) AS d FROM bp_records WHERE systolic IS NOT NULL OR pulse IS NOT NULL"
            )
            anchor = latest[0]["d"] if latest and latest[0]["d"] else None
            if anchor:
                from datetime import timedelta as _td
                cutoff = (date.fromisoformat(anchor) - _td(days=days - 1)).isoformat()
                where += " AND measure_date >= ?"
                params.append(cutoff)
                suffix = f"_last{days}d_{anchor}"

        limit_clause = ""
        if limit and limit > 0:
            limit_clause = f" LIMIT {int(limit)}"
            suffix = f"_min{int(limit)}" + suffix

        rows = db.query(f"""
            SELECT measure_date, period, measure_time, sequence, arm,
                   systolic, diastolic, pulse, source
            FROM bp_records
            {where}
            ORDER BY measure_date DESC, period DESC, sequence DESC, arm DESC
            {limit_clause}
        """, params)
        xml = health_export.build_xml(rows)
        return Response(
            xml,
            mimetype="application/xml",
            headers={
                "Content-Disposition":
                    f'attachment; filename="bp_export_{date.today().isoformat()}{suffix}.xml"'
            },
        )

    @app.route("/export")
    def export_page():
        return render_template("export.html")

    # ---- Re-import corrected Excel ----

    @app.route("/reimport", methods=["GET", "POST"])
    def reimport_page():
        result = None
        if request.method == "POST":
            uploaded = request.files.get("excel")
            mode = request.form.get("mode", "verified")
            if not uploaded or not uploaded.filename.endswith(".xlsx"):
                result = {"ok": False, "msg": "請選擇 .xlsx 檔案"}
            else:
                upload_dir = Path(db.get_db_path()).parent / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = upload_dir / f"bp_review_{ts}.xlsx"
                uploaded.save(save_path)

                # Mirror into expected location for the import script
                project_root = Path(__file__).resolve().parents[1]
                target_excel = project_root / "phase1_ocr" / "output" / "bp_ocr_review.xlsx"
                target_excel.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(save_path, target_excel)

                cmd = [
                    sys.executable,
                    str(project_root / "phase2_db" / "import_excel_to_db.py"),
                    "--db", str(db.get_db_path()),
                ]
                if mode == "unverified":
                    cmd.append("--unverified")

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                ok = proc.returncode == 0
                result = {
                    "ok": ok,
                    "msg": "匯入成功" if ok else "匯入失敗",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "saved_path": str(save_path),
                    "mode": mode,
                }

        # Current DB stats
        stats = {}
        rows = db.query("""
            SELECT source, COUNT(*) AS n FROM bp_records GROUP BY source
        """)
        stats["by_source"] = {r["source"]: r["n"] for r in rows}
        stats["total"] = sum(stats["by_source"].values())
        last = db.query("SELECT MAX(updated_at) AS t FROM bp_records")
        stats["last_update"] = last[0]["t"] if last else None

        return render_template("reimport.html", result=result, stats=stats)
