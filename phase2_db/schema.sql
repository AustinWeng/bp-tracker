-- Blood Pressure Tracker DB Schema
-- SQLite 3

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    birth_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO users (id, name) VALUES (1, '本人');

-- Each row is ONE measurement (one arm, one sequence, at one session time)
-- A complete day has 8 rows (AM/PM × seq1/seq2 × L/R)
CREATE TABLE IF NOT EXISTS bp_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    measure_date DATE NOT NULL,
    period TEXT NOT NULL CHECK(period IN ('AM','PM')),
    measure_time TIME,                              -- session start time, shared by 4 readings
    sequence INTEGER NOT NULL CHECK(sequence IN (1,2)),
    arm TEXT NOT NULL CHECK(arm IN ('L','R')),
    systolic INTEGER,
    diastolic INTEGER,
    pulse INTEGER,
    notes TEXT,                                     -- session-level notes (shared by 4 readings of same session)
    source TEXT NOT NULL DEFAULT 'manual',          -- 'ocr' | 'manual' | 'edit'
    source_ref TEXT,                                -- e.g. 'p12' for OCR origin
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, measure_date, period, sequence, arm)
);

-- Per-day context (temperature etc.)
CREATE TABLE IF NOT EXISTS daily_context (
    user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
    measure_date DATE NOT NULL,
    temperature_c REAL,
    weather_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_id, measure_date)
);

CREATE INDEX IF NOT EXISTS idx_bp_date ON bp_records(user_id, measure_date DESC);
CREATE INDEX IF NOT EXISTS idx_bp_session ON bp_records(user_id, measure_date, period);

-- Convenience views
CREATE VIEW IF NOT EXISTS v_session_means AS
SELECT
    user_id,
    measure_date,
    period,
    measure_time,
    AVG(systolic) AS mean_systolic,
    AVG(diastolic) AS mean_diastolic,
    AVG(pulse) AS mean_pulse,
    COUNT(*) AS n_readings,
    MAX(notes) AS notes
FROM bp_records
WHERE systolic IS NOT NULL
GROUP BY user_id, measure_date, period, measure_time;

CREATE VIEW IF NOT EXISTS v_daily_means AS
SELECT
    user_id,
    measure_date,
    AVG(systolic) AS mean_systolic,
    AVG(diastolic) AS mean_diastolic,
    AVG(pulse) AS mean_pulse,
    MIN(systolic) AS min_systolic,
    MAX(systolic) AS max_systolic,
    COUNT(*) AS n_readings
FROM bp_records
WHERE systolic IS NOT NULL
GROUP BY user_id, measure_date;

-- Trigger to update updated_at on bp_records edits
CREATE TRIGGER IF NOT EXISTS trg_bp_updated
AFTER UPDATE ON bp_records
BEGIN
    UPDATE bp_records SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_daily_updated
AFTER UPDATE ON daily_context
BEGIN
    UPDATE daily_context SET updated_at = CURRENT_TIMESTAMP
    WHERE user_id = NEW.user_id AND measure_date = NEW.measure_date;
END;
