import aiosqlite
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", "/app/data/blaha.db"))

async def init_db():
    """Initialize the database with required tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                icon TEXT DEFAULT '',
                description TEXT DEFAULT '',
                display_order INTEGER DEFAULT 0,
                subdomain TEXT DEFAULT ''
            )
        """)

        # Migration: Add subdomain column if it doesn't exist
        try:
            await db.execute("ALTER TABLE services ADD COLUMN subdomain TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add stack column if it doesn't exist
        try:
            await db.execute("ALTER TABLE services ADD COLUMN stack TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add is_default column if it doesn't exist
        try:
            await db.execute("ALTER TABLE services ADD COLUMN is_default INTEGER DEFAULT 0")
        except:
            pass  # Column already exists

        # Migration: Add plex_user_id column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN plex_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add plex_pin column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN plex_pin TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add ombi_user_id column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN ombi_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add jellyfin_user_id column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN jellyfin_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        await db.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_visit TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS friend_services (
                friend_id INTEGER REFERENCES friends(id) ON DELETE CASCADE,
                service_id INTEGER REFERENCES services(id) ON DELETE CASCADE,
                PRIMARY KEY (friend_id, service_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS access_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                friend_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (friend_id) REFERENCES friends(id) ON DELETE CASCADE,
                FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
            )
        """)

        await db.commit()

async def get_db():
    """Get database connection."""
    return aiosqlite.connect(DB_PATH)
