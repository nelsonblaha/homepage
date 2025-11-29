"""Tests for WebSocket manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.accepted = False
        self.messages = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.closed:
            raise Exception("WebSocket closed")
        self.messages.append(data)

    def close(self):
        self.closed = True


@pytest.fixture
def ws_manager():
    """Create a fresh ConnectionManager for each test."""
    from websocket import ConnectionManager
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_without_token(ws_manager):
    """Test connecting as admin (no token)."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)

    assert ws.accepted
    assert ws in ws_manager.active_connections
    assert ws in ws_manager.admin_connections


@pytest.mark.asyncio
async def test_connect_with_token(ws_manager):
    """Test connecting as friend (with token)."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token="friend123")

    assert ws.accepted
    assert ws in ws_manager.active_connections
    assert "friend123" in ws_manager.friend_connections
    assert ws in ws_manager.friend_connections["friend123"]


@pytest.mark.asyncio
async def test_disconnect_admin(ws_manager):
    """Test disconnecting admin connection."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)
    ws_manager.disconnect(ws, token=None)

    assert ws not in ws_manager.active_connections
    assert ws not in ws_manager.admin_connections


@pytest.mark.asyncio
async def test_disconnect_friend(ws_manager):
    """Test disconnecting friend connection."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token="friend123")
    ws_manager.disconnect(ws, token="friend123")

    assert ws not in ws_manager.active_connections
    assert "friend123" not in ws_manager.friend_connections


@pytest.mark.asyncio
async def test_broadcast(ws_manager):
    """Test broadcasting to all connections."""
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    await ws_manager.connect(ws1, token=None)
    await ws_manager.connect(ws2, token="friend123")

    # Clear initial state messages
    ws1.messages.clear()
    ws2.messages.clear()

    await ws_manager.broadcast({"type": "test", "data": "hello"})

    assert {"type": "test", "data": "hello"} in ws1.messages
    assert {"type": "test", "data": "hello"} in ws2.messages


@pytest.mark.asyncio
async def test_broadcast_to_admins(ws_manager):
    """Test broadcasting only to admin connections."""
    admin_ws = MockWebSocket()
    friend_ws = MockWebSocket()
    await ws_manager.connect(admin_ws, token=None)
    await ws_manager.connect(friend_ws, token="friend123")

    admin_ws.messages.clear()
    friend_ws.messages.clear()

    await ws_manager.broadcast_to_admins({"type": "admin_only"})

    assert {"type": "admin_only"} in admin_ws.messages
    assert {"type": "admin_only"} not in friend_ws.messages


@pytest.mark.asyncio
async def test_broadcast_to_friend(ws_manager):
    """Test broadcasting to specific friend."""
    friend1_ws = MockWebSocket()
    friend2_ws = MockWebSocket()
    await ws_manager.connect(friend1_ws, token="friend1")
    await ws_manager.connect(friend2_ws, token="friend2")

    friend1_ws.messages.clear()
    friend2_ws.messages.clear()

    await ws_manager.broadcast_to_friend("friend1", {"type": "for_friend1"})

    assert {"type": "for_friend1"} in friend1_ws.messages
    assert {"type": "for_friend1"} not in friend2_ws.messages


@pytest.mark.asyncio
async def test_update_service_status(ws_manager):
    """Test service status update broadcasts."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)
    ws.messages.clear()

    await ws_manager.update_service_status(1, "up")

    assert ws_manager.service_statuses[1] == {"health": "up"}
    assert {"type": "service_status", "service_id": 1, "health": "up"} in ws.messages


@pytest.mark.asyncio
async def test_update_service_status_no_change(ws_manager):
    """Test that unchanged status doesn't broadcast."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)

    await ws_manager.update_service_status(1, "up")
    ws.messages.clear()

    # Same status again
    await ws_manager.update_service_status(1, "up")

    assert len(ws.messages) == 0  # No new message


@pytest.mark.asyncio
async def test_update_provisioning_status(ws_manager):
    """Test provisioning status update."""
    admin_ws = MockWebSocket()
    friend_ws = MockWebSocket()
    await ws_manager.connect(admin_ws, token=None)
    await ws_manager.connect(friend_ws, token="friend123")

    admin_ws.messages.clear()
    friend_ws.messages.clear()

    await ws_manager.update_provisioning_status(
        friend_id=1,
        service="ombi",
        status="provisioning",
        friend_token="friend123"
    )

    # Both should receive the message
    expected = {
        "type": "account_status",
        "friend_id": 1,
        "service": "ombi",
        "status": "provisioning"
    }
    assert expected in admin_ws.messages
    assert expected in friend_ws.messages

    # Should be cached
    assert "1:ombi" in ws_manager.provisioning_statuses


@pytest.mark.asyncio
async def test_provisioning_complete_removes_from_cache(ws_manager):
    """Test that completed provisioning is removed from cache."""
    await ws_manager.update_provisioning_status(1, "ombi", "provisioning", "token")
    assert "1:ombi" in ws_manager.provisioning_statuses

    await ws_manager.update_provisioning_status(1, "ombi", "ready", "token")
    assert "1:ombi" not in ws_manager.provisioning_statuses


@pytest.mark.asyncio
async def test_update_jitsi_participants(ws_manager):
    """Test Jitsi participant count update."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)
    ws.messages.clear()

    await ws_manager.update_jitsi_participants(5)

    assert ws_manager.jitsi_participants == 5
    assert {"type": "jitsi_update", "participants": 5} in ws.messages


@pytest.mark.asyncio
async def test_jitsi_no_change_no_broadcast(ws_manager):
    """Test that unchanged Jitsi count doesn't broadcast."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)

    await ws_manager.update_jitsi_participants(5)
    ws.messages.clear()

    await ws_manager.update_jitsi_participants(5)
    assert len(ws.messages) == 0


@pytest.mark.asyncio
async def test_state_snapshot_on_connect(ws_manager):
    """Test that new connections receive current state."""
    # Set up some state first
    ws_manager.service_statuses[1] = {"health": "up"}
    ws_manager.service_statuses[2] = {"health": "down"}
    ws_manager.jitsi_participants = 3

    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)

    # Should have received state snapshot
    assert {"type": "service_status", "service_id": 1, "health": "up"} in ws.messages
    assert {"type": "service_status", "service_id": 2, "health": "down"} in ws.messages
    assert {"type": "jitsi_update", "participants": 3} in ws.messages


@pytest.mark.asyncio
async def test_broadcast_activity(ws_manager):
    """Test activity broadcast goes only to admins."""
    admin_ws = MockWebSocket()
    friend_ws = MockWebSocket()
    await ws_manager.connect(admin_ws, token=None)
    await ws_manager.connect(friend_ws, token="friend123")

    admin_ws.messages.clear()
    friend_ws.messages.clear()

    entry = {"action": "login", "user": "test"}
    await ws_manager.broadcast_activity(entry)

    assert {"type": "activity", "entry": entry} in admin_ws.messages
    assert {"type": "activity", "entry": entry} not in friend_ws.messages


@pytest.mark.asyncio
async def test_disconnected_client_removed_on_broadcast(ws_manager):
    """Test that failed sends remove the connection."""
    ws = MockWebSocket()
    await ws_manager.connect(ws, token=None)
    ws.messages.clear()

    # Simulate closed connection
    ws.closed = True

    await ws_manager.broadcast({"type": "test"})

    # Should have been removed
    assert ws not in ws_manager.active_connections
    assert ws not in ws_manager.admin_connections
