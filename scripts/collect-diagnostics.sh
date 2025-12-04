#!/bin/bash
# =============================================================================
# Hampstead Renovations Voice AI Agent - Diagnostics Collection Script
# =============================================================================

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/hampstead-diagnostics-$TIMESTAMP"
OUTPUT_FILE="hampstead-diagnostics-$TIMESTAMP.tar.gz"

echo "=========================================="
echo "Collecting Diagnostics"
echo "Output: $OUTPUT_FILE"
echo "=========================================="

mkdir -p "$OUTPUT_DIR"

# System info
echo "Collecting system info..."
{
    echo "=== SYSTEM INFO ==="
    uname -a
    echo ""
    echo "=== DISK USAGE ==="
    df -h
    echo ""
    echo "=== MEMORY ==="
    free -h
    echo ""
    echo "=== CPU ==="
    lscpu | head -20
} > "$OUTPUT_DIR/system-info.txt"

# Docker info
echo "Collecting Docker info..."
{
    echo "=== DOCKER VERSION ==="
    docker --version
    docker compose version
    echo ""
    echo "=== RUNNING CONTAINERS ==="
    docker compose ps
    echo ""
    echo "=== CONTAINER STATS ==="
    docker stats --no-stream
    echo ""
    echo "=== DOCKER DISK USAGE ==="
    docker system df
} > "$OUTPUT_DIR/docker-info.txt"

# Container logs
echo "Collecting container logs..."
for container in api postgres redis traefik prometheus grafana loki promtail; do
    echo "  - $container"
    docker compose logs --tail=500 "$container" > "$OUTPUT_DIR/logs-$container.txt" 2>&1 || true
done

# API health check
echo "Collecting API health..."
{
    echo "=== API HEALTH ==="
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "API not responding"
    echo ""
    echo "=== API METRICS ==="
    curl -s http://localhost:8000/metrics | head -100 || echo "Metrics not available"
} > "$OUTPUT_DIR/api-health.txt"

# Database info
echo "Collecting database info..."
{
    echo "=== DATABASE CONNECTIONS ==="
    docker compose exec -T postgres psql -U hampstead -c "SELECT * FROM pg_stat_activity;" 2>/dev/null || echo "DB not accessible"
    echo ""
    echo "=== TABLE SIZES ==="
    docker compose exec -T postgres psql -U hampstead -c "
        SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as size
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
        LIMIT 20;
    " 2>/dev/null || echo "Cannot query tables"
} > "$OUTPUT_DIR/database-info.txt"

# Redis info
echo "Collecting Redis info..."
{
    echo "=== REDIS INFO ==="
    docker compose exec -T redis redis-cli INFO 2>/dev/null || echo "Redis not accessible"
    echo ""
    echo "=== REDIS MEMORY ==="
    docker compose exec -T redis redis-cli MEMORY STATS 2>/dev/null || echo "Cannot get memory stats"
} > "$OUTPUT_DIR/redis-info.txt"

# Network info
echo "Collecting network info..."
{
    echo "=== DOCKER NETWORKS ==="
    docker network ls
    echo ""
    echo "=== NETWORK CONNECTIONS ==="
    ss -tuln | head -50
    echo ""
    echo "=== DNS RESOLUTION ==="
    nslookup api.hampsteadrenovations.com 2>/dev/null || echo "DNS lookup failed"
} > "$OUTPUT_DIR/network-info.txt"

# Environment (sanitized)
echo "Collecting environment (sanitized)..."
{
    echo "=== ENVIRONMENT VARIABLES (sanitized) ==="
    docker compose config | grep -E "^\s+[A-Z_]+:" | sed 's/\(API_KEY\|SECRET\|PASSWORD\|TOKEN\)=.*/\1=***REDACTED***/gi'
} > "$OUTPUT_DIR/environment.txt"

# Recent errors
echo "Extracting recent errors..."
{
    echo "=== ERRORS FROM LAST HOUR ==="
    docker compose logs --since 1h 2>&1 | grep -iE "(error|exception|failed|critical)" | tail -200
} > "$OUTPUT_DIR/recent-errors.txt"

# Create tarball
echo "Creating archive..."
cd /tmp
tar -czf "$OUTPUT_FILE" "hampstead-diagnostics-$TIMESTAMP"

# Cleanup
rm -rf "$OUTPUT_DIR"

echo ""
echo "=========================================="
echo "Diagnostics collected: /tmp/$OUTPUT_FILE"
echo "Size: $(du -h /tmp/$OUTPUT_FILE | cut -f1)"
echo "=========================================="
echo ""
echo "To share diagnostics, run:"
echo "  scp /tmp/$OUTPUT_FILE user@support-server:/path/"
echo ""
