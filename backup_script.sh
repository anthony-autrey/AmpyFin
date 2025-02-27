# To set this script up to run hourly, do the following:
# "crontab -e"
# in nano, add this line at the bottom: "0 13-21/2 * * 1-5 /root/AmpyFin/backup_script.sh >> /backups/backup.log 2>&1"
#   (this cron expression will backup every two hours from 9-5 (UTC), mon-fri )
#   ctrl+O, enter to save
#   ctrl+X to exit
# ..this backs up every 4 hours

# To restore from a backup, issue the following command:
#   mongorestore --drop /path/to/backup


#!/bin/bash

# Configuration (customize these or pass via environment variables)
BACKUP_ROOT="/backups"
MAX_BACKUPS=5  # Keep the last 5 backups
CONTAINER_NAME="ampyfin-mongo"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Run mongodump inside the running container
docker exec "$CONTAINER_NAME" mongodump \
  --out="/backup_temp"  # Use a temporary path inside the container

# Copy backups from the container to the host
docker cp "$CONTAINER_NAME:/backup_temp" "$BACKUP_DIR"

# Cleanup the temporary directory inside the container
docker exec "$CONTAINER_NAME" rm -rf "/backup_temp"

# Delete backups older than $MAX_BACKUPS days
find "$BACKUP_ROOT" -type d -mtime +$((MAX_BACKUPS - 1)) -exec rm -rf {} \;

echo "Backup saved to: $BACKUP_DIR"