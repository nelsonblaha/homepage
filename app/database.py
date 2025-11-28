import aiosqlite
import os
from pathlib import Path


def get_db_path() -> Path:
    """Get database path from environment (allows test override)."""
    return Path(os.environ.get("DB_PATH", "/app/data/homepage.db"))


async def init_db():
    """Initialize the database with required tables."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # =====================================================================
        # CREATE ALL TABLES FIRST
        # =====================================================================

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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                user_agent TEXT DEFAULT ''
            )
        """)

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

        # Activity log for admin dashboard
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                friend_id INTEGER,
                service_id INTEGER,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (friend_id) REFERENCES friends(id) ON DELETE SET NULL,
                FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
            )
        """)

        # =====================================================================
        # MIGRATIONS FOR services TABLE
        # =====================================================================

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

        # Migration: Add auth_type column (basic, jellyfin, ombi, none)
        try:
            await db.execute("ALTER TABLE services ADD COLUMN auth_type TEXT DEFAULT 'none'")
        except:
            pass  # Column already exists

        # Migration: Add github_repo column for CI status badges
        try:
            await db.execute("ALTER TABLE services ADD COLUMN github_repo TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # =====================================================================
        # MIGRATIONS FOR friends TABLE
        # =====================================================================

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

        # Migration: Add ombi_password column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN ombi_password TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add jellyfin_user_id column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN jellyfin_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add jellyfin_password column to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN jellyfin_password TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add nextcloud columns to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN nextcloud_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN nextcloud_password TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add overseerr columns to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN overseerr_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN overseerr_password TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add mattermost columns to friends
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN mattermost_user_id TEXT DEFAULT ''")
        except:
            pass  # Column already exists
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN mattermost_password TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # =====================================================================
        # FRIEND AUTHENTICATION MIGRATIONS
        # =====================================================================

        # Migration: Add password_hash for optional password authentication
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN password_hash TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add totp_secret for optional 2FA
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN totp_secret TEXT DEFAULT ''")
        except:
            pass  # Column already exists

        # Migration: Add usage_count to track token usage
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN usage_count INTEGER DEFAULT 0")
        except:
            pass  # Column already exists

        # Migration: Add password_required flag (0=no, 1=yes, 2=after_threshold)
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN password_required INTEGER DEFAULT 0")
        except:
            pass  # Column already exists

        # Migration: Add password_required_after threshold (usage count)
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN password_required_after INTEGER DEFAULT 10")
        except:
            pass  # Column already exists

        # Migration: Add expires_at for time-limited access
        try:
            await db.execute("ALTER TABLE friends ADD COLUMN expires_at TIMESTAMP DEFAULT NULL")
        except:
            pass  # Column already exists

        await db.commit()


class ForeignKeyConnection:
    """Wrapper that enables foreign keys on connection.

    Supports both patterns:
    - async with get_db() as db:
    - async with await get_db() as db:
    """

    def __init__(self, db_path):
        self._path = db_path
        self._conn = None

    def __await__(self):
        """Make this awaitable - returns self for compat with 'await get_db()'."""
        async def _identity():
            return self
        return _identity().__await__()

    async def __aenter__(self):
        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()
        return False


def get_db():
    """Get database connection with foreign keys enabled."""
    return ForeignKeyConnection(get_db_path())
