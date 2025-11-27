"""Plex integration for blaha.io"""
import os
from fastapi import APIRouter, HTTPException, Depends

from database import get_db
from services.session import verify_admin

PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
PLEX_URL = os.environ.get("PLEX_URL", "http://localhost:32400")

router = APIRouter(prefix="/api/plex", tags=["plex"])


def get_plex_account():
    """Get Plex account connection."""
    if not PLEX_TOKEN:
        return None
    try:
        from plexapi.myplex import MyPlexAccount
        return MyPlexAccount(token=PLEX_TOKEN)
    except Exception as e:
        print(f"Plex connection error: {e}")
        return None


def get_plex_server():
    """Get Plex server connection."""
    if not PLEX_TOKEN:
        return None
    try:
        from plexapi.server import PlexServer
        return PlexServer(PLEX_URL, PLEX_TOKEN)
    except Exception as e:
        print(f"Plex server error: {e}")
        return None


@router.get("/status")
async def plex_status(_: bool = Depends(verify_admin)):
    """Check Plex connection status."""
    account = get_plex_account()
    if not account:
        return {"connected": False, "error": "No Plex token configured"}
    try:
        return {
            "connected": True,
            "username": account.username,
            "email": account.email
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.get("/home-users")
async def list_plex_home_users(_: bool = Depends(verify_admin)):
    """List existing Plex Home users."""
    account = get_plex_account()
    if not account:
        raise HTTPException(status_code=400, detail="Plex not configured")
    try:
        users = []
        for user in account.users():
            if user.home:  # Only home users
                users.append({
                    "id": str(user.id),
                    "title": user.title,
                    "username": user.username,
                    "restricted": user.restricted,
                    "thumb": user.thumb
                })
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def create_plex_user(friend_name: str) -> dict | None:
    """Create a Plex managed user for a friend."""
    account = get_plex_account()
    if not account:
        return None
    try:
        plex_user = account.createHomeUser(friend_name, server=get_plex_server())
        return {"id": str(plex_user.id), "username": plex_user.title}
    except Exception as e:
        print(f"Failed to create Plex user: {e}")
        return None


async def delete_plex_user(plex_user_id: str) -> bool:
    """Delete a Plex user by ID."""
    account = get_plex_account()
    if not account:
        return False
    try:
        for user in account.users():
            if str(user.id) == plex_user_id:
                user.delete()
                return True
    except Exception as e:
        print(f"Failed to delete Plex user: {e}")
    return False
