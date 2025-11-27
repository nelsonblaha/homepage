"""Overseerr integration for blaha.io"""
import os
import secrets
import httpx
from fastapi import APIRouter, Depends

from services.session import verify_admin

OVERSEERR_URL = os.environ.get("OVERSEERR_URL", "")
OVERSEERR_API_KEY = os.environ.get("OVERSEERR_API_KEY", "")

router = APIRouter(prefix="/api/overseerr", tags=["overseerr"])


async def create_overseerr_user(username: str) -> dict | None:
    """Create an Overseerr local user with password. Returns user info including password."""
    if not OVERSEERR_URL or not OVERSEERR_API_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            password = secrets.token_urlsafe(16)
            email = f"{username.lower().replace(' ', '')}@blaha.io"

            # Create the user
            # Permissions are bit flags: 2=REQUEST, 32=AUTO_APPROVE
            # 34 = REQUEST + AUTO_APPROVE (requests are auto-approved)
            resp = await client.post(
                f"{OVERSEERR_URL}/api/v1/user",
                headers={"X-Api-Key": OVERSEERR_API_KEY, "Content-Type": "application/json"},
                json={
                    "email": email,
                    "username": username,
                    "permissions": 34  # REQUEST + AUTO_APPROVE
                },
                timeout=10.0
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                user_id = data.get("id")

                # Set the password
                pwd_resp = await client.post(
                    f"{OVERSEERR_URL}/api/v1/user/{user_id}/settings/password",
                    headers={"X-Api-Key": OVERSEERR_API_KEY, "Content-Type": "application/json"},
                    json={"newPassword": password},
                    timeout=10.0
                )
                if pwd_resp.status_code in (200, 204):
                    return {"id": str(user_id), "username": username, "email": email, "password": password}
                else:
                    print(f"Overseerr set password failed: {pwd_resp.status_code} {pwd_resp.text}")
                    # User was created but password failed - still return info
                    return {"id": str(user_id), "username": username, "email": email, "password": ""}
            print(f"Overseerr create user failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Overseerr error: {e}")
    return None


async def delete_overseerr_user(user_id: str) -> bool:
    """Delete an Overseerr user by ID."""
    if not OVERSEERR_URL or not OVERSEERR_API_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{OVERSEERR_URL}/api/v1/user/{user_id}",
                headers={"X-Api-Key": OVERSEERR_API_KEY},
                timeout=10.0
            )
            return resp.status_code in (200, 204)
    except Exception as e:
        print(f"Overseerr delete error: {e}")
    return False


async def authenticate_overseerr(email: str, password: str) -> dict | None:
    """Authenticate to Overseerr and return session cookie."""
    if not OVERSEERR_URL:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OVERSEERR_URL}/api/v1/auth/local",
                json={"email": email, "password": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                # Get the session cookie from response
                cookies = resp.cookies
                return {
                    "success": True,
                    "cookies": dict(cookies)
                }
    except Exception as e:
        print(f"Overseerr auth error: {e}")
    return None


@router.get("/auth-setup")
async def overseerr_auth_setup(email: str, password: str):
    """Proxy login to Overseerr and set session cookie.

    This endpoint should be accessed via overseerr.blaha.io/blaha-auth-setup
    so the cookie is set on the correct domain.
    """
    from fastapi.responses import Response, RedirectResponse

    if not OVERSEERR_URL:
        return Response(content="Overseerr not configured", status_code=500)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OVERSEERR_URL}/api/v1/auth/local",
                json={"email": email, "password": password},
                timeout=10.0
            )
            if resp.status_code == 200:
                # Create redirect response and copy cookies
                redirect = RedirectResponse(url="https://overseerr.blaha.io", status_code=302)
                for cookie_name, cookie_value in resp.cookies.items():
                    redirect.set_cookie(
                        key=cookie_name,
                        value=cookie_value,
                        domain=".blaha.io",
                        httponly=True,
                        secure=True,
                        samesite="lax"
                    )
                return redirect
            else:
                return Response(content=f"Auth failed: {resp.status_code}", status_code=401)
    except Exception as e:
        return Response(content=f"Error: {e}", status_code=500)


@router.get("/status")
async def overseerr_status(_: bool = Depends(verify_admin)):
    """Check Overseerr connection status."""
    if not OVERSEERR_URL or not OVERSEERR_API_KEY:
        return {"connected": False, "error": "Not configured"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OVERSEERR_URL}/api/v1/status",
                headers={"X-Api-Key": OVERSEERR_API_KEY},
                timeout=5.0
            )
            if resp.status_code == 200:
                return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
