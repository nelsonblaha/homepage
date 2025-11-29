"""Tests for background tasks."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


@pytest.mark.asyncio
async def test_check_service_health_up():
    """Test health check returns 'up' for 200 response."""
    from services.background import check_service_health

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        result = await check_service_health(1, "http://example.com")

    assert result == "up"


@pytest.mark.asyncio
async def test_check_service_health_auth_required():
    """Test health check returns 'auth_required' for 401 response."""
    from services.background import check_service_health

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        result = await check_service_health(1, "http://example.com")

    assert result == "auth_required"


@pytest.mark.asyncio
async def test_check_service_health_down_on_500():
    """Test health check returns 'down' for 500 response."""
    from services.background import check_service_health

    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            return_value=mock_response
        )
        result = await check_service_health(1, "http://example.com")

    assert result == "down"


@pytest.mark.asyncio
async def test_check_service_health_down_on_error():
    """Test health check returns 'down' on connection error."""
    from services.background import check_service_health

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await check_service_health(1, "http://example.com")

    assert result == "down"


@pytest.mark.asyncio
async def test_check_service_health_redirect_followed():
    """Test health check follows redirects."""
    from services.background import check_service_health

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = mock_client.return_value.__aenter__.return_value
        mock_instance.get = AsyncMock(return_value=mock_response)
        result = await check_service_health(1, "http://example.com")

    # Verify AsyncClient was created with follow_redirects=True
    mock_client.assert_called_with(timeout=10.0, follow_redirects=True)
    assert result == "up"


@pytest.mark.asyncio
async def test_start_background_tasks():
    """Test that background tasks are created."""
    from services.background import start_background_tasks
    import asyncio

    with patch("services.background.health_check_loop", new_callable=AsyncMock) as mock_health:
        with patch("services.background.jitsi_check_loop", new_callable=AsyncMock) as mock_jitsi:
            with patch("services.background.infra_health_check_loop", new_callable=AsyncMock) as mock_infra:
                tasks = await start_background_tasks()

                assert len(tasks) == 3
                assert all(isinstance(t, asyncio.Task) for t in tasks)

                # Cancel tasks to clean up
                for task in tasks:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
