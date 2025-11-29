"""
WebSocket Manager for real-time updates.

Handles connection tracking and broadcasting of:
- Service health status changes
- Account provisioning status
- Jitsi participant counts
- Activity log entries
"""

import asyncio
import json
from typing import Dict, Set, Optional
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        # All active connections
        self.active_connections: Set[WebSocket] = set()
        # Map friend tokens to their connections (for targeted messages)
        self.friend_connections: Dict[str, Set[WebSocket]] = {}
        # Admin connections (no token)
        self.admin_connections: Set[WebSocket] = set()
        # Current state cache (for sending on connect)
        self.service_statuses: Dict[int, dict] = {}
        self.provisioning_statuses: Dict[str, dict] = {}  # key: f"{friend_id}:{service}"
        self.jitsi_participants: int = 0
        # Infrastructure health from blaha-health-daemon
        self.infra_health: Optional[dict] = None

    async def connect(self, websocket: WebSocket, token: Optional[str] = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)

        if token:
            if token not in self.friend_connections:
                self.friend_connections[token] = set()
            self.friend_connections[token].add(websocket)
        else:
            self.admin_connections.add(websocket)

        # Send current state snapshot
        await self._send_state_snapshot(websocket, token)

    def disconnect(self, websocket: WebSocket, token: Optional[str] = None):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)

        if token and token in self.friend_connections:
            self.friend_connections[token].discard(websocket)
            if not self.friend_connections[token]:
                del self.friend_connections[token]
        else:
            self.admin_connections.discard(websocket)

    async def _send_state_snapshot(self, websocket: WebSocket, token: Optional[str] = None):
        """Send current state to a newly connected client."""
        # Service statuses
        for service_id, status in self.service_statuses.items():
            await self._send_json(websocket, {
                "type": "service_status",
                "service_id": service_id,
                **status
            })

        # Provisioning statuses (filtered by friend if token provided)
        for key, status in self.provisioning_statuses.items():
            friend_id, service = key.split(":", 1)
            # For friends, only send their own provisioning status
            # For admins, send all
            if token is None or status.get("friend_token") == token:
                await self._send_json(websocket, {
                    "type": "account_status",
                    "friend_id": int(friend_id),
                    "service": service,
                    "status": status.get("status", "unknown")
                })

        # Jitsi participants
        await self._send_json(websocket, {
            "type": "jitsi_update",
            "participants": self.jitsi_participants
        })

        # Infrastructure health (admin only)
        if token is None and self.infra_health:
            await self._send_json(websocket, {
                "type": "infra_health",
                **self.infra_health
            })

    async def _send_json(self, websocket: WebSocket, data: dict):
        """Send JSON to a single websocket, handling errors."""
        try:
            await websocket.send_json(data)
        except Exception:
            # Connection probably closed
            pass

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)
            self.admin_connections.discard(conn)
            for token_conns in self.friend_connections.values():
                token_conns.discard(conn)

    async def broadcast_to_friend(self, token: str, message: dict):
        """Broadcast a message to a specific friend's connections."""
        if token not in self.friend_connections:
            return

        disconnected = set()
        for connection in self.friend_connections[token]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        for conn in disconnected:
            self.friend_connections[token].discard(conn)
            self.active_connections.discard(conn)

    async def broadcast_to_admins(self, message: dict):
        """Broadcast a message to all admin connections."""
        disconnected = set()
        for connection in self.admin_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        for conn in disconnected:
            self.admin_connections.discard(conn)
            self.active_connections.discard(conn)

    # State update methods (update cache and broadcast)

    async def update_service_status(self, service_id: int, health: str):
        """Update and broadcast service health status."""
        old_status = self.service_statuses.get(service_id, {}).get("health")
        if old_status == health:
            return  # No change

        self.service_statuses[service_id] = {"health": health}
        await self.broadcast({
            "type": "service_status",
            "service_id": service_id,
            "health": health
        })

    async def update_provisioning_status(
        self,
        friend_id: int,
        service: str,
        status: str,
        friend_token: Optional[str] = None
    ):
        """Update and broadcast account provisioning status."""
        key = f"{friend_id}:{service}"

        if status in ("ready", "failed"):
            # Remove from cache when complete
            self.provisioning_statuses.pop(key, None)
        else:
            self.provisioning_statuses[key] = {
                "status": status,
                "friend_token": friend_token
            }

        message = {
            "type": "account_status",
            "friend_id": friend_id,
            "service": service,
            "status": status
        }

        # Broadcast to the specific friend and all admins
        if friend_token:
            await self.broadcast_to_friend(friend_token, message)
        await self.broadcast_to_admins(message)

    async def update_jitsi_participants(self, count: int):
        """Update and broadcast Jitsi participant count."""
        if self.jitsi_participants == count:
            return  # No change

        self.jitsi_participants = count
        await self.broadcast({
            "type": "jitsi_update",
            "participants": count
        })

    async def broadcast_activity(self, entry: dict):
        """Broadcast a new activity log entry to admins."""
        await self.broadcast_to_admins({
            "type": "activity",
            "entry": entry
        })

    async def update_infra_health(self, health_data: dict):
        """Update and broadcast infrastructure health to admins."""
        self.infra_health = health_data
        await self.broadcast_to_admins({
            "type": "infra_health",
            **health_data
        })


# Global instance
manager = ConnectionManager()
