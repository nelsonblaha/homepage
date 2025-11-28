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
