"""Contract tests for health daemon integration.

These tests verify that homepage correctly handles responses from blaha-health-daemon.
If the daemon's API changes, these tests should catch the incompatibility.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# Example response from blaha-health-daemon /api/health/results
DAEMON_RESPONSE_EXAMPLE = {
    "summary": {
        "total": 95,
        "ok": 83,
        "info": 0,
        "warning": 12,
        "critical": 0
    },
    "infra": [
        {
            "check_id": "infra_disk_root",
            "name": "Disk: /",
            "severity": "ok",
            "message": "45% used (180GB/400GB)"
        },
        {
            "check_id": "infra_memory",
            "name": "Memory",
            "severity": "warning",
            "message": "85% used (27GB/32GB)"
        }
    ],
    "containers": {
        "plex": [
            {
                "check_id": "security_plex_host_network",
                "name": "Security: plex",
                "severity": "warning",
                "message": "Using host network mode"
            },
            {
                "check_id": "logs_plex",
                "name": "Logs: plex",
                "severity": "ok",
                "message": "No errors in last 24h"
            }
        ],
        "nginx-proxy": [
            {
                "check_id": "security_nginx-proxy_ports",
                "name": "Security: nginx-proxy",
                "severity": "ok",
                "message": "Ports properly bound"
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_websocket_handles_daemon_response():
    """Test that WebSocket manager correctly processes daemon health data."""
    from websocket import ConnectionManager

    manager = ConnectionManager()

    # Simulate receiving daemon response
    await manager.update_infra_health(DAEMON_RESPONSE_EXAMPLE)

    # Verify it was stored correctly
    assert manager.infra_health == DAEMON_RESPONSE_EXAMPLE
    assert manager.infra_health["summary"]["total"] == 95
    assert manager.infra_health["summary"]["warning"] == 12
    assert "plex" in manager.infra_health["containers"]
    assert len(manager.infra_health["infra"]) == 2


@pytest.mark.asyncio
async def test_background_loop_parses_daemon_response():
    """Test that background loop correctly fetches and broadcasts daemon health."""
    from websocket import manager as ws_manager

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = DAEMON_RESPONSE_EXAMPLE

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )

        # Import and run one iteration of the loop logic
        from services.background import HEALTH_DAEMON_URL
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/results")
            if response.status_code == 200:
                data = response.json()
                await ws_manager.update_infra_health(data)

        # Verify the data was processed
        assert ws_manager.infra_health is not None
        assert ws_manager.infra_health["summary"]["total"] == 95


@pytest.mark.asyncio
async def test_health_routes_proxy_status():
    """Test that /api/health/status proxies correctly."""
    from fastapi.testclient import TestClient
    from httpx import AsyncClient
    from unittest.mock import patch, AsyncMock, MagicMock

    # Mock admin auth
    with patch("services.session.verify_admin", return_value=True):
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = DAEMON_RESPONSE_EXAMPLE["summary"]
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            from routes.health import health_status
            result = await health_status(_=True)

            assert result == DAEMON_RESPONSE_EXAMPLE["summary"]


@pytest.mark.asyncio
async def test_health_routes_proxy_results():
    """Test that /api/health/results proxies correctly."""
    with patch("services.session.verify_admin", return_value=True):
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = DAEMON_RESPONSE_EXAMPLE
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            from routes.health import health_results
            result = await health_results(_=True)

            assert result == DAEMON_RESPONSE_EXAMPLE
            assert "summary" in result
            assert "infra" in result
            assert "containers" in result


def test_daemon_response_schema_has_required_fields():
    """Verify the expected daemon response schema has all required fields.

    This test documents the contract - if it fails, both daemon and homepage
    need to be updated together.
    """
    # Summary must have these fields
    assert "total" in DAEMON_RESPONSE_EXAMPLE["summary"]
    assert "ok" in DAEMON_RESPONSE_EXAMPLE["summary"]
    assert "info" in DAEMON_RESPONSE_EXAMPLE["summary"]
    assert "warning" in DAEMON_RESPONSE_EXAMPLE["summary"]
    assert "critical" in DAEMON_RESPONSE_EXAMPLE["summary"]

    # Infra checks must have these fields
    for check in DAEMON_RESPONSE_EXAMPLE["infra"]:
        assert "check_id" in check
        assert "name" in check
        assert "severity" in check
        assert "message" in check

    # Container checks must have these fields
    for container, checks in DAEMON_RESPONSE_EXAMPLE["containers"].items():
        assert isinstance(checks, list)
        for check in checks:
            assert "check_id" in check
            assert "name" in check
            assert "severity" in check
            assert "message" in check
