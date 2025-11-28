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


# =============================================================================
# SESSION DURATION TESTS
# =============================================================================

def test_session_duration_constants():
    """Test session duration constants are correct."""
    from services.session import SESSION_DURATION_SHORT, SESSION_DURATION_LONG

    assert SESSION_DURATION_SHORT == timedelta(hours=24)
    assert SESSION_DURATION_LONG == timedelta(days=30)


@pytest.mark.asyncio
async def test_remember_me_creates_long_session(test_db, test_env):
    """Test remember=True creates 30-day session."""
    from services.session import create_session, SESSION_DURATION_LONG

    token, expires_at = await create_session("admin", remember=True)

    # Should expire approximately 30 days from now
    expected_min = datetime.now() + SESSION_DURATION_LONG - timedelta(minutes=1)
    expected_max = datetime.now() + SESSION_DURATION_LONG + timedelta(minutes=1)
    assert expected_min <= expires_at <= expected_max


@pytest.mark.asyncio
async def test_no_remember_creates_short_session(test_db, test_env):
    """Test remember=False creates 24-hour session."""
    from services.session import create_session, SESSION_DURATION_SHORT

    token, expires_at = await create_session("admin", remember=False)

    # Should expire approximately 24 hours from now
    expected_min = datetime.now() + SESSION_DURATION_SHORT - timedelta(minutes=1)
    expected_max = datetime.now() + SESSION_DURATION_SHORT + timedelta(minutes=1)
    assert expected_min <= expires_at <= expected_max


# =============================================================================
# TOKEN GENERATION TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_session_token_uniqueness(test_db, test_env):
    """Test that session tokens are unique."""
    from services.session import create_session

    tokens = []
    for _ in range(5):
        token, _ = await create_session("admin")
        tokens.append(token)

    # All tokens should be unique
    assert len(set(tokens)) == 5


@pytest.mark.asyncio
async def test_session_token_format(test_db, test_env):
    """Test session token format."""
    from services.session import create_session

    token, _ = await create_session("admin")

    # Should be hex string
    assert all(c in '0123456789abcdef' for c in token)
    # 32 bytes = 64 hex chars
    assert len(token) == 64


# =============================================================================
# EMPTY TOKEN TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_validate_empty_token_returns_none(test_db, test_env):
    """Test that empty token returns None."""
    from services.session import validate_session

    assert await validate_session("") is None
    assert await validate_session(None) is None


# =============================================================================
# USER AGENT STORAGE TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_session_stores_user_agent(test_db, test_env):
    """Test session stores user agent."""
    from services.session import create_session, validate_session

    ua = "Mozilla/5.0 (Test Browser)"
    token, _ = await create_session("admin", user_agent=ua)

    session = await validate_session(token)
    assert session["user_agent"] == ua


# =============================================================================
# CLEANUP TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_cleanup_expired_sessions(test_db, test_env):
    """Test cleanup_expired_sessions removes expired sessions."""
    from services.session import cleanup_expired_sessions, validate_session
    from database import get_db
    import secrets

    # Create an expired session manually
    token = secrets.token_hex(32)
    async with await get_db() as db:
        expired_time = (datetime.now() - timedelta(days=1)).isoformat()
        await db.execute(
            "INSERT INTO sessions (token, type, user_id, expires_at) VALUES (?, ?, ?, ?)",
            (token, "admin", None, expired_time)
        )
        await db.commit()

    # Run cleanup
    await cleanup_expired_sessions()

    # Session should be gone
    session = await validate_session(token)
    assert session is None
