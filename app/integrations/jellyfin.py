"""Jellyfin integration - auto-login via localStorage token injection"""
import os
import secrets
import httpx
from fastapi import APIRouter, Depends

from services.session import verify_admin

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")

router = APIRouter(prefix="/api/jellyfin", tags=["jellyfin"])


async def create_jellyfin_user(username: str) -> dict | None:
    """Create a Jellyfin user with a password. Returns user info or None on failure."""
    if not JELLYFIN_URL or not JELLYFIN_API_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            # Create user
            resp = await client.post(
                f"{JELLYFIN_URL}/Users/New",
                headers={"X-Emby-Token": JELLYFIN_API_KEY, "Content-Type": "application/json"},
                json={"Name": username},
                timeout=10.0
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                user_id = data.get("Id")

                # Set a password for the user
                password = secrets.token_urlsafe(16)
                pwd_resp = await client.post(
                    f"{JELLYFIN_URL}/Users/{user_id}/Password",
                    headers={"X-Emby-Token": JELLYFIN_API_KEY, "Content-Type": "application/json"},
                    json={"NewPw": password},
                    timeout=10.0
                )
                if pwd_resp.status_code not in (200, 204):
                    print(f"Jellyfin set password failed: {pwd_resp.status_code}")

                return {"id": user_id, "username": data.get("Name"), "password": password}
            print(f"Jellyfin create user failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Jellyfin error: {e}")
    return None


async def delete_jellyfin_user(user_id: str) -> bool:
    """Delete a Jellyfin user by ID."""
    if not JELLYFIN_URL or not JELLYFIN_API_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{JELLYFIN_URL}/Users/{user_id}",
                headers={"X-Emby-Token": JELLYFIN_API_KEY},
                timeout=10.0
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        print(f"Jellyfin delete error: {e}")
    return False


async def authenticate_jellyfin(username: str, password: str) -> dict | None:
    """Authenticate to Jellyfin and return token info."""
    if not JELLYFIN_URL:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{JELLYFIN_URL}/Users/AuthenticateByName",
                headers={
                    "Content-Type": "application/json",
                    "X-Emby-Authorization": 'MediaBrowser Client="blaha.io", Device="Web", DeviceId="blaha-auto-login", Version="1.0"'
                },
                json={"Username": username, "Pw": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "access_token": data.get("AccessToken"),
                    "user_id": data.get("User", {}).get("Id"),
                    "server_id": data.get("ServerId")
                }
    except Exception as e:
        print(f"Jellyfin auth error: {e}")
    return None


@router.get("/auth-setup")
async def jellyfin_auth_setup(
    access_token: str,
    user_id: str,
    server_id: str
):
    """Serve the localStorage setup page for Jellyfin auto-login.

    This endpoint is accessed via jellyfin.{BASE_DOMAIN}/blaha-auth-setup so that
    localStorage is set on the correct domain.
    """
    from fastapi.responses import HTMLResponse

    jellyfin_base = f"https://jellyfin.{BASE_DOMAIN}"
    html = f"""<!DOCTYPE html>
<html>
<head><title>Signing into Jellyfin...</title></head>
<body style="background:#101010;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>Signing into Jellyfin...</h2>
<script>
const credentials = {{
    Servers: [{{
        Id: "{server_id}",
        Name: "Jellyfin",
        LocalAddress: "{JELLYFIN_URL}",
        ManualAddress: "{jellyfin_base}",
        AccessToken: "{access_token}",
        UserId: "{user_id}",
        DateLastAccessed: Date.now()
    }}]
}};
localStorage.setItem('jellyfin_credentials', JSON.stringify(credentials));
window.location.href = '{jellyfin_base}/web/index.html#!/home.html';
</script>
<noscript>JavaScript is required. <a href="{jellyfin_base}">Go to Jellyfin</a></noscript>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/status")
async def jellyfin_status(_: bool = Depends(verify_admin)):
    """Check Jellyfin connection status."""
    if not JELLYFIN_URL or not JELLYFIN_API_KEY:
        return {"connected": False, "error": "Not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{JELLYFIN_URL}/System/Info",
                headers={"X-Emby-Token": JELLYFIN_API_KEY},
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"connected": True, "serverName": data.get("ServerName", "Jellyfin")}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
