#!/bin/bash
# MySQL backup script for FSourceInsight
# Usage: ./scripts/backup_mysql.sh
# Recommended: Run via cron daily at 2:00 AM
#   0 2 * * * /path/to/FSourceInsight/scripts/backup_mysql.sh >> /var/log/fsourceinsight-backup.log 2>&1

set -euo pipefail

# Config (override via environment)
BACKUP_DIR="${BACKUP_DIR:-/var/backups/fsourceinsight}"
MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-fsourceinsight}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:?MYSQL_PASSWORD must be set}"
MYSQL_DATABASE="${MYSQL_DATABASE:-fsourceinsight}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Derived
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${MYSQL_DATABASE}_${TIMESTAMP}.sql.gz"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

echo "[$(date)] Starting backup of ${MYSQL_DATABASE}..."

# Dump and compress
mysqldump \
    -h "${MYSQL_HOST}" \
    -P "${MYSQL_PORT}" \
    -u "${MYSQL_USER}" \
    -p"${MYSQL_PASSWORD}" \
    --single-transaction \
    --routines \
    --triggers \
    --quick \
    "${MYSQL_DATABASE}" | gzip > "${BACKUP_FILE}"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Clean up old backups
DELETED=$(find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date)] Cleaned up ${DELETED} backup(s) older than ${RETENTION_DAYS} days"
fi

echo "[$(date)] Done."
