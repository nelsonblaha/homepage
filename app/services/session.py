"""Session management for blaha.io"""
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Cookie, HTTPException

from database import get_db

# Session durations
SESSION_DURATION_SHORT = timedelta(hours=24)
SESSION_DURATION_LONG = timedelta(days=30)  # "Remember me"


async def create_session(session_type: str, user_id: int = None, remember: bool = False, user_agent: str = "") -> tuple[str, datetime]:
    """Create a new session and store in database."""
    token = secrets.token_hex(32)
    duration = SESSION_DURATION_LONG if remember else SESSION_DURATION_SHORT
    expires_at = datetime.now() + duration

    async with await get_db() as db:
        await db.execute(
            "INSERT INTO sessions (token, type, user_id, expires_at, user_agent) VALUES (?, ?, ?, ?, ?)",
            (token, session_type, user_id, expires_at.isoformat(), user_agent)
        )
        await db.commit()

    return token, expires_at


async def validate_session(token: str) -> dict | None:
    """Validate a session token. Returns session info or None if invalid/expired."""
    if not token:
        return None

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE token = ?", (token,)
        )
        session = await cursor.fetchone()

        if not session:
            return None

        # Check expiry
        expires_at = datetime.fromisoformat(session["expires_at"])
        if datetime.now() > expires_at:
            await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
            await db.commit()
            return None

        return session


async def delete_session(token: str):
    """Delete a session from the database."""
    async with await get_db() as db:
        await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await db.commit()


async def cleanup_expired_sessions():
    """Remove all expired sessions."""
    async with await get_db() as db:
        await db.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(),))
        await db.commit()


# Dependency to verify admin session
async def verify_admin(admin_token: Optional[str] = Cookie(default=None)):
    session = await validate_session(admin_token)
    if not session or session["type"] != "admin":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True
