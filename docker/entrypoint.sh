#!/bin/sh
set -e

# Initialize DB if it doesn't exist
if [ ! -f "$BP_DB_PATH" ]; then
    echo "Initializing new DB at $BP_DB_PATH"
    mkdir -p "$(dirname "$BP_DB_PATH")"
    python -c "
import sqlite3
from pathlib import Path
schema = Path('schema.sql').read_text()
conn = sqlite3.connect('$BP_DB_PATH')
conn.executescript(schema)
conn.close()
print('DB initialized')
"
fi

# Daily backup at 03:00 (background)
(
    while true; do
        # sleep until next 03:00
        now=$(date +%s)
        target=$(date -d "tomorrow 03:00" +%s 2>/dev/null || date -v+1d -v3H -v0M -v0S +%s)
        sleep_s=$((target - now))
        sleep "$sleep_s"
        backup_dir="$(dirname "$BP_DB_PATH")/backups"
        mkdir -p "$backup_dir"
        backup_file="$backup_dir/bp_$(date +%Y%m%d).db"
        cp "$BP_DB_PATH" "$backup_file"
        # Keep last 30
        ls -t "$backup_dir"/bp_*.db 2>/dev/null | tail -n +31 | xargs -r rm -f
        echo "Backup: $backup_file"
    done
) &

# Run gunicorn
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --access-logfile - --error-logfile - "app:create_app()"
