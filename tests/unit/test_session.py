"""Tests for session management."""
import pytest
from datetime import datetime, timedelta


@pytest.mark.asyncio
async def test_create_admin_session(test_db, test_env):
    """Test creating an admin session."""
    from services.session import create_session, validate_session

    token, expires_at = await create_session("admin", user_id=None, remember=True)
    assert token is not None
    assert len(token) == 64  # hex(32) = 64 chars

    session = await validate_session(token)
    assert session is not None
    assert session["type"] == "admin"


@pytest.mark.asyncio
async def test_create_friend_session(test_db, test_env):
    """Test creating a friend session."""
    from services.session import create_session, validate_session
    from database import get_db

    # Create a friend first
    async with await get_db() as db:
        await db.execute("INSERT INTO friends (name, token) VALUES (?, ?)",
                        ("TestFriend", "friend123"))
        await db.commit()
        cursor = await db.execute("SELECT id FROM friends WHERE token = 'friend123'")
        friend_id = (await cursor.fetchone())[0]

    token, _ = await create_session("friend", user_id=friend_id, remember=True)
    assert token is not None

    session = await validate_session(token)
    assert session is not None
    assert session["type"] == "friend"
    assert session["user_id"] == friend_id


@pytest.mark.asyncio
async def test_invalid_session_returns_none(test_db, test_env):
    """Test that invalid tokens return None."""
    from services.session import validate_session

    session = await validate_session("nonexistent_token_12345")
    assert session is None


@pytest.mark.asyncio
async def test_session_expiry(test_db, test_env):
    """Test that expired sessions are rejected."""
    from services.session import validate_session
    from database import get_db
    import secrets

    # Manually create an expired session
    token = secrets.token_hex(32)
    async with await get_db() as db:
        expired_time = (datetime.now() - timedelta(days=1)).isoformat()
        await db.execute(
            """INSERT INTO sessions (token, type, user_id, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token, "admin", None, expired_time)
        )
        await db.commit()

    session = await validate_session(token)
    assert session is None


@pytest.mark.asyncio
async def test_delete_session(test_db, test_env):
    """Test deleting a session (logout)."""
    from services.session import create_session, validate_session, delete_session

    token, _ = await create_session("admin", user_id=None, remember=True)
    assert token is not None

    # Verify it exists
    session = await validate_session(token)
    assert session is not None

    # Delete it
    await delete_session(token)

    # Verify it's gone
    session = await validate_session(token)
    assert session is None
