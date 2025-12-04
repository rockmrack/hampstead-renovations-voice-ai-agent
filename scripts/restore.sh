#!/bin/bash
# =============================================================================
# Hampstead Renovations Voice AI Agent - Restore Script
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/hampstead}"

usage() {
    echo "Usage: $0 [--db <backup_file>] [--redis <backup_file>] [--config <backup_file>]"
    echo ""
    echo "Options:"
    echo "  --db      Restore PostgreSQL from backup file"
    echo "  --redis   Restore Redis from backup file"
    echo "  --config  Restore configuration from backup file"
    echo "  --list    List available backups"
    echo ""
    echo "Examples:"
    echo "  $0 --list"
    echo "  $0 --db /opt/backups/hampstead/db_20240115_030000.sql.gz"
    echo "  $0 --db latest"
    exit 1
}

list_backups() {
    echo "Available backups in $BACKUP_DIR:"
    echo ""
    echo "PostgreSQL backups:"
    ls -lht "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -10 || echo "  None found"
    echo ""
    echo "Redis backups:"
    ls -lht "$BACKUP_DIR"/redis_*.rdb 2>/dev/null | head -10 || echo "  None found"
    echo ""
    echo "Config backups:"
    ls -lht "$BACKUP_DIR"/config_*.tar.gz 2>/dev/null | head -10 || echo "  None found"
}

restore_db() {
    local BACKUP_FILE=$1
    
    if [ "$BACKUP_FILE" = "latest" ]; then
        BACKUP_FILE=$(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)
        if [ -z "$BACKUP_FILE" ]; then
            echo "Error: No database backups found"
            exit 1
        fi
    fi
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    echo "Restoring PostgreSQL from: $BACKUP_FILE"
    echo "WARNING: This will overwrite the current database!"
    read -p "Continue? (yes/no): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
    
    # Stop API to prevent writes
    echo "Stopping API..."
    docker compose stop api
    
    # Drop and recreate database
    echo "Recreating database..."
    docker compose exec -T postgres psql -U hampstead -d postgres -c "DROP DATABASE IF EXISTS hampstead;"
    docker compose exec -T postgres psql -U hampstead -d postgres -c "CREATE DATABASE hampstead;"
    
    # Restore
    echo "Restoring data..."
    gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U hampstead -d hampstead
    
    # Restart API
    echo "Restarting API..."
    docker compose start api
    
    echo "Database restore complete!"
}

restore_redis() {
    local BACKUP_FILE=$1
    
    if [ "$BACKUP_FILE" = "latest" ]; then
        BACKUP_FILE=$(ls -t "$BACKUP_DIR"/redis_*.rdb 2>/dev/null | head -1)
        if [ -z "$BACKUP_FILE" ]; then
            echo "Error: No Redis backups found"
            exit 1
        fi
    fi
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    echo "Restoring Redis from: $BACKUP_FILE"
    echo "WARNING: This will overwrite the current Redis data!"
    read -p "Continue? (yes/no): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
    
    # Stop Redis
    echo "Stopping Redis..."
    docker compose stop redis
    
    # Copy backup file
    echo "Copying backup..."
    docker cp "$BACKUP_FILE" "$(docker compose ps -q redis)":/data/dump.rdb
    
    # Restart Redis
    echo "Restarting Redis..."
    docker compose start redis
    
    echo "Redis restore complete!"
}

restore_config() {
    local BACKUP_FILE=$1
    
    if [ "$BACKUP_FILE" = "latest" ]; then
        BACKUP_FILE=$(ls -t "$BACKUP_DIR"/config_*.tar.gz 2>/dev/null | head -1)
        if [ -z "$BACKUP_FILE" ]; then
            echo "Error: No config backups found"
            exit 1
        fi
    fi
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    
    echo "Restoring config from: $BACKUP_FILE"
    echo "WARNING: This will overwrite configuration files!"
    read -p "Continue? (yes/no): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
    
    # Extract to current directory
    echo "Extracting configuration..."
    tar -xzf "$BACKUP_FILE" -C .
    
    echo "Config restore complete!"
    echo "You may need to restart services: docker compose restart"
}

# Parse arguments
if [ $# -eq 0 ]; then
    usage
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --list)
            list_backups
            exit 0
            ;;
        --db)
            restore_db "$2"
            shift 2
            ;;
        --redis)
            restore_redis "$2"
            shift 2
            ;;
        --config)
            restore_config "$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done
