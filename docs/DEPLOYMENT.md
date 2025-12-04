# Deployment Guide

This guide covers deploying the Hampstead Renovations Voice AI Agent to production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Environment Configuration](#environment-configuration)
4. [Docker Deployment](#docker-deployment)
5. [Database Setup](#database-setup)
6. [SSL/TLS Configuration](#ssltls-configuration)
7. [Monitoring Setup](#monitoring-setup)
8. [Post-Deployment Verification](#post-deployment-verification)
9. [Rollback Procedures](#rollback-procedures)

---

## Prerequisites

### Required Software
- Docker 24.0+
- Docker Compose 2.20+
- Git 2.40+
- OpenSSL 3.0+

### Cloud Accounts
- **AWS** (S3 for voice file storage)
- **Domain** (for SSL certificates)
- **360dialog** (WhatsApp Business API)
- **Anthropic** (Claude API)
- **Deepgram** (Speech-to-Text)
- **ElevenLabs** (Text-to-Speech)
- **VAPI** (Voice calls)
- **HubSpot** (CRM)
- **Microsoft Azure** (Graph API for calendar)

### Server Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 50 GB SSD | 100 GB SSD |
| Network | 100 Mbps | 1 Gbps |

---

## Infrastructure Setup

### 1. Server Provisioning

```bash
# Ubuntu 22.04 LTS recommended
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify installation
docker --version
docker compose version
```

### 2. Firewall Configuration

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Prometheus (internal only)
sudo ufw allow from 10.0.0.0/8 to any port 9090

# Enable firewall
sudo ufw enable
```

### 3. Clone Repository

```bash
# Create deployment directory
sudo mkdir -p /opt/hampstead-voice-agent
sudo chown $USER:$USER /opt/hampstead-voice-agent

# Clone repository
cd /opt/hampstead-voice-agent
git clone https://github.com/rockmrack/hampstead-renovations-voice-ai-agent.git .
```

---

## Environment Configuration

### 1. Create Environment File

```bash
cp .env.example .env
nano .env
```

### 2. Required Environment Variables

```bash
# =============================================================================
# CORE SETTINGS
# =============================================================================
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY=<generate-256-bit-key>

# =============================================================================
# API CONFIGURATION
# =============================================================================
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
API_TIMEOUT=60

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/hampstead
REDIS_URL=redis://redis:6379/0

# =============================================================================
# AI SERVICES
# =============================================================================
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=...

# =============================================================================
# VAPI CONFIGURATION
# =============================================================================
VAPI_API_KEY=...
VAPI_WEBHOOK_SECRET=...
VAPI_PHONE_NUMBER=+44...

# =============================================================================
# WHATSAPP (360dialog)
# =============================================================================
WHATSAPP_API_KEY=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_WEBHOOK_SECRET=...

# =============================================================================
# HUBSPOT CRM
# =============================================================================
HUBSPOT_API_KEY=...
HUBSPOT_PIPELINE_ID=...

# =============================================================================
# MICROSOFT GRAPH (Calendar)
# =============================================================================
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
MICROSOFT_TENANT_ID=...

# =============================================================================
# AWS (S3)
# =============================================================================
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-west-2
S3_BUCKET=hampstead-voice-agent

# =============================================================================
# DOMAIN CONFIGURATION
# =============================================================================
DOMAIN=api.hampsteadrenovations.com
ACME_EMAIL=admin@hampsteadrenovations.com
```

### 3. Generate Secure Keys

```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate webhook secrets
openssl rand -base64 32
```

---

## Docker Deployment

### 1. Build and Deploy

```bash
cd /opt/hampstead-voice-agent

# Pull latest changes
git pull origin main

# Build images
docker compose build --no-cache

# Start services
docker compose up -d

# Check status
docker compose ps
```

### 2. View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 api
```

### 3. Scale API Workers

```bash
# Scale to 4 API replicas
docker compose up -d --scale api=4
```

---

## Database Setup

### 1. Initialize Database

```bash
# Wait for PostgreSQL to be ready
docker compose exec postgres pg_isready -U hampstead

# Run initialization script
docker compose exec -T postgres psql -U hampstead -d hampstead < scripts/init-db.sql
```

### 2. Run Migrations

```bash
# Enter API container
docker compose exec api bash

# Run Alembic migrations
cd /app
alembic upgrade head

# Verify migration status
alembic current
```

### 3. Create Backup Schedule

```bash
# Create backup script
cat > /opt/hampstead-voice-agent/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/opt/backups/hampstead
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker compose exec -T postgres pg_dump -U hampstead hampstead | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Backup Redis
docker compose exec -T redis redis-cli SAVE
docker cp hampstead-redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# Upload to S3
aws s3 sync $BACKUP_DIR s3://hampstead-backups/

# Clean old backups (keep 30 days)
find $BACKUP_DIR -mtime +30 -delete
EOF

chmod +x /opt/hampstead-voice-agent/scripts/backup.sh

# Add to crontab (daily at 3am)
echo "0 3 * * * /opt/hampstead-voice-agent/scripts/backup.sh" | crontab -
```

---

## SSL/TLS Configuration

### Automatic (Traefik + Let's Encrypt)

SSL is automatically configured via Traefik. Ensure:

1. Domain DNS points to server IP
2. Ports 80 and 443 are open
3. `ACME_EMAIL` is set in `.env`

### Manual Verification

```bash
# Check certificate
curl -vI https://api.hampsteadrenovations.com/health

# View certificate details
echo | openssl s_client -servername api.hampsteadrenovations.com \
  -connect api.hampsteadrenovations.com:443 2>/dev/null | \
  openssl x509 -noout -dates
```

---

## Monitoring Setup

### 1. Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | https://grafana.hampsteadrenovations.com | admin / (from .env) |
| Prometheus | https://prometheus.hampsteadrenovations.com | N/A (internal) |

### 2. Configure Alerting

```bash
# Edit Prometheus alerting rules
nano monitoring/prometheus/alerts.yml

# Reload Prometheus config
curl -X POST http://localhost:9090/-/reload
```

### 3. Set Up Slack Notifications

1. Create Slack Webhook URL
2. Configure in Grafana:
   - Alerting → Notification channels → Add channel
   - Type: Slack
   - Webhook URL: your-webhook-url

---

## Post-Deployment Verification

### 1. Health Checks

```bash
# API health
curl -s https://api.hampsteadrenovations.com/health | jq

# Expected response:
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "database": "connected",
    "redis": "connected",
    "claude": "available",
    "deepgram": "available",
    "elevenlabs": "available"
  }
}
```

### 2. Integration Tests

```bash
# Test WhatsApp webhook (simulation)
curl -X POST https://api.hampsteadrenovations.com/whatsapp/webhook \
  -H "Content-Type: application/json" \
  -d '{"entry": [{"changes": [{"value": {"messages": []}}]}]}'

# Test voice endpoint
curl -X POST https://api.hampsteadrenovations.com/voice/synthesize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"text": "Hello, this is a test"}'
```

### 3. Monitoring Verification

```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check Grafana datasources
curl -s http://localhost:3000/api/datasources | jq '.[].name'
```

---

## Rollback Procedures

### 1. Quick Rollback

```bash
# Stop current deployment
docker compose down

# Checkout previous version
git checkout <previous-commit-sha>

# Rebuild and deploy
docker compose build
docker compose up -d
```

### 2. Database Rollback

```bash
# Downgrade migration
docker compose exec api alembic downgrade -1

# Or restore from backup
gunzip -c /opt/backups/hampstead/db_20240115_030000.sql.gz | \
  docker compose exec -T postgres psql -U hampstead -d hampstead
```

### 3. Emergency Stop

```bash
# Stop all services immediately
docker compose kill

# View what happened
docker compose logs --tail=500 > emergency_logs.txt
```

---

## Maintenance Tasks

### Regular Maintenance Checklist

- [ ] Weekly: Review Grafana dashboards for anomalies
- [ ] Weekly: Check disk space usage
- [ ] Monthly: Update Docker images
- [ ] Monthly: Review and rotate API keys
- [ ] Quarterly: Security audit with Snyk
- [ ] Quarterly: Load testing

### Update Procedure

```bash
# 1. Pull latest code
cd /opt/hampstead-voice-agent
git pull origin main

# 2. Review changes
git log --oneline -10

# 3. Backup current state
./scripts/backup.sh

# 4. Deploy update (zero-downtime)
docker compose pull
docker compose up -d --force-recreate

# 5. Run migrations if needed
docker compose exec api alembic upgrade head

# 6. Verify deployment
curl -s https://api.hampsteadrenovations.com/health | jq
```

---

## Support

For deployment issues:
1. Check logs: `docker compose logs -f`
2. Review documentation
3. Contact: devops@hampsteadrenovations.com
