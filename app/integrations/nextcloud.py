"""Nextcloud integration for blaha.io"""
import os
import secrets
import httpx
from fastapi import APIRouter, Depends

from services.session import verify_admin

NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "")
NEXTCLOUD_ADMIN_USER = os.environ.get("NEXTCLOUD_ADMIN_USER", "admin")
NEXTCLOUD_ADMIN_PASS = os.environ.get("NEXTCLOUD_ADMIN_PASS", "")

router = APIRouter(prefix="/api/nextcloud", tags=["nextcloud"])


async def create_nextcloud_user(username: str) -> dict | None:
    """Create a Nextcloud user with a password. Returns user info or None on failure."""
    if not NEXTCLOUD_URL or not NEXTCLOUD_ADMIN_PASS:
        return None
    try:
        password = secrets.token_urlsafe(16)
        async with httpx.AsyncClient() as client:
            # OCS API for user creation
            resp = await client.post(
                f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/users",
                auth=(NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASS),
                headers={
                    "OCS-APIRequest": "true",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                data={
                    "userid": username,
                    "password": password
                },
                timeout=15.0
            )
            # OCS returns 100 for success in the meta status
            if resp.status_code == 200:
                # Check if the OCS status indicates success
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                status_code = root.find(".//statuscode")
                if status_code is not None and status_code.text == "100":
                    return {"id": username, "username": username, "password": password}
                else:
                    message = root.find(".//message")
                    msg_text = message.text if message is not None else "Unknown error"
                    print(f"Nextcloud create user failed: {msg_text}")
            else:
                print(f"Nextcloud create user failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Nextcloud error: {e}")
    return None


async def delete_nextcloud_user(user_id: str) -> bool:
    """Delete a Nextcloud user by username/ID."""
    if not NEXTCLOUD_URL or not NEXTCLOUD_ADMIN_PASS:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/users/{user_id}",
                auth=(NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASS),
                headers={"OCS-APIRequest": "true"},
                timeout=10.0
            )
            if resp.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp.text)
                status_code = root.find(".//statuscode")
                return status_code is not None and status_code.text == "100"
    except Exception as e:
        print(f"Nextcloud delete error: {e}")
    return False


async def authenticate_nextcloud(username: str, password: str) -> dict | None:
    """Authenticate to Nextcloud and return login flow token."""
    if not NEXTCLOUD_URL:
        return None
    try:
        async with httpx.AsyncClient() as client:
            # Verify credentials work by hitting capabilities endpoint
            resp = await client.get(
                f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/capabilities",
                auth=(username, password),
                headers={"OCS-APIRequest": "true"},
                timeout=10.0
            )
            if resp.status_code == 200:
                # Credentials are valid - for Nextcloud we'll do direct login
                # since it uses session-based auth primarily
                return {
                    "username": username,
                    "password": password,
                    "valid": True
                }
    except Exception as e:
        print(f"Nextcloud auth error: {e}")
    return None


@router.get("/auth-setup")
async def nextcloud_auth_setup(username: str, password: str):
    """Serve a page that auto-logs into Nextcloud.

    Nextcloud uses session-based auth, so we create a form that auto-submits
    to the login endpoint.
    """
    from fastapi.responses import HTMLResponse
    from urllib.parse import quote

    html = f"""<!DOCTYPE html>
<html>
<head><title>Signing into Nextcloud...</title></head>
<body style="background:#0082c9;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>Signing into Nextcloud...</h2>
<form id="loginForm" method="POST" action="https://nextcloud.blaha.io/login">
    <input type="hidden" name="user" value="{quote(username)}" />
    <input type="hidden" name="password" value="{quote(password)}" />
    <input type="hidden" name="requesttoken" value="" />
</form>
<script>
// For Nextcloud, we need to first get a request token, then submit
// Simpler approach: just redirect to the login page - user has credentials
// Actually, just show them their credentials and link them through
document.body.innerHTML = `
<div style="text-align:center;padding:20px">
<h2>Nextcloud Login</h2>
<p>Your credentials:</p>
<p><strong>Username:</strong> {username}</p>
<p><strong>Password:</strong> <code style="background:#fff;color:#333;padding:4px 8px;border-radius:4px">{password}</code></p>
<p style="margin-top:20px"><a href="https://nextcloud.blaha.io" style="color:#fff;font-size:1.2em">Go to Nextcloud →</a></p>
</div>
`;
</script>
<noscript>
<p>Your credentials:</p>
<p>Username: {username}</p>
<p>Password: {password}</p>
<p><a href="https://nextcloud.blaha.io" style="color:#fff">Go to Nextcloud</a></p>
</noscript>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/status")
async def nextcloud_status(_: bool = Depends(verify_admin)):
    """Check Nextcloud connection status."""
    if not NEXTCLOUD_URL or not NEXTCLOUD_ADMIN_PASS:
        return {"connected": False, "error": "Not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{NEXTCLOUD_URL}/ocs/v1.php/cloud/capabilities",
                auth=(NEXTCLOUD_ADMIN_USER, NEXTCLOUD_ADMIN_PASS),
                headers={"OCS-APIRequest": "true"},
                timeout=5.0
            )
            if resp.status_code == 200:
                return {"connected": True, "serverName": "Nextcloud"}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
