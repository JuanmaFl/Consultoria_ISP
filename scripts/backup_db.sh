#!/bin/bash
BACKUP_DIR="/opt/cobertura_isp/backups"
LOG_FILE="/opt/cobertura_isp/logs/backup.log"
FECHA=$(date +%Y%m%d_%H%M%S)
ARCHIVO="$BACKUP_DIR/cobertura_isp_$FECHA.sql.gz"
DIAS_RETENER=7
mkdir -p "$BACKUP_DIR"
echo "$(date) - Iniciando backup..." >> "$LOG_FILE"
export $(grep -v "^#" /opt/cobertura_isp/.env | xargs)
PGPASSWORD="$DATABASE_PASSWORD" pg_dump -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER" -d "$DATABASE_NAME" --no-password | gzip > "$ARCHIVO"
if [ $? -eq 0 ]; then
    SIZE=$(du -sh "$ARCHIVO" | cut -f1)
    echo "$(date) - OK: $ARCHIVO ($SIZE)" >> "$LOG_FILE"
else
    echo "$(date) - ERROR: Fallo el backup" >> "$LOG_FILE"
    exit 1
fi
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$DIAS_RETENER -delete
echo "$(date) - Backups actuales: $(ls $BACKUP_DIR | wc -l)" >> "$LOG_FILE"
