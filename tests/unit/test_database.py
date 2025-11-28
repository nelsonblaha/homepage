"""Tests for database operations and migrations."""
import pytest


@pytest.mark.asyncio
async def test_init_creates_tables(test_db):
    """Test that init_db creates all required tables."""
    from database import get_db

    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    assert "services" in tables
    assert "friends" in tables
    assert "friend_services" in tables
    assert "sessions" in tables
    assert "access_requests" in tables


@pytest.mark.asyncio
async def test_services_table_has_required_columns(test_db):
    """Test services table has all expected columns."""
    from database import get_db

    async with await get_db() as db:
        cursor = await db.execute("PRAGMA table_info(services)")
        columns = {row[1] for row in await cursor.fetchall()}

    expected = {"id", "name", "url", "icon", "description", "display_order",
                "subdomain", "stack", "is_default", "auth_type"}
    assert expected.issubset(columns)


@pytest.mark.asyncio
async def test_friends_table_has_integration_columns(test_db):
    """Test friends table has columns for service integrations."""
    from database import get_db

    async with await get_db() as db:
        cursor = await db.execute("PRAGMA table_info(friends)")
        columns = {row[1] for row in await cursor.fetchall()}

    # Check for integration-specific columns
    assert "plex_user_id" in columns
    assert "ombi_user_id" in columns
    assert "jellyfin_user_id" in columns
    assert "nextcloud_user_id" in columns
    assert "overseerr_user_id" in columns
    assert "mattermost_user_id" in columns


@pytest.mark.asyncio
async def test_can_insert_and_retrieve_service(test_db):
    """Test basic CRUD for services table."""
    from database import get_db

    async with await get_db() as db:
        # Insert
        await db.execute(
            "INSERT INTO services (name, url, icon, description) VALUES (?, ?, ?, ?)",
            ("Test Service", "https://test.local", "🧪", "A test service")
        )
        await db.commit()

        # Retrieve
        cursor = await db.execute("SELECT name, url, icon FROM services WHERE name = ?",
                                  ("Test Service",))
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "Test Service"
    assert row[1] == "https://test.local"
    assert row[2] == "🧪"


@pytest.mark.asyncio
async def test_can_insert_and_retrieve_friend(test_db):
    """Test basic CRUD for friends table."""
    from database import get_db

    async with await get_db() as db:
        # Insert
        await db.execute(
            "INSERT INTO friends (name, token) VALUES (?, ?)",
            ("Test Friend", "abc123")
        )
        await db.commit()

        # Retrieve
        cursor = await db.execute("SELECT name, token FROM friends WHERE token = ?",
                                  ("abc123",))
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "Test Friend"
    assert row[1] == "abc123"


@pytest.mark.asyncio
async def test_friend_service_relationship(test_db):
    """Test friend-service many-to-many relationship."""
    from database import get_db

    async with await get_db() as db:
        # Create service and friend
        await db.execute(
            "INSERT INTO services (name, url) VALUES (?, ?)",
            ("Plex", "https://plex.local")
        )
        await db.execute(
            "INSERT INTO friends (name, token) VALUES (?, ?)",
            ("Alice", "alice123")
        )
        await db.commit()

        # Get IDs
        cursor = await db.execute("SELECT id FROM services WHERE name = 'Plex'")
        service_id = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT id FROM friends WHERE name = 'Alice'")
        friend_id = (await cursor.fetchone())[0]

        # Create relationship
        await db.execute(
            "INSERT INTO friend_services (friend_id, service_id) VALUES (?, ?)",
            (friend_id, service_id)
        )
        await db.commit()

        # Verify relationship
        cursor = await db.execute(
            """SELECT f.name, s.name
               FROM friend_services fs
               JOIN friends f ON fs.friend_id = f.id
               JOIN services s ON fs.service_id = s.id
               WHERE f.name = 'Alice'"""
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "Alice"
    assert row[1] == "Plex"


@pytest.mark.asyncio
async def test_cascade_delete_friend_removes_services(test_db):
    """Test that deleting a friend cascades to friend_services."""
    from database import get_db

    async with await get_db() as db:
        # Setup
        await db.execute("INSERT INTO services (name, url) VALUES ('Svc', 'https://svc.local')")
        await db.execute("INSERT INTO friends (name, token) VALUES ('Bob', 'bob123')")
        await db.commit()

        cursor = await db.execute("SELECT id FROM services")
        service_id = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT id FROM friends")
        friend_id = (await cursor.fetchone())[0]

        await db.execute("INSERT INTO friend_services VALUES (?, ?)", (friend_id, service_id))
        await db.commit()

        # Delete friend
        await db.execute("DELETE FROM friends WHERE id = ?", (friend_id,))
        await db.commit()

        # Verify cascade
        cursor = await db.execute("SELECT COUNT(*) FROM friend_services")
        count = (await cursor.fetchone())[0]

    assert count == 0


# =============================================================================
# ACCESS REQUESTS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_access_request_table_exists(test_db):
    """Test access_requests table has correct schema."""
    from database import get_db

    async with await get_db() as db:
        cursor = await db.execute("PRAGMA table_info(access_requests)")
        columns = {row[1] for row in await cursor.fetchall()}

    expected = {"id", "friend_id", "service_id", "requested_at", "status"}
    assert expected.issubset(columns)


@pytest.mark.asyncio
async def test_can_create_access_request(test_db):
    """Test creating an access request."""
    from database import get_db

    async with await get_db() as db:
        # Create service and friend first
        await db.execute("INSERT INTO services (name, url) VALUES ('Jellyfin', 'https://jf.local')")
        await db.execute("INSERT INTO friends (name, token) VALUES ('Charlie', 'charlie123')")
        await db.commit()

        cursor = await db.execute("SELECT id FROM services")
        service_id = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT id FROM friends")
        friend_id = (await cursor.fetchone())[0]

        # Create access request
        await db.execute(
            "INSERT INTO access_requests (friend_id, service_id, status) VALUES (?, ?, ?)",
            (friend_id, service_id, "pending")
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT status FROM access_requests WHERE friend_id = ? AND service_id = ?",
            (friend_id, service_id)
        )
        row = await cursor.fetchone()

    assert row[0] == "pending"


# =============================================================================
# SESSIONS TABLE TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_sessions_table_has_required_columns(test_db):
    """Test sessions table has correct schema."""
    from database import get_db

    async with await get_db() as db:
        cursor = await db.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in await cursor.fetchall()}

    expected = {"id", "token", "type", "user_id", "expires_at", "user_agent", "created_at"}
    assert expected.issubset(columns)


# =============================================================================
# SERVICE DEFAULT VALUES TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_service_default_values(test_db):
    """Test service table default values."""
    from database import get_db

    async with await get_db() as db:
        # Insert with minimal fields
        await db.execute(
            "INSERT INTO services (name, url) VALUES ('Minimal', 'https://min.local')"
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT display_order, is_default, auth_type, stack FROM services WHERE name = 'Minimal'"
        )
        row = await cursor.fetchone()

    assert row[0] == 0  # display_order default
    assert row[1] == 0  # is_default default (False = 0)
    assert row[2] == "none"  # auth_type default
    # stack can be empty string or NULL


# =============================================================================
# FRIEND DEFAULT VALUES TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_friend_default_values(test_db):
    """Test friend table default values."""
    from database import get_db

    async with await get_db() as db:
        await db.execute(
            "INSERT INTO friends (name, token) VALUES ('DefaultTest', 'def123')"
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT plex_user_id, ombi_user_id, jellyfin_user_id FROM friends WHERE token = 'def123'"
        )
        row = await cursor.fetchone()

    # Integration columns should default to empty or NULL
    assert row[0] in (None, "")
    assert row[1] in (None, "")
    assert row[2] in (None, "")


# =============================================================================
# UNIQUE CONSTRAINT TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_friend_token_unique(test_db):
    """Test that friend tokens must be unique."""
    from database import get_db
    import sqlite3

    async with await get_db() as db:
        await db.execute("INSERT INTO friends (name, token) VALUES ('F1', 'unique123')")
        await db.commit()

        # Try to insert duplicate token
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO friends (name, token) VALUES ('F2', 'unique123')")
            await db.commit()


# =============================================================================
# FOREIGN KEY CONSTRAINT TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_friend_services_requires_valid_friend(test_db):
    """Test that friend_services requires valid friend_id."""
    from database import get_db
    import sqlite3

    async with await get_db() as db:
        await db.execute("INSERT INTO services (name, url) VALUES ('ValidSvc', 'https://vs.local')")
        await db.commit()

        cursor = await db.execute("SELECT id FROM services")
        service_id = (await cursor.fetchone())[0]

        # Try to create relationship with non-existent friend
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO friend_services VALUES (9999, ?)", (service_id,))
            await db.commit()


@pytest.mark.asyncio
async def test_friend_services_requires_valid_service(test_db):
    """Test that friend_services requires valid service_id."""
    from database import get_db
    import sqlite3

    async with await get_db() as db:
        await db.execute("INSERT INTO friends (name, token) VALUES ('ValidFriend', 'vf123')")
        await db.commit()

        cursor = await db.execute("SELECT id FROM friends")
        friend_id = (await cursor.fetchone())[0]

        # Try to create relationship with non-existent service
        with pytest.raises(sqlite3.IntegrityError):
            await db.execute("INSERT INTO friend_services VALUES (?, 9999)", (friend_id,))
            await db.commit()
