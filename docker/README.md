# NAS Deployment (Synology)

## Prerequisites
- Synology DSM 7+ with **Container Manager** (formerly Docker) installed
- SSH access to NAS
- Local development tested working

## One-time Setup on Mac

Build the image locally and save it as a tar:

```bash
cd ~/Git/bp-tracker
docker build -f docker/Dockerfile -t bp-tracker:latest .
docker save bp-tracker:latest -o /tmp/bp-tracker.tar
```

## Deploy to Synology

### Option A: Push image via SSH

1. Copy image and compose file to NAS:
   ```bash
   scp /tmp/bp-tracker.tar admin@<NAS_IP>:/volume1/docker/bp-tracker/
   scp docker/docker-compose.yml admin@<NAS_IP>:/volume1/docker/bp-tracker/
   ```

2. SSH into NAS and load:
   ```bash
   ssh admin@<NAS_IP>
   sudo docker load -i /volume1/docker/bp-tracker/bp-tracker.tar
   cd /volume1/docker/bp-tracker
   sudo docker compose up -d
   ```

3. (Optional) Seed initial DB from your local OCR data:
   ```bash
   scp ~/Git/bp-tracker/phase2_db/bp.db admin@<NAS_IP>:/volume1/docker/bp-tracker/data/bp.db
   ```

### Option B: Container Manager UI

1. In DSM: **Container Manager** → **Image** → **Add** → **Add From File** → upload `bp-tracker.tar`
2. **Project** → **Create** → upload `docker-compose.yml`

## Access

Open in browser: `http://<NAS_IP>:8080`

Add bookmark on iPhone Safari for quick access.

## Future Updates

When you change code:
```bash
cd ~/Git/bp-tracker
docker build -f docker/Dockerfile -t bp-tracker:latest .
docker save bp-tracker:latest -o /tmp/bp-tracker.tar
scp /tmp/bp-tracker.tar admin@<NAS_IP>:/volume1/docker/bp-tracker/
ssh admin@<NAS_IP>
sudo docker load -i /volume1/docker/bp-tracker/bp-tracker.tar
sudo docker compose up -d --force-recreate
```

## Backups

The container auto-backs-up the DB to `data/backups/bp_YYYYMMDD.db` daily at 03:00 (keeps 30 days).
Synology snapshots add another safety layer.

## Re-import Verified OCR Data Later

Once you've completed Excel review on your Mac:
```bash
~/.virtualenvs/bp-tracker/bin/python ~/Git/bp-tracker/phase2_db/import_excel_to_db.py \
    --db /tmp/bp.db
scp /tmp/bp.db admin@<NAS_IP>:/volume1/docker/bp-tracker/data/bp.db
ssh admin@<NAS_IP> "sudo docker restart bp-tracker"
```

This script preserves manually-entered records (source IN ('manual','edit')) and only replaces OCR rows.
