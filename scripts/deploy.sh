#!/bin/bash
# =============================================================================
# HAMPSTEAD RENOVATIONS VOICE AI AGENT - DEPLOYMENT SCRIPT
# =============================================================================
# Production deployment script for Docker Compose stack
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"
BACKUP_DIR="$PROJECT_ROOT/backups"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# PRE-DEPLOYMENT CHECKS
# =============================================================================
pre_deploy_checks() {
    log_info "Running pre-deployment checks..."
    
    # Check if .env file exists
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found at $ENV_FILE"
        log_info "Copy .env.example to .env and fill in your values"
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Check if Docker Compose is available
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed."
        exit 1
    fi
    
    # Check required environment variables
    source "$ENV_FILE"
    required_vars=(
        "ANTHROPIC_API_KEY"
        "DEEPGRAM_API_KEY"
        "ELEVENLABS_API_KEY"
        "VAPI_API_KEY"
        "WHATSAPP_API_KEY"
        "POSTGRES_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            log_error "Required environment variable $var is not set"
            exit 1
        fi
    done
    
    log_success "Pre-deployment checks passed"
}

# =============================================================================
# BACKUP FUNCTION
# =============================================================================
backup_data() {
    log_info "Creating backup..."
    
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    
    # Backup PostgreSQL if running
    if docker ps --format '{{.Names}}' | grep -q "hampstead-postgres"; then
        log_info "Backing up PostgreSQL database..."
        docker exec hampstead-postgres pg_dumpall -U "${POSTGRES_USER:-hampstead}" > "$BACKUP_DIR/postgres_backup_$TIMESTAMP.sql"
        log_success "PostgreSQL backup created"
    fi
    
    # Backup n8n data
    if docker ps --format '{{.Names}}' | grep -q "hampstead-n8n"; then
        log_info "Backing up n8n data..."
        docker run --rm -v hampstead-renovations-voice-ai-agent_n8n-data:/data -v "$BACKUP_DIR":/backup alpine tar czf "/backup/n8n_backup_$TIMESTAMP.tar.gz" -C /data .
        log_success "n8n backup created"
    fi
    
    # Cleanup old backups (keep last 7 days)
    find "$BACKUP_DIR" -type f -mtime +7 -delete
    
    log_success "Backup completed: $BACKUP_DIR"
}

# =============================================================================
# BUILD FUNCTION
# =============================================================================
build_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_ROOT"
    
    # Build with no cache if --fresh flag is passed
    if [ "${1:-}" = "--fresh" ]; then
        docker-compose build --no-cache
    else
        docker-compose build
    fi
    
    log_success "Docker images built successfully"
}

# =============================================================================
# DEPLOY FUNCTION
# =============================================================================
deploy() {
    log_info "Deploying Hampstead Renovations Voice AI Agent..."
    
    cd "$PROJECT_ROOT"
    
    # Pull latest images for external services
    log_info "Pulling external images..."
    docker-compose pull redis postgres traefik prometheus grafana loki promtail n8n
    
    # Start services
    log_info "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check service health
    services=("hampstead-redis" "hampstead-postgres" "hampstead-voice-api")
    for service in "${services[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "$service"; then
            log_success "$service is running"
        else
            log_warning "$service may not be running properly"
        fi
    done
    
    log_success "Deployment completed!"
}

# =============================================================================
# ROLLBACK FUNCTION
# =============================================================================
rollback() {
    log_info "Rolling back to previous version..."
    
    cd "$PROJECT_ROOT"
    
    # Stop current containers
    docker-compose down
    
    # Find latest backup
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/postgres_backup_*.sql 2>/dev/null | head -1)
    
    if [ -n "$LATEST_BACKUP" ]; then
        log_info "Restoring from backup: $LATEST_BACKUP"
        
        # Start only postgres
        docker-compose up -d postgres
        sleep 10
        
        # Restore database
        docker exec -i hampstead-postgres psql -U "${POSTGRES_USER:-hampstead}" < "$LATEST_BACKUP"
        
        # Start remaining services
        docker-compose up -d
        
        log_success "Rollback completed"
    else
        log_warning "No backup found. Starting fresh deployment..."
        docker-compose up -d
    fi
}

# =============================================================================
# STATUS FUNCTION
# =============================================================================
status() {
    log_info "Checking service status..."
    
    echo ""
    echo "=== Container Status ==="
    docker-compose ps
    
    echo ""
    echo "=== Health Checks ==="
    
    # Check API health
    if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        API_STATUS=$(curl -s http://localhost:8000/api/v1/health | jq -r '.status' 2>/dev/null || echo "unknown")
        log_success "API: $API_STATUS"
    else
        log_warning "API: Not responding"
    fi
    
    # Check Redis
    if docker exec hampstead-redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis: Connected"
    else
        log_warning "Redis: Not responding"
    fi
    
    # Check PostgreSQL
    if docker exec hampstead-postgres pg_isready -U "${POSTGRES_USER:-hampstead}" > /dev/null 2>&1; then
        log_success "PostgreSQL: Ready"
    else
        log_warning "PostgreSQL: Not ready"
    fi
    
    echo ""
    echo "=== Resource Usage ==="
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | head -10
}

# =============================================================================
# LOGS FUNCTION
# =============================================================================
logs() {
    SERVICE="${1:-api}"
    LINES="${2:-100}"
    
    log_info "Showing logs for $SERVICE (last $LINES lines)..."
    
    case "$SERVICE" in
        "api")
            docker logs hampstead-voice-api --tail "$LINES" -f
            ;;
        "n8n")
            docker logs hampstead-n8n --tail "$LINES" -f
            ;;
        "postgres")
            docker logs hampstead-postgres --tail "$LINES" -f
            ;;
        "all")
            docker-compose logs --tail "$LINES" -f
            ;;
        *)
            docker-compose logs "$SERVICE" --tail "$LINES" -f
            ;;
    esac
}

# =============================================================================
# STOP FUNCTION
# =============================================================================
stop() {
    log_info "Stopping all services..."
    cd "$PROJECT_ROOT"
    docker-compose down
    log_success "All services stopped"
}

# =============================================================================
# CLEANUP FUNCTION
# =============================================================================
cleanup() {
    log_info "Cleaning up Docker resources..."
    
    # Remove stopped containers
    docker container prune -f
    
    # Remove unused images
    docker image prune -f
    
    # Remove unused volumes (be careful!)
    if [ "${1:-}" = "--volumes" ]; then
        log_warning "Removing unused volumes..."
        docker volume prune -f
    fi
    
    # Remove unused networks
    docker network prune -f
    
    log_success "Cleanup completed"
}

# =============================================================================
# MAIN
# =============================================================================
main() {
    case "${1:-help}" in
        "deploy")
            pre_deploy_checks
            backup_data
            build_images "${2:-}"
            deploy
            ;;
        "build")
            build_images "${2:-}"
            ;;
        "start")
            deploy
            ;;
        "stop")
            stop
            ;;
        "restart")
            stop
            deploy
            ;;
        "status")
            status
            ;;
        "logs")
            logs "${2:-api}" "${3:-100}"
            ;;
        "backup")
            backup_data
            ;;
        "rollback")
            rollback
            ;;
        "cleanup")
            cleanup "${2:-}"
            ;;
        "help"|*)
            echo ""
            echo "Hampstead Renovations Voice AI Agent - Deployment Script"
            echo ""
            echo "Usage: $0 <command> [options]"
            echo ""
            echo "Commands:"
            echo "  deploy [--fresh]  Full deployment (backup, build, start)"
            echo "  build [--fresh]   Build Docker images"
            echo "  start             Start all services"
            echo "  stop              Stop all services"
            echo "  restart           Restart all services"
            echo "  status            Show service status and health"
            echo "  logs [service]    View logs (api|n8n|postgres|all)"
            echo "  backup            Create database backup"
            echo "  rollback          Rollback to previous backup"
            echo "  cleanup [--volumes]  Clean up Docker resources"
            echo "  help              Show this help message"
            echo ""
            ;;
    esac
}

main "$@"
