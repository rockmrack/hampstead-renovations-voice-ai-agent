"""
WebSocket service for real-time dashboard communication.
Handles live updates for conversations, metrics, and agent activities.
"""

import asyncio
import json
from datetime import datetime
from weakref import WeakSet

import structlog
from fastapi import WebSocket

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: WeakSet[WebSocket] = WeakSet()
        self.connection_metadata: dict[int, dict] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str | None = None) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            self.connection_metadata[id(websocket)] = {
                "client_id": client_id,
                "connected_at": datetime.utcnow().isoformat(),
                "subscriptions": set(),
            }
        logger.info(
            "websocket_connected",
            client_id=client_id,
            total_connections=len(self.active_connections),
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
            self.connection_metadata.pop(id(websocket), None)
        logger.info(
            "websocket_disconnected",
            total_connections=len(self.active_connections),
        )

    async def subscribe(self, websocket: WebSocket, channel: str) -> None:
        """Subscribe a connection to a specific channel."""
        ws_id = id(websocket)
        if ws_id in self.connection_metadata:
            self.connection_metadata[ws_id]["subscriptions"].add(channel)
            logger.debug("websocket_subscribed", channel=channel)

    async def unsubscribe(self, websocket: WebSocket, channel: str) -> None:
        """Unsubscribe a connection from a channel."""
        ws_id = id(websocket)
        if ws_id in self.connection_metadata:
            self.connection_metadata[ws_id]["subscriptions"].discard(channel)

    async def broadcast(self, message: dict, channel: str | None = None) -> None:
        """Broadcast message to all connections or specific channel subscribers."""
        payload = json.dumps(message)
        disconnected = []

        for websocket in list(self.active_connections):
            try:
                # If channel specified, only send to subscribers
                if channel:
                    ws_id = id(websocket)
                    metadata = self.connection_metadata.get(ws_id, {})
                    subscriptions = metadata.get("subscriptions", set())
                    if channel not in subscriptions and "*" not in subscriptions:
                        continue

                await websocket.send_text(payload)
            except Exception as e:
                logger.warning("websocket_send_error", error=str(e))
                disconnected.append(websocket)

        # Clean up disconnected sockets
        for ws in disconnected:
            await self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """Send message to a specific connection."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error("websocket_personal_send_error", error=str(e))

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


# Global connection manager instance
connection_manager = ConnectionManager()


class DashboardEventEmitter:
    """Emits events to the real-time dashboard."""

    def __init__(self, manager: ConnectionManager):
        self.manager = manager

    async def emit_conversation_started(
        self,
        conversation_id: str,
        channel: str,
        customer_phone: str,
        customer_name: str | None = None,
    ) -> None:
        """Emit when a new conversation starts."""
        await self.manager.broadcast(
            {
                "event": "conversation.started",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "conversation_id": conversation_id,
                    "channel": channel,
                    "customer_phone": customer_phone[-4:],  # Last 4 digits only
                    "customer_name": customer_name,
                },
            },
            channel="conversations",
        )

    async def emit_message_received(
        self,
        conversation_id: str,
        message_type: str,
        content: str,
        direction: str,
    ) -> None:
        """Emit when a message is received or sent."""
        await self.manager.broadcast(
            {
                "event": "message.received",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "conversation_id": conversation_id,
                    "message_type": message_type,
                    "content": content[:200] + "..." if len(content) > 200 else content,
                    "direction": direction,
                },
            },
            channel="conversations",
        )

    async def emit_transcription_update(
        self,
        call_id: str,
        transcript: str,
        is_final: bool = False,
    ) -> None:
        """Emit live transcription updates during calls."""
        await self.manager.broadcast(
            {
                "event": "transcription.update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "call_id": call_id,
                    "transcript": transcript,
                    "is_final": is_final,
                },
            },
            channel="transcriptions",
        )

    async def emit_lead_score_update(
        self,
        conversation_id: str,
        phone: str,
        old_score: int,
        new_score: int,
        qualification_data: dict,
    ) -> None:
        """Emit when a lead score changes."""
        await self.manager.broadcast(
            {
                "event": "lead.score_updated",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "conversation_id": conversation_id,
                    "phone": phone[-4:],
                    "old_score": old_score,
                    "new_score": new_score,
                    "is_hot": new_score >= 70,
                    "qualification": qualification_data,
                },
            },
            channel="leads",
        )

    async def emit_booking_created(
        self,
        booking_id: str,
        customer_name: str,
        date: str,
        time: str,
        service_type: str,
    ) -> None:
        """Emit when a booking is created."""
        await self.manager.broadcast(
            {
                "event": "booking.created",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "booking_id": booking_id,
                    "customer_name": customer_name,
                    "date": date,
                    "time": time,
                    "service_type": service_type,
                },
            },
            channel="bookings",
        )

    async def emit_metrics_update(self, metrics: dict) -> None:
        """Emit periodic metrics updates."""
        await self.manager.broadcast(
            {
                "event": "metrics.update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": metrics,
            },
            channel="metrics",
        )

    async def emit_agent_status(
        self,
        status: str,
        active_conversations: int,
        queue_size: int,
    ) -> None:
        """Emit agent status updates."""
        await self.manager.broadcast(
            {
                "event": "agent.status",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "status": status,
                    "active_conversations": active_conversations,
                    "queue_size": queue_size,
                },
            },
            channel="agent",
        )

    async def emit_error(
        self,
        error_type: str,
        message: str,
        conversation_id: str | None = None,
    ) -> None:
        """Emit error events."""
        await self.manager.broadcast(
            {
                "event": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "error_type": error_type,
                    "message": message,
                    "conversation_id": conversation_id,
                },
            },
            channel="errors",
        )


# Global event emitter instance
dashboard_emitter = DashboardEventEmitter(connection_manager)
