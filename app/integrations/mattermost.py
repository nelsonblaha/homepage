"""Mattermost integration - auto-login via session cookie proxy"""
import os
import secrets
import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response

MATTERMOST_URL = os.environ.get("MATTERMOST_URL", "")
MATTERMOST_TOKEN = os.environ.get("MATTERMOST_TOKEN", "")
MATTERMOST_TEAM_ID = os.environ.get("MATTERMOST_TEAM_ID", "")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "")  # e.g., ".example.com"

router = APIRouter(prefix="/api/mattermost", tags=["mattermost"])


async def create_mattermost_user(username: str) -> dict | None:
    """Create a Mattermost user. Returns user info including password."""
    if not MATTERMOST_URL or not MATTERMOST_TOKEN:
        return None
    try:
        async with httpx.AsyncClient() as client:
            password = secrets.token_urlsafe(16)
            email = f"{username.lower().replace(' ', '')}@{BASE_DOMAIN}"
            # Mattermost username must be lowercase, alphanumeric + underscores
            mm_username = username.lower().replace(' ', '_')

            # Create the user
            resp = await client.post(
                f"{MATTERMOST_URL}/api/v4/users",
                headers={"Authorization": f"Bearer {MATTERMOST_TOKEN}", "Content-Type": "application/json"},
                json={
                    "email": email,
                    "username": mm_username,
                    "password": password,
                    "nickname": username
                },
                timeout=10.0
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                user_id = data.get("id")

                # Add user to team
                team_resp = await client.post(
                    f"{MATTERMOST_URL}/api/v4/teams/{MATTERMOST_TEAM_ID}/members",
                    headers={"Authorization": f"Bearer {MATTERMOST_TOKEN}", "Content-Type": "application/json"},
                    json={"team_id": MATTERMOST_TEAM_ID, "user_id": user_id},
                    timeout=10.0
                )
                if team_resp.status_code not in (200, 201):
                    print(f"Mattermost add to team failed: {team_resp.status_code} {team_resp.text}")

                return {"id": user_id, "username": mm_username, "email": email, "password": password}
            print(f"Mattermost create user failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Mattermost error: {e}")
    return None


async def delete_mattermost_user(user_id: str) -> bool:
    """Delete a Mattermost user by ID."""
    if not MATTERMOST_URL or not MATTERMOST_TOKEN:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{MATTERMOST_URL}/api/v4/users/{user_id}",
                headers={"Authorization": f"Bearer {MATTERMOST_TOKEN}"},
                timeout=10.0
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        print(f"Mattermost delete error: {e}")
    return False


async def authenticate_mattermost(email: str, password: str) -> dict | None:
    """Authenticate to Mattermost and return session token."""
    if not MATTERMOST_URL:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MATTERMOST_URL}/api/v4/users/login",
                json={"login_id": email, "password": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                token = resp.headers.get("Token")
                return {"success": True, "token": token}
    except Exception as e:
        print(f"Mattermost auth error: {e}")
    return None


@router.get("/auth-setup")
async def mattermost_auth_setup(email: str, password: str):
    """Log into Mattermost and redirect with session cookie."""
    if not MATTERMOST_URL:
        return Response(content="Mattermost not configured", status_code=500)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MATTERMOST_URL}/api/v4/users/login",
                json={"login_id": email, "password": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                token = resp.headers.get("Token")
                # Create redirect response and set the MMAUTHTOKEN cookie
                redirect = RedirectResponse(url=f"https://chat.{BASE_DOMAIN}", status_code=302)
                cookie_kwargs = {
                    "key": "MMAUTHTOKEN",
                    "value": token,
                    "httponly": True,
                    "samesite": "lax"
                }
                # Only set domain and secure for non-localhost
                if COOKIE_DOMAIN:
                    cookie_kwargs["domain"] = COOKIE_DOMAIN
                    cookie_kwargs["secure"] = True
                redirect.set_cookie(**cookie_kwargs)
                return redirect
            else:
                return Response(content=f"Auth failed: {resp.status_code}", status_code=401)
    except Exception as e:
        return Response(content=f"Error: {e}", status_code=500)


@router.get("/status")
async def mattermost_status():
    """Check Mattermost connection status."""
    if not MATTERMOST_URL or not MATTERMOST_TOKEN:
        return {"connected": False, "error": "Not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MATTERMOST_URL}/api/v4/system/ping",
                headers={"Authorization": f"Bearer {MATTERMOST_TOKEN}"},
                timeout=5.0
            )
            if resp.status_code == 200:
                return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
