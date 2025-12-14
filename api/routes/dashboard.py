"""
Real-time dashboard WebSocket routes.
Provides live updates for admin dashboard.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel

from services.websocket_service import connection_manager, dashboard_emitter

logger = structlog.get_logger(__name__)

router = APIRouter()


class DashboardStats(BaseModel):
    """Current dashboard statistics."""
    active_conversations: int = 0
    total_messages_today: int = 0
    leads_qualified_today: int = 0
    bookings_today: int = 0
    avg_response_time_ms: float = 0.0
    sentiment_score: float = 0.0


# In-memory stats (in production, use Redis)
_dashboard_stats = DashboardStats()
_conversation_cache: dict[str, dict] = {}


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    """
    Main WebSocket endpoint for real-time dashboard updates.
    
    Query params:
        client_id: Optional client identifier
        token: Authentication token (required in production)
    
    Message protocol:
        Send: {"action": "subscribe", "channel": "conversations"}
        Receive: {"event": "...", "timestamp": "...", "data": {...}}
    """
    # TODO: Validate token in production
    # if not token or not validate_dashboard_token(token):
    #     await websocket.close(code=4001, reason="Unauthorized")
    #     return

    await connection_manager.connect(websocket, client_id)
    
    try:
        # Send initial state
        await connection_manager.send_personal(websocket, {
            "event": "connected",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "client_id": client_id,
                "stats": _dashboard_stats.model_dump(),
                "active_conversations": list(_conversation_cache.values())[-10:],  # Last 10
            },
        })
        
        # Handle incoming messages
        while True:
            data = await websocket.receive_json()
            await handle_websocket_message(websocket, data)
            
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e))
        await connection_manager.disconnect(websocket)


async def handle_websocket_message(websocket: WebSocket, data: dict) -> None:
    """Handle incoming WebSocket messages."""
    action = data.get("action")
    
    if action == "subscribe":
        channel = data.get("channel", "*")
        await connection_manager.subscribe(websocket, channel)
        await connection_manager.send_personal(websocket, {
            "event": "subscribed",
            "channel": channel,
        })
        
    elif action == "unsubscribe":
        channel = data.get("channel")
        if channel:
            await connection_manager.unsubscribe(websocket, channel)
            await connection_manager.send_personal(websocket, {
                "event": "unsubscribed",
                "channel": channel,
            })
            
    elif action == "ping":
        await connection_manager.send_personal(websocket, {
            "event": "pong",
            "timestamp": datetime.utcnow().isoformat(),
        })
        
    elif action == "get_stats":
        await connection_manager.send_personal(websocket, {
            "event": "stats",
            "data": _dashboard_stats.model_dump(),
        })
        
    elif action == "get_conversations":
        limit = data.get("limit", 20)
        conversations = list(_conversation_cache.values())[-limit:]
        await connection_manager.send_personal(websocket, {
            "event": "conversations",
            "data": conversations,
        })


@router.get("/stats")
async def get_dashboard_stats() -> DashboardStats:
    """Get current dashboard statistics."""
    return _dashboard_stats


@router.get("/conversations/active")
async def get_active_conversations(limit: int = 20) -> list[dict]:
    """Get list of active conversations."""
    return list(_conversation_cache.values())[-limit:]


@router.post("/conversations/{conversation_id}/watch")
async def watch_conversation(conversation_id: str) -> dict:
    """Mark a conversation for detailed watching."""
    if conversation_id in _conversation_cache:
        _conversation_cache[conversation_id]["watched"] = True
        return {"status": "watching", "conversation_id": conversation_id}
    raise HTTPException(status_code=404, detail="Conversation not found")


# Helper functions for updating dashboard state
async def update_conversation_cache(
    conversation_id: str,
    channel: str,
    customer_phone: str,
    customer_name: Optional[str] = None,
    status: str = "active",
) -> None:
    """Update conversation in cache and emit event."""
    _conversation_cache[conversation_id] = {
        "id": conversation_id,
        "channel": channel,
        "customer_phone": customer_phone[-4:],
        "customer_name": customer_name,
        "status": status,
        "started_at": datetime.utcnow().isoformat(),
        "messages": [],
        "lead_score": None,
        "watched": False,
    }
    
    await dashboard_emitter.emit_conversation_started(
        conversation_id=conversation_id,
        channel=channel,
        customer_phone=customer_phone,
        customer_name=customer_name,
    )
    
    _dashboard_stats.active_conversations = len(
        [c for c in _conversation_cache.values() if c["status"] == "active"]
    )


async def add_message_to_conversation(
    conversation_id: str,
    content: str,
    direction: str,
    message_type: str = "text",
) -> None:
    """Add message to conversation and emit event."""
    if conversation_id in _conversation_cache:
        _conversation_cache[conversation_id]["messages"].append({
            "content": content[:500],
            "direction": direction,
            "type": message_type,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Keep only last 50 messages per conversation
        _conversation_cache[conversation_id]["messages"] = \
            _conversation_cache[conversation_id]["messages"][-50:]
    
    await dashboard_emitter.emit_message_received(
        conversation_id=conversation_id,
        message_type=message_type,
        content=content,
        direction=direction,
    )
    
    _dashboard_stats.total_messages_today += 1


async def update_lead_score(
    conversation_id: str,
    phone: str,
    score: int,
    qualification_data: dict,
) -> None:
    """Update lead score and emit event."""
    old_score = 0
    if conversation_id in _conversation_cache:
        old_score = _conversation_cache[conversation_id].get("lead_score", 0) or 0
        _conversation_cache[conversation_id]["lead_score"] = score
    
    await dashboard_emitter.emit_lead_score_update(
        conversation_id=conversation_id,
        phone=phone,
        old_score=old_score,
        new_score=score,
        qualification_data=qualification_data,
    )
    
    if score >= 70 and old_score < 70:
        _dashboard_stats.leads_qualified_today += 1


async def close_conversation(conversation_id: str) -> None:
    """Mark conversation as closed."""
    if conversation_id in _conversation_cache:
        _conversation_cache[conversation_id]["status"] = "closed"
        _conversation_cache[conversation_id]["closed_at"] = datetime.utcnow().isoformat()
        
        _dashboard_stats.active_conversations = len(
            [c for c in _conversation_cache.values() if c["status"] == "active"]
        )


# Background task to emit periodic metrics
async def metrics_emitter_task():
    """Periodically emit metrics updates."""
    while True:
        try:
            await asyncio.sleep(5)  # Every 5 seconds
            await dashboard_emitter.emit_metrics_update(_dashboard_stats.model_dump())
        except Exception as e:
            logger.error("metrics_emitter_error", error=str(e))


# Cleanup old conversations periodically
async def cleanup_old_conversations():
    """Remove conversations older than 24 hours."""
    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            cutoff = datetime.utcnow() - timedelta(hours=24)
            
            to_remove = []
            for conv_id, conv in _conversation_cache.items():
                started_at = datetime.fromisoformat(conv["started_at"])
                if started_at < cutoff:
                    to_remove.append(conv_id)
            
            for conv_id in to_remove:
                del _conversation_cache[conv_id]
                
            logger.info("cleaned_old_conversations", count=len(to_remove))
        except Exception as e:
            logger.error("cleanup_error", error=str(e))
