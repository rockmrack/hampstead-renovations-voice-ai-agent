# API Documentation

## Overview

The Hampstead Renovations Voice AI Agent API provides endpoints for managing voice conversations, WhatsApp messaging, calendar bookings, and CRM integration.

**Base URL:** `https://api.hampsteadrenovations.com`

**API Version:** `1.0.0`

---

## Authentication

All API endpoints require authentication using Bearer tokens or webhook signatures.

### Bearer Token Authentication

```http
Authorization: Bearer your-api-key
```

### Webhook Signature Verification

For incoming webhooks, verify the signature:

```python
import hmac
import hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## Endpoints

### Health Check

#### `GET /health`

Check API health and service connectivity.

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "services": {
    "database": "connected",
    "redis": "connected",
    "claude": "available",
    "deepgram": "available",
    "elevenlabs": "available"
  }
}
```

**Status Codes:**
- `200 OK` - All services healthy
- `503 Service Unavailable` - One or more services unhealthy

---

### WhatsApp Webhooks

#### `POST /whatsapp/webhook`

Receive incoming WhatsApp messages.

**Headers:**

| Header | Description |
|--------|-------------|
| `X-Hub-Signature-256` | HMAC-SHA256 signature |
| `Content-Type` | `application/json` |

**Request Body:**

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "447900000000",
              "phone_number_id": "PHONE_NUMBER_ID"
            },
            "contacts": [
              {
                "profile": {
                  "name": "John Smith"
                },
                "wa_id": "447777777777"
              }
            ],
            "messages": [
              {
                "from": "447777777777",
                "id": "wamid.xxx",
                "timestamp": "1704067200",
                "text": {
                  "body": "Hello, I'd like a quote for a kitchen renovation"
                },
                "type": "text"
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
```

**Response:**

```json
{
  "status": "received",
  "message_id": "wamid.xxx"
}
```

#### `GET /whatsapp/webhook`

Webhook verification for Meta.

**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `hub.mode` | Always "subscribe" |
| `hub.verify_token` | Your verification token |
| `hub.challenge` | Challenge to return |

**Response:** Returns `hub.challenge` value

---

### Voice Processing

#### `POST /voice/synthesize`

Convert text to speech.

**Request:**

```json
{
  "text": "Hello! Thank you for contacting Hampstead Renovations.",
  "voice_id": "sarah",
  "output_format": "mp3_44100_128"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Text to synthesize (max 5000 chars) |
| `voice_id` | string | No | Voice to use (default: "sarah") |
| `output_format` | string | No | Audio format (default: "mp3_44100_128") |

**Response:**

```json
{
  "audio_url": "https://s3.amazonaws.com/hampstead-voice/tts/abc123.mp3",
  "duration_seconds": 3.5,
  "characters_used": 52
}
```

#### `POST /voice/transcribe`

Convert speech to text.

**Request:**

Content-Type: `multipart/form-data`

| Field | Type | Description |
|-------|------|-------------|
| `audio` | file | Audio file (mp3, wav, ogg, m4a) |
| `language` | string | Language code (default: "en-GB") |

**Response:**

```json
{
  "transcript": "I'd like to get a quote for renovating my bathroom",
  "confidence": 0.96,
  "words": [
    {"word": "I'd", "start": 0.0, "end": 0.2, "confidence": 0.98},
    {"word": "like", "start": 0.22, "end": 0.4, "confidence": 0.97}
  ],
  "duration_seconds": 4.2
}
```

---

### Calendar & Booking

#### `GET /calendar/availability`

Get available appointment slots.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | Yes | Start date (YYYY-MM-DD) |
| `end_date` | string | No | End date (default: start + 7 days) |
| `service_type` | string | No | Filter by service type |
| `duration_minutes` | integer | No | Required slot duration (default: 60) |

**Response:**

```json
{
  "available_slots": [
    {
      "date": "2024-01-16",
      "day_name": "Tuesday",
      "slots": [
        {
          "start_time": "09:00",
          "end_time": "10:00",
          "surveyor": "James Wilson"
        },
        {
          "start_time": "14:00",
          "end_time": "15:00",
          "surveyor": "Sarah Thompson"
        }
      ]
    },
    {
      "date": "2024-01-17",
      "day_name": "Wednesday",
      "slots": [
        {
          "start_time": "10:00",
          "end_time": "11:00",
          "surveyor": "James Wilson"
        }
      ]
    }
  ],
  "timezone": "Europe/London"
}
```

#### `POST /calendar/book`

Book an appointment.

**Request:**

```json
{
  "date": "2024-01-16",
  "start_time": "09:00",
  "customer": {
    "name": "John Smith",
    "email": "john.smith@email.com",
    "phone": "+447777777777"
  },
  "property": {
    "address": "123 High Street, London NW3 1AB",
    "postcode": "NW3 1AB",
    "property_type": "terraced_house"
  },
  "service_type": "kitchen_renovation",
  "notes": "Looking for full kitchen refit with new appliances"
}
```

**Response:**

```json
{
  "booking_id": "BK-2024-0001",
  "status": "confirmed",
  "appointment": {
    "date": "2024-01-16",
    "start_time": "09:00",
    "end_time": "10:00",
    "surveyor": {
      "name": "James Wilson",
      "phone": "+447900000001"
    }
  },
  "confirmation_sent": {
    "email": true,
    "whatsapp": true
  },
  "calendar_event_id": "AAMkAGE1M..."
}
```

#### `DELETE /calendar/book/{booking_id}`

Cancel a booking.

**Response:**

```json
{
  "booking_id": "BK-2024-0001",
  "status": "cancelled",
  "cancellation_time": "2024-01-15T11:30:00Z"
}
```

---

### VAPI Webhooks

#### `POST /vapi/webhooks`

Handle VAPI call events.

**Headers:**

| Header | Description |
|--------|-------------|
| `X-VAPI-Signature` | Request signature |
| `X-VAPI-Timestamp` | Request timestamp |

**Event Types:**

##### Call Started

```json
{
  "type": "call.started",
  "call": {
    "id": "call_abc123",
    "phone_number": "+447777777777",
    "direction": "inbound",
    "started_at": "2024-01-15T10:30:00Z"
  }
}
```

##### Transcript Update

```json
{
  "type": "transcript.update",
  "call_id": "call_abc123",
  "transcript": {
    "role": "user",
    "content": "I'd like to book a survey please",
    "timestamp": "2024-01-15T10:30:15Z"
  }
}
```

##### Function Call

```json
{
  "type": "function.call",
  "call_id": "call_abc123",
  "function": {
    "name": "check_availability",
    "arguments": {
      "date": "2024-01-16",
      "service_type": "kitchen"
    }
  }
}
```

**Function Call Response:**

```json
{
  "result": {
    "available": true,
    "slots": ["09:00", "14:00", "16:00"]
  }
}
```

##### Call Ended

```json
{
  "type": "call.ended",
  "call": {
    "id": "call_abc123",
    "duration_seconds": 245,
    "ended_at": "2024-01-15T10:34:05Z",
    "end_reason": "customer_hangup"
  }
}
```

---

### Conversations

#### `GET /conversations/{conversation_id}`

Get conversation history.

**Response:**

```json
{
  "conversation_id": "conv_abc123",
  "channel": "whatsapp",
  "customer": {
    "phone": "+447777777777",
    "name": "John Smith"
  },
  "messages": [
    {
      "id": "msg_001",
      "role": "user",
      "content": "Hello, I need a kitchen renovation quote",
      "timestamp": "2024-01-15T10:00:00Z"
    },
    {
      "id": "msg_002",
      "role": "assistant",
      "content": "Hello John! I'd be happy to help...",
      "timestamp": "2024-01-15T10:00:05Z"
    }
  ],
  "metadata": {
    "lead_score": 85,
    "service_interest": ["kitchen", "bathroom"],
    "budget_range": "£20,000-£30,000",
    "timeline": "3-6 months"
  },
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid phone number format",
    "details": {
      "field": "phone",
      "expected": "E.164 format",
      "received": "07777777777"
    }
  },
  "request_id": "req_abc123"
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `AUTHENTICATION_ERROR` | 401 | Invalid or missing API key |
| `AUTHORIZATION_ERROR` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |
| `SERVICE_UNAVAILABLE` | 503 | External service unavailable |

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| All endpoints | 100 requests | 1 minute |
| `/voice/synthesize` | 30 requests | 1 minute |
| `/voice/transcribe` | 30 requests | 1 minute |
| `/calendar/book` | 10 requests | 1 minute |

Rate limit headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067260
```

---

## Webhooks

### Configuring Webhooks

Register your webhook endpoint:

```json
POST /webhooks/register

{
  "url": "https://your-domain.com/webhooks",
  "events": ["booking.created", "booking.cancelled", "lead.qualified"],
  "secret": "your-webhook-secret"
}
```

### Webhook Events

| Event | Description |
|-------|-------------|
| `booking.created` | New appointment booked |
| `booking.cancelled` | Appointment cancelled |
| `booking.reminder` | Reminder sent (24h/1h before) |
| `lead.qualified` | Lead score exceeds threshold |
| `conversation.completed` | Conversation ended |

### Webhook Payload Example

```json
{
  "event": "booking.created",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": {
    "booking_id": "BK-2024-0001",
    "customer_phone": "+447777777777",
    "appointment_date": "2024-01-16",
    "service_type": "kitchen"
  },
  "signature": "sha256=abc123..."
}
```

---

## SDKs

### Python SDK

```python
from hampstead_voice import HampsteadClient

client = HampsteadClient(api_key="your-api-key")

# Check availability
slots = client.calendar.get_availability(
    start_date="2024-01-16",
    service_type="kitchen"
)

# Book appointment
booking = client.calendar.book(
    date="2024-01-16",
    start_time="09:00",
    customer_name="John Smith",
    customer_phone="+447777777777",
    service_type="kitchen"
)
```

### JavaScript SDK

```javascript
import { HampsteadClient } from 'hampstead-voice-sdk';

const client = new HampsteadClient({ apiKey: 'your-api-key' });

// Check availability
const slots = await client.calendar.getAvailability({
  startDate: '2024-01-16',
  serviceType: 'kitchen'
});

// Book appointment
const booking = await client.calendar.book({
  date: '2024-01-16',
  startTime: '09:00',
  customer: {
    name: 'John Smith',
    phone: '+447777777777'
  },
  serviceType: 'kitchen'
});
```

---

## Changelog

### v1.0.0 (2024-01-15)

- Initial release
- WhatsApp messaging integration
- Voice call support via VAPI
- Calendar booking system
- Claude AI conversation engine
- HubSpot CRM integration

---

## Support

- **Email:** api-support@hampsteadrenovations.com
- **Documentation:** https://docs.hampsteadrenovations.com
- **Status Page:** https://status.hampsteadrenovations.com
