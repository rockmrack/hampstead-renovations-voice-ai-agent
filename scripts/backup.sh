#!/bin/bash
# =============================================================================
# Hampstead Renovations Voice AI Agent - Backup Script
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/hampstead}"
S3_BUCKET="${S3_BUCKET:-hampstead-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "Starting Backup - $TIMESTAMP"
echo "=========================================="

# Create backup directory
mkdir -p "$BACKUP_DIR"

# PostgreSQL Backup
echo "Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U hampstead hampstead | gzip > "$BACKUP_DIR/db_$TIMESTAMP.sql.gz"
echo "  → Created: db_$TIMESTAMP.sql.gz ($(du -h "$BACKUP_DIR/db_$TIMESTAMP.sql.gz" | cut -f1))"

# Redis Backup
echo "Backing up Redis..."
docker compose exec -T redis redis-cli SAVE
docker cp "$(docker compose ps -q redis)":/data/dump.rdb "$BACKUP_DIR/redis_$TIMESTAMP.rdb"
echo "  → Created: redis_$TIMESTAMP.rdb ($(du -h "$BACKUP_DIR/redis_$TIMESTAMP.rdb" | cut -f1))"

# Configuration Backup
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$TIMESTAMP.tar.gz" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    docker-compose.yml \
    .env \
    monitoring/ \
    scripts/ 2>/dev/null || true
echo "  → Created: config_$TIMESTAMP.tar.gz"

# Upload to S3 (if AWS CLI configured)
if command -v aws &> /dev/null && [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo "Uploading to S3..."
    aws s3 sync "$BACKUP_DIR" "s3://$S3_BUCKET/backups/" --exclude "*" \
        --include "db_$TIMESTAMP.sql.gz" \
        --include "redis_$TIMESTAMP.rdb" \
        --include "config_$TIMESTAMP.tar.gz"
    echo "  → Uploaded to s3://$S3_BUCKET/backups/"
else
    echo "  ⚠ AWS CLI not configured, skipping S3 upload"
fi

# Cleanup old backups
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -name "db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "redis_*.rdb" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +$RETENTION_DAYS -delete
echo "  → Removed backups older than $RETENTION_DAYS days"

# Summary
echo ""
echo "=========================================="
echo "Backup Complete"
echo "=========================================="
echo "Location: $BACKUP_DIR"
echo "Files:"
ls -lh "$BACKUP_DIR" | grep "$TIMESTAMP" | awk '{print "  - " $9 " (" $5 ")"}'
echo ""
