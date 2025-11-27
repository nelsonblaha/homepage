"""Ombi integration for blaha.io"""
import os
import secrets
import httpx
from fastapi import APIRouter, Depends

from services.session import verify_admin

OMBI_URL = os.environ.get("OMBI_URL", "")
OMBI_API_KEY = os.environ.get("OMBI_API_KEY", "")

router = APIRouter(prefix="/api/ombi", tags=["ombi"])


async def create_ombi_user(username: str) -> dict | None:
    """Create an Ombi user with password. Returns user info including password."""
    if not OMBI_URL or not OMBI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            password = secrets.token_urlsafe(16)
            resp = await client.post(
                f"{OMBI_URL}/api/v1/Identity",
                headers={"ApiKey": OMBI_API_KEY, "Content-Type": "application/json"},
                json={
                    "userName": username,
                    "password": password,
                    "claims": [{"value": "RequestMovie", "enabled": True},
                              {"value": "RequestTv", "enabled": True}]
                },
                timeout=10.0
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                # Ombi API doesn't return ID on creation, need to fetch it
                user_id = data.get("id")
                if not user_id:
                    # Look up user by name to get ID
                    users_resp = await client.get(
                        f"{OMBI_URL}/api/v1/Identity/Users",
                        headers={"ApiKey": OMBI_API_KEY},
                        timeout=10.0
                    )
                    if users_resp.status_code == 200:
                        users = users_resp.json()
                        for user in users:
                            if user.get("userName") == username:
                                user_id = user.get("id")
                                break
                return {"id": user_id, "username": username, "password": password}
            print(f"Ombi create user failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Ombi error: {e}")
    return None


async def delete_ombi_user(user_id: str) -> bool:
    """Delete an Ombi user by ID."""
    if not OMBI_URL or not OMBI_API_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{OMBI_URL}/api/v1/Identity/{user_id}",
                headers={"ApiKey": OMBI_API_KEY},
                timeout=10.0
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        print(f"Ombi delete error: {e}")
    return False


async def authenticate_ombi(username: str, password: str) -> str | None:
    """Authenticate to Ombi and return JWT token."""
    if not OMBI_URL:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OMBI_URL}/api/v1/Token",
                headers={"Content-Type": "application/json"},
                json={"username": username, "password": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
    except Exception as e:
        print(f"Ombi auth error: {e}")
    return None


@router.get("/status")
async def ombi_status(_: bool = Depends(verify_admin)):
    """Check Ombi connection status."""
    if not OMBI_URL or not OMBI_API_KEY:
        return {"connected": False, "error": "Not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OMBI_URL}/api/v1/Status",
                headers={"ApiKey": OMBI_API_KEY},
                timeout=5.0
            )
            if resp.status_code == 200:
                return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
