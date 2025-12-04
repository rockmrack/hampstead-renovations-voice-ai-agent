# System Architecture

## Overview

The Hampstead Renovations Voice AI Agent is a comprehensive voice-enabled customer service solution built on a modern microservices architecture. This document provides a detailed overview of the system components and their interactions.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL CHANNELS                                  │
├─────────────────┬───────────────────┬───────────────────┬──────────────────┤
│     WhatsApp    │    Phone/VAPI     │   Website Widget  │   Survey/Forms   │
│   (360dialog)   │   (Voice Calls)   │    (Future)       │   (HubSpot)      │
└────────┬────────┴─────────┬─────────┴─────────┬─────────┴────────┬─────────┘
         │                  │                   │                   │
         ▼                  ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TRAEFIK                                         │
│                    (Reverse Proxy + SSL Termination)                        │
│                     *.hampsteadrenovations.com                              │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI APPLICATION                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         MIDDLEWARE STACK                             │   │
│  ├──────────────┬──────────────────┬──────────────────┬────────────────┤   │
│  │ ErrorHandler │  RequestLogger   │   RateLimiter    │ CORS/Security  │   │
│  └──────────────┴──────────────────┴──────────────────┴────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          API ROUTES                                  │   │
│  ├────────────┬────────────┬────────────┬────────────┬────────────────┤   │
│  │  /health   │  /whatsapp │   /voice   │  /calendar │ /vapi/webhooks │   │
│  └────────────┴────────────┴────────────┴────────────┴────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          SERVICES                                    │   │
│  ├─────────────────┬─────────────────┬─────────────────┬───────────────┤   │
│  │ ConversationSvc │    ClaudeSvc    │   DeepgramSvc   │ ElevenLabsSvc │   │
│  ├─────────────────┼─────────────────┼─────────────────┼───────────────┤   │
│  │  WhatsAppSvc    │   HubSpotSvc    │   CalendarSvc   │    VAPISvc    │   │
│  ├─────────────────┼─────────────────┼─────────────────┼───────────────┤   │
│  │  StorageSvc     │ NotificationSvc │                 │               │   │
│  └─────────────────┴─────────────────┴─────────────────┴───────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       UTILS & HELPERS                                │   │
│  ├───────────────┬───────────────┬───────────────┬─────────────────────┤   │
│  │    Metrics    │    Helpers    │   Validators  │    Transformers     │   │
│  └───────────────┴───────────────┴───────────────┴─────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
┌────────────────┐        ┌────────────────────┐       ┌────────────────────┐
│     Redis      │        │     PostgreSQL     │       │     AWS S3         │
│   (Cache +     │        │    (Persistence)   │       │   (Voice Files)    │
│  Rate Limit)   │        │                    │       │                    │
└────────────────┘        └────────────────────┘       └────────────────────┘
```

## Component Details

### 1. External Channels

#### WhatsApp (360dialog)
- **Purpose**: Primary customer communication channel
- **Features**: Text messages, voice notes, images, location
- **Integration**: Webhook-based message handling
- **Rate Limits**: 1000 messages/day (Business tier)

#### Phone/VAPI
- **Purpose**: Real-time voice conversations
- **Features**: Inbound/outbound calls, IVR, call transfer
- **Integration**: WebSocket for real-time audio
- **Voice Models**: Deepgram (STT) + ElevenLabs (TTS)

### 2. API Gateway (Traefik)

```yaml
Features:
  - Automatic SSL via Let's Encrypt
  - Load balancing across API replicas
  - Request routing based on path/host
  - Health check monitoring
  - Rate limiting at edge
```

### 3. FastAPI Application

#### Middleware Stack (Processing Order)
1. **CORS Middleware**: Handle cross-origin requests
2. **GZip Middleware**: Compress responses > 500 bytes
3. **Error Handler**: Catch exceptions, format error responses
4. **Request Logger**: Log all requests with timing
5. **Rate Limiter**: Enforce per-client request limits

#### API Routes
| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | Liveness/readiness probes |
| `/whatsapp/webhook` | POST | Incoming WhatsApp messages |
| `/voice/synthesize` | POST | Text-to-speech generation |
| `/voice/transcribe` | POST | Speech-to-text conversion |
| `/calendar/availability` | GET | Check available slots |
| `/calendar/book` | POST | Book appointments |
| `/vapi/webhooks` | POST | VAPI call events |

### 4. Services Layer

#### Claude Service
```python
Purpose: AI conversation engine
Model: claude-sonnet-4-5-20250514
Features:
  - Multi-turn conversation
  - Function calling
  - Context management
  - Lead qualification
Resilience:
  - Circuit breaker (5 failures)
  - Retry with exponential backoff
  - Timeout: 30 seconds
```

#### Deepgram Service
```python
Purpose: Speech-to-text
Model: Nova-2
Features:
  - Real-time transcription
  - UK English optimized
  - Punctuation + diarization
  - Smart formatting
Accuracy: 95%+ for UK accents
```

#### ElevenLabs Service
```python
Purpose: Text-to-speech
Voice: Sarah (British Female)
Features:
  - Natural prosody
  - Emotion control
  - S3 upload integration
  - Caching for common phrases
Latency: <1.5s for 100 words
```

### 5. Data Stores

#### Redis
```
Purpose: Caching + Session Management
Data Types:
  - Conversation history (24h TTL)
  - Rate limit counters (1min window)
  - Lead scores (1h TTL)
  - Service area cache (1d TTL)
```

#### PostgreSQL
```
Purpose: Persistent Storage
Tables:
  - conversations
  - messages
  - leads
  - bookings
  - surveys
  - call_logs
Migrations: Alembic
```

#### AWS S3
```
Purpose: Media Storage
Buckets:
  - voice-recordings/
  - tts-cache/
  - transcriptions/
Lifecycle: 90 days retention
```

## Data Flow Examples

### WhatsApp Text Message Flow
```
1. Customer sends WhatsApp message
2. 360dialog webhook → /whatsapp/webhook
3. WhatsAppService validates signature
4. ConversationService retrieves context from Redis
5. ClaudeService generates response
6. WhatsAppService sends reply
7. ConversationService stores in PostgreSQL
8. HubSpotService updates CRM contact
```

### Voice Call Flow (VAPI)
```
1. Customer calls phone number
2. VAPI initiates WebSocket connection
3. /vapi/webhooks receives call.started event
4. DeepgramService transcribes audio stream
5. ClaudeService processes transcription
6. ElevenLabsService generates voice response
7. Audio streamed back through VAPI
8. Call ends → /vapi/webhooks receives call.ended
9. ConversationService stores full transcript
```

### Appointment Booking Flow
```
1. Customer requests appointment
2. ClaudeService extracts intent + preferences
3. CalendarService checks Microsoft Graph availability
4. Options presented to customer
5. Customer confirms slot
6. CalendarService creates booking
7. HubSpotService creates/updates deal
8. NotificationService sends confirmation
```

## Security Architecture

### Authentication & Authorization
```
┌─────────────────────────────────────────────────────────┐
│                   SECURITY LAYERS                        │
├─────────────────────────────────────────────────────────┤
│ 1. Traefik TLS (HTTPS Only)                             │
│ 2. Webhook Signature Verification (HMAC-SHA256)         │
│ 3. API Key Authentication (Bearer Token)                │
│ 4. Rate Limiting (100 req/min per IP)                   │
│ 5. Input Validation (Pydantic Models)                   │
│ 6. SQL Injection Prevention (SQLAlchemy ORM)            │
│ 7. XSS Protection (Sanitized outputs)                   │
│ 8. Secrets Management (Environment Variables)           │
└─────────────────────────────────────────────────────────┘
```

### Webhook Security
- **WhatsApp**: X-Hub-Signature-256 header validation
- **VAPI**: X-VAPI-Signature header with timestamp
- **HubSpot**: X-HubSpot-Signature with client secret

## Monitoring & Observability

### Metrics (Prometheus)
```
hampstead_requests_total{method, endpoint, status}
hampstead_request_duration_seconds{endpoint}
hampstead_ai_response_time_seconds{service}
hampstead_active_conversations
hampstead_leads_qualified_total{source}
hampstead_bookings_total{type}
```

### Logging (Loki)
```
Format: JSON structured logs
Fields:
  - timestamp
  - level
  - message
  - request_id
  - user_id
  - conversation_id
  - latency_ms
```

### Dashboards (Grafana)
1. **Operations**: Request rates, error rates, latency
2. **AI Performance**: Response times, token usage, quality
3. **Business Metrics**: Leads, bookings, conversions

## Scaling Strategy

### Horizontal Scaling
```yaml
API Replicas: 2-10 (auto-scaled)
Redis: Cluster mode (3 nodes)
PostgreSQL: Read replicas (2)
Triggers:
  - CPU > 70%
  - Memory > 80%
  - Request queue > 100
```

### Performance Optimizations
- Connection pooling (asyncpg)
- Response caching (Redis)
- Async I/O throughout
- Lazy loading of resources
- Batched database operations

## Disaster Recovery

### Backup Strategy
| Data | Frequency | Retention | Location |
|------|-----------|-----------|----------|
| PostgreSQL | Daily | 30 days | AWS S3 |
| Redis | Hourly | 7 days | AWS S3 |
| Configs | On change | Forever | Git |
| Secrets | On change | Versioned | AWS Secrets Manager |

### Recovery Time Objectives
- **RTO**: 4 hours
- **RPO**: 1 hour
- **MTTR**: 30 minutes

## Future Enhancements

1. **Multi-tenancy**: Support multiple brands
2. **A/B Testing**: Prompt experimentation
3. **Analytics Pipeline**: BigQuery integration
4. **Mobile App**: React Native companion
5. **Video Calls**: WebRTC integration
