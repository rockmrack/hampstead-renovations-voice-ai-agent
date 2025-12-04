#!/bin/bash
# =============================================================================
# Hampstead Renovations Voice AI Agent - Health Check Script
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Voice AI Agent Health Check"
echo "=========================================="
echo ""

# Track overall status
HEALTHY=true

check_service() {
    local service=$1
    local check_cmd=$2
    
    if eval "$check_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $service is healthy"
    else
        echo -e "${RED}✗${NC} $service is unhealthy"
        HEALTHY=false
    fi
}

echo "Checking Docker containers..."
echo "-------------------------------------------"

# Check if containers are running
for container in api postgres redis traefik prometheus grafana; do
    if docker compose ps | grep -q "${container}.*running"; then
        echo -e "${GREEN}✓${NC} Container: $container is running"
    else
        echo -e "${RED}✗${NC} Container: $container is not running"
        HEALTHY=false
    fi
done

echo ""
echo "Checking service health..."
echo "-------------------------------------------"

# API Health
check_service "API Server" "curl -sf http://localhost:8000/health"

# PostgreSQL
check_service "PostgreSQL" "docker compose exec -T postgres pg_isready -U hampstead"

# Redis
check_service "Redis" "docker compose exec -T redis redis-cli ping | grep -q PONG"

# Prometheus
check_service "Prometheus" "curl -sf http://localhost:9090/-/healthy"

# Grafana
check_service "Grafana" "curl -sf http://localhost:3000/api/health"

echo ""
echo "Checking external services..."
echo "-------------------------------------------"

# Claude API (with API key from env)
if [ -n "$ANTHROPIC_API_KEY" ]; then
    check_service "Claude API" "curl -sf https://api.anthropic.com/v1/models -H 'x-api-key: $ANTHROPIC_API_KEY' -H 'anthropic-version: 2023-06-01'"
else
    echo -e "${YELLOW}?${NC} Claude API: ANTHROPIC_API_KEY not set"
fi

# Deepgram API
if [ -n "$DEEPGRAM_API_KEY" ]; then
    check_service "Deepgram API" "curl -sf https://api.deepgram.com/v1/projects -H 'Authorization: Token $DEEPGRAM_API_KEY'"
else
    echo -e "${YELLOW}?${NC} Deepgram API: DEEPGRAM_API_KEY not set"
fi

# ElevenLabs API
if [ -n "$ELEVENLABS_API_KEY" ]; then
    check_service "ElevenLabs API" "curl -sf https://api.elevenlabs.io/v1/user -H 'xi-api-key: $ELEVENLABS_API_KEY'"
else
    echo -e "${YELLOW}?${NC} ElevenLabs API: ELEVENLABS_API_KEY not set"
fi

echo ""
echo "Checking disk space..."
echo "-------------------------------------------"

DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓${NC} Disk usage: ${DISK_USAGE}%"
elif [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}!${NC} Disk usage: ${DISK_USAGE}% (warning)"
else
    echo -e "${RED}✗${NC} Disk usage: ${DISK_USAGE}% (critical)"
    HEALTHY=false
fi

echo ""
echo "Checking memory usage..."
echo "-------------------------------------------"

MEM_USAGE=$(free | awk '/Mem:/ {printf("%.0f"), $3/$2 * 100}')
if [ "$MEM_USAGE" -lt 80 ]; then
    echo -e "${GREEN}✓${NC} Memory usage: ${MEM_USAGE}%"
elif [ "$MEM_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}!${NC} Memory usage: ${MEM_USAGE}% (warning)"
else
    echo -e "${RED}✗${NC} Memory usage: ${MEM_USAGE}% (critical)"
    HEALTHY=false
fi

echo ""
echo "Checking container stats..."
echo "-------------------------------------------"

docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -10

echo ""
echo "=========================================="
if [ "$HEALTHY" = true ]; then
    echo -e "${GREEN}Overall Status: HEALTHY${NC}"
    exit 0
else
    echo -e "${RED}Overall Status: UNHEALTHY${NC}"
    exit 1
fi
