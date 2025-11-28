"""Tests for activity tracking service."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.row_factory = None
    return db


@pytest.mark.asyncio
async def test_log_activity_page_view(mock_db):
    """Test logging a page view activity."""
    import sys
    sys.path.insert(0, 'app')
    from services.activity import log_activity, ACTION_PAGE_VIEW

    await log_activity(mock_db, ACTION_PAGE_VIEW, friend_id=1)

    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert "INSERT INTO activity_log" in call_args[0][0]
    assert call_args[0][1][0] == 1  # friend_id
    assert call_args[0][1][2] == ACTION_PAGE_VIEW  # action


@pytest.mark.asyncio
async def test_log_activity_service_click(mock_db):
    """Test logging a service click activity."""
    import sys
    sys.path.insert(0, 'app')
    from services.activity import log_activity, ACTION_SERVICE_CLICK

    await log_activity(mock_db, ACTION_SERVICE_CLICK, friend_id=2, service_id=5)

    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert call_args[0][1][0] == 2  # friend_id
    assert call_args[0][1][1] == 5  # service_id
    assert call_args[0][1][2] == ACTION_SERVICE_CLICK  # action


@pytest.mark.asyncio
async def test_log_activity_with_details(mock_db):
    """Test logging activity with extra details."""
    import sys
    sys.path.insert(0, 'app')
    from services.activity import log_activity, ACTION_SERVICE_CLICK

    await log_activity(
        mock_db, ACTION_SERVICE_CLICK,
        friend_id=1, service_id=3,
        details="nginx:jellyfin"
    )

    call_args = mock_db.execute.call_args
    assert call_args[0][1][3] == "nginx:jellyfin"  # details


@pytest.mark.asyncio
async def test_get_recent_activity(mock_db):
    """Test fetching recent activity."""
    import sys
    sys.path.insert(0, 'app')
    from services.activity import get_recent_activity

    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[
        {
            "id": 1, "action": "page_view", "details": "",
            "created_at": "2024-01-01T12:00:00",
            "friend_id": 1, "friend_name": "Alice",
            "service_id": None, "service_name": None
        }
    ])
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    result = await get_recent_activity(mock_db, limit=10)

    assert len(result) == 1
    assert result[0]["friend_name"] == "Alice"
    mock_db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_activity_stats(mock_db):
    """Test fetching activity statistics."""
    import sys
    sys.path.insert(0, 'app')
    from services.activity import get_activity_stats

    # Mock multiple queries for stats
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value={"count": 10})
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    result = await get_activity_stats(mock_db, days=7)

    assert result["period_days"] == 7
    assert "page_views" in result
    assert "service_clicks" in result
    assert "active_friends" in result
    assert "top_services" in result
    assert "top_friends" in result
