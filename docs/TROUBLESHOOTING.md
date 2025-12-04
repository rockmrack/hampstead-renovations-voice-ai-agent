# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Hampstead Renovations Voice AI Agent.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Service-Specific Issues](#service-specific-issues)
3. [Integration Issues](#integration-issues)
4. [Performance Issues](#performance-issues)
5. [Error Code Reference](#error-code-reference)
6. [Log Analysis](#log-analysis)
7. [Recovery Procedures](#recovery-procedures)

---

## Quick Diagnostics

### System Health Check

```bash
# Run full diagnostics
./scripts/health-check.sh

# Or manually:
# 1. Check all containers
docker compose ps

# 2. Check API health
curl -s http://localhost:8000/health | jq

# 3. Check database connection
docker compose exec postgres pg_isready -U hampstead

# 4. Check Redis connection
docker compose exec redis redis-cli ping

# 5. Check logs for errors
docker compose logs --tail=100 | grep -i error
```

### Common Quick Fixes

| Symptom | Quick Fix |
|---------|-----------|
| API not responding | `docker compose restart api` |
| High memory usage | `docker compose restart` |
| Redis connection errors | `docker compose restart redis` |
| Database connection errors | `docker compose restart postgres` |
| SSL certificate expired | `docker compose restart traefik` |

---

## Service-Specific Issues

### 1. FastAPI Application

#### Issue: API returns 500 errors

**Symptoms:**
- HTTP 500 Internal Server Error
- "Internal server error" in response

**Diagnosis:**
```bash
# Check API logs
docker compose logs api --tail=200 | grep -E "(ERROR|Exception|Traceback)"

# Check if dependencies are available
docker compose exec api python -c "import anthropic; print('OK')"
```

**Solutions:**
1. **Missing environment variable:**
   ```bash
   # Check all required vars are set
   docker compose config | grep -E "^\s+[A-Z_]+:"
   ```

2. **Module import error:**
   ```bash
   # Rebuild container
   docker compose build api --no-cache
   docker compose up -d api
   ```

3. **Resource exhaustion:**
   ```bash
   # Check container resources
   docker stats api
   
   # Increase limits in docker-compose.yml
   ```

#### Issue: Slow response times

**Symptoms:**
- API responses > 5 seconds
- Timeout errors

**Diagnosis:**
```bash
# Check API metrics
curl -s http://localhost:8000/metrics | grep request_duration

# Check database query times
docker compose exec postgres psql -U hampstead -c "
  SELECT query, calls, mean_time 
  FROM pg_stat_statements 
  ORDER BY mean_time DESC 
  LIMIT 10;"
```

**Solutions:**
1. Add database indexes
2. Enable Redis caching
3. Scale API replicas: `docker compose up -d --scale api=4`

---

### 2. Claude AI Service

#### Issue: AI responses are empty or generic

**Symptoms:**
- Claude returns empty responses
- Responses don't match context

**Diagnosis:**
```bash
# Check Claude API connectivity
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model": "claude-sonnet-4-5-20250514", "max_tokens": 100, "messages": [{"role": "user", "content": "Hello"}]}'
```

**Solutions:**
1. **API key invalid:**
   ```bash
   # Verify API key
   echo $ANTHROPIC_API_KEY | head -c 20
   # Should start with "sk-ant-"
   ```

2. **Rate limited:**
   - Check Anthropic dashboard for usage
   - Implement request queuing

3. **Context too long:**
   - Trim conversation history
   - Implement summarization

#### Issue: Circuit breaker open

**Symptoms:**
- Log: "Circuit breaker is open"
- AI requests failing fast

**Diagnosis:**
```bash
# Check error rate
docker compose logs api | grep -c "Claude API error"
```

**Solutions:**
```bash
# Wait for circuit to half-open (60 seconds)
# Or restart service to reset circuit
docker compose restart api
```

---

### 3. Deepgram (Speech-to-Text)

#### Issue: Transcription accuracy is low

**Symptoms:**
- Wrong words in transcript
- Missing words or sentences

**Diagnosis:**
```bash
# Check audio quality
# Look for: sample rate, bitrate, noise levels
```

**Solutions:**
1. **Wrong language model:**
   ```python
   # Use UK English model
   options = PrerecordedOptions(
       model="nova-2",
       language="en-GB",  # Not en-US
       smart_format=True
   )
   ```

2. **Poor audio quality:**
   - Require minimum bitrate (16kbps)
   - Add noise reduction preprocessing

3. **Accent issues:**
   - Enable `diarize=True` for multiple speakers
   - Use domain-specific keywords

---

### 4. ElevenLabs (Text-to-Speech)

#### Issue: Voice synthesis fails

**Symptoms:**
- No audio returned
- Error: "quota exceeded"

**Diagnosis:**
```bash
# Check API status
curl -s https://api.elevenlabs.io/v1/user \
  -H "xi-api-key: $ELEVENLABS_API_KEY" | jq '.subscription'
```

**Solutions:**
1. **Quota exceeded:**
   - Check usage in ElevenLabs dashboard
   - Implement caching for common phrases
   
2. **Voice not found:**
   ```bash
   # List available voices
   curl -s https://api.elevenlabs.io/v1/voices \
     -H "xi-api-key: $ELEVENLABS_API_KEY" | jq '.voices[].name'
   ```

3. **Text too long:**
   - Split text into chunks < 5000 characters
   - Implement streaming for long responses

---

### 5. WhatsApp (360dialog)

#### Issue: Messages not being received

**Symptoms:**
- Webhook not triggered
- No incoming messages

**Diagnosis:**
```bash
# Check webhook configuration
curl -s "https://waba.360dialog.io/v1/configs/webhook" \
  -H "D360-API-KEY: $WHATSAPP_API_KEY"

# Verify webhook is accessible
curl -I https://api.hampsteadrenovations.com/whatsapp/webhook
```

**Solutions:**
1. **Webhook URL incorrect:**
   ```bash
   # Update webhook URL
   curl -X POST "https://waba.360dialog.io/v1/configs/webhook" \
     -H "D360-API-KEY: $WHATSAPP_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://api.hampsteadrenovations.com/whatsapp/webhook"}'
   ```

2. **Signature verification failing:**
   - Verify `WHATSAPP_WEBHOOK_SECRET` matches 360dialog config
   - Check signature algorithm (HMAC-SHA256)

#### Issue: Messages not being sent

**Symptoms:**
- Send returns error
- Messages stuck in queue

**Diagnosis:**
```bash
# Test sending message
curl -X POST "https://waba.360dialog.io/v1/messages" \
  -H "D360-API-KEY: $WHATSAPP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "447777777777",
    "type": "text",
    "text": {"body": "Test message"}
  }'
```

**Solutions:**
1. **Phone number format:**
   - Use international format without +
   - Example: "447777777777" not "+447777777777"

2. **24-hour window expired:**
   - Use template message instead
   - Customer must message first

---

### 6. VAPI (Voice Calls)

#### Issue: Calls dropping unexpectedly

**Symptoms:**
- Calls disconnect mid-conversation
- "call.ended" with error reason

**Diagnosis:**
```bash
# Check VAPI logs
docker compose logs api | grep "vapi" | grep -i error

# Check WebSocket connections
ss -tn | grep ESTABLISHED | wc -l
```

**Solutions:**
1. **Network timeout:**
   - Increase keep-alive interval
   - Check for NAT/firewall issues

2. **Audio processing timeout:**
   - Reduce Deepgram latency setting
   - Pre-warm TTS connections

#### Issue: Function calling not working

**Symptoms:**
- VAPI doesn't call functions
- Wrong function called

**Solutions:**
1. **Function schema mismatch:**
   - Verify function definitions in VAPI dashboard
   - Check parameter types match expectations

2. **Webhook not responding:**
   - Ensure webhook returns within 10 seconds
   - Use async processing with immediate acknowledgment

---

## Integration Issues

### HubSpot CRM

#### Issue: Contacts not syncing

**Diagnosis:**
```bash
# Test HubSpot API
curl -s "https://api.hubapi.com/crm/v3/objects/contacts?limit=1" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY"
```

**Solutions:**
1. **API key permissions:**
   - Verify scopes: contacts, deals, timeline
   
2. **Rate limiting:**
   - HubSpot: 100 requests/10 seconds
   - Implement request queuing

### Microsoft Calendar

#### Issue: Can't read availability

**Diagnosis:**
```bash
# Get OAuth token
curl -X POST "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials"
```

**Solutions:**
1. **Token expired:**
   - Refresh token automatically
   - Check token expiry handling

2. **Calendar permissions:**
   - Grant `Calendars.ReadWrite` in Azure AD
   - Ensure admin consent given

---

## Performance Issues

### High CPU Usage

```bash
# Identify high-CPU container
docker stats --no-stream

# Profile Python code
docker compose exec api python -m cProfile -o profile.out /app/main.py

# Analyze profile
docker compose exec api python -c "
import pstats
p = pstats.Stats('profile.out')
p.sort_stats('cumulative').print_stats(20)
"
```

### Memory Leaks

```bash
# Check memory growth
watch -n 5 'docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}"'

# Profile memory
docker compose exec api python -c "
import tracemalloc
tracemalloc.start()
# ... run code ...
snapshot = tracemalloc.take_snapshot()
for stat in snapshot.statistics('lineno')[:10]:
    print(stat)
"
```

### Database Slow Queries

```bash
# Enable slow query log
docker compose exec postgres psql -U hampstead -c "
  ALTER SYSTEM SET log_min_duration_statement = 1000;
  SELECT pg_reload_conf();
"

# View slow queries
docker compose logs postgres | grep "duration:"
```

---

## Error Code Reference

| Code | Meaning | Resolution |
|------|---------|------------|
| `E001` | Database connection failed | Check PostgreSQL is running |
| `E002` | Redis connection failed | Check Redis is running |
| `E003` | Claude API error | Verify API key, check rate limits |
| `E004` | Deepgram API error | Verify API key, check audio format |
| `E005` | ElevenLabs API error | Verify API key, check quota |
| `E006` | WhatsApp API error | Verify API key, check webhook |
| `E007` | VAPI API error | Verify API key, check webhook secret |
| `E008` | HubSpot API error | Verify API key, check permissions |
| `E009` | Calendar API error | Refresh OAuth token |
| `E010` | S3 upload failed | Check AWS credentials |
| `E011` | Rate limit exceeded | Implement backoff, queue requests |
| `E012` | Circuit breaker open | Wait 60s or restart service |
| `E013` | Webhook signature invalid | Verify webhook secret |
| `E014` | Conversation not found | Check Redis TTL settings |
| `E015` | Lead qualification failed | Check qualification rules |

---

## Log Analysis

### Finding Errors

```bash
# All errors in last hour
docker compose logs --since 1h 2>&1 | grep -E "(ERROR|Exception|Failed)"

# Specific request tracking
docker compose logs api | grep "request_id=abc123"

# Error frequency
docker compose logs api | grep ERROR | cut -d' ' -f4 | sort | uniq -c | sort -rn
```

### Log Locations

| Service | Log Location |
|---------|-------------|
| API | stdout → Docker logs |
| PostgreSQL | `/var/log/postgresql/` |
| Redis | stdout → Docker logs |
| Traefik | `/var/log/traefik/` |
| Prometheus | stdout → Docker logs |
| Grafana | `/var/log/grafana/` |

### Setting Up Log Alerts

```yaml
# In Grafana, create alert rule:
# Query: count_over_time({job="api"} |= "ERROR" [5m])
# Condition: > 10
# Notification: Slack channel
```

---

## Recovery Procedures

### 1. Full System Recovery

```bash
# 1. Stop all services
docker compose down

# 2. Restore database from backup
gunzip -c /backup/db_latest.sql.gz | \
  docker compose exec -T postgres psql -U hampstead

# 3. Restore Redis data
docker cp /backup/redis_latest.rdb redis:/data/dump.rdb

# 4. Restart services
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
```

### 2. Corrupted Database Recovery

```bash
# 1. Stop API to prevent writes
docker compose stop api

# 2. Create point-in-time backup
docker compose exec postgres pg_dump -U hampstead > emergency_backup.sql

# 3. Repair (if possible)
docker compose exec postgres vacuumdb -U hampstead --full hampstead

# 4. Or restore from backup
# (see above)

# 5. Restart API
docker compose start api
```

### 3. Memory Emergency

```bash
# 1. Immediate relief
docker compose restart api

# 2. Clear Redis cache
docker compose exec redis redis-cli FLUSHDB

# 3. Check for memory leaks in logs
docker compose logs api | grep -i memory

# 4. Increase memory limits
# Edit docker-compose.yml: mem_limit: 2g
```

---

## Getting Help

If you can't resolve an issue:

1. **Collect diagnostics:**
   ```bash
   ./scripts/collect-diagnostics.sh > diagnostics.tar.gz
   ```

2. **Check documentation:**
   - [Architecture](ARCHITECTURE.md)
   - [Deployment](DEPLOYMENT.md)
   - [API Documentation](API.md)

3. **Contact support:**
   - Email: support@hampsteadrenovations.com
   - Slack: #voice-agent-support
