"""Authentication routes - admin login and service SSO"""
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Cookie, Request, Header, Form
from fastapi.responses import RedirectResponse, HTMLResponse

from database import get_db
from models import AdminLogin
from services.session import (
    create_session, validate_session, delete_session,
    SESSION_DURATION_SHORT, SESSION_DURATION_LONG
)
from integrations.ombi import authenticate_ombi, OMBI_URL
from integrations.jellyfin import authenticate_jellyfin, JELLYFIN_URL
from integrations.overseerr import OVERSEERR_URL

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "")  # e.g., ".example.com" - leave empty for localhost
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")  # e.g., "example.com"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@localhost")

router = APIRouter(tags=["auth"])


# =============================================================================
# ADMIN AUTH
# =============================================================================

@router.post("/api/admin/login")
async def admin_login(login: AdminLogin, response: Response, request: Request):
    if login.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    user_agent = request.headers.get("user-agent", "")
    remember = getattr(login, "remember", False)
    session_token, expires_at = await create_session("admin", remember=remember, user_agent=user_agent)

    duration = SESSION_DURATION_LONG if remember else SESSION_DURATION_SHORT
    cookie_kwargs = {
        "key": "admin_token",
        "value": session_token,
        "httponly": True,
        "samesite": "lax",
        "max_age": int(duration.total_seconds()),
    }
    if COOKIE_DOMAIN and COOKIE_DOMAIN != "localhost":
        cookie_kwargs["domain"] = COOKIE_DOMAIN
        cookie_kwargs["secure"] = True
    response.set_cookie(**cookie_kwargs)
    return {"status": "ok"}


@router.get("/api/admin/verify")
async def verify_admin_session(admin_token: Optional[str] = Cookie(default=None)):
    session = await validate_session(admin_token)
    if session and session["type"] == "admin":
        return {"authenticated": True, "type": "admin"}
    return {"authenticated": False}


@router.post("/api/admin/logout")
async def admin_logout(response: Response, admin_token: Optional[str] = Cookie(default=None)):
    if admin_token:
        await delete_session(admin_token)
    if COOKIE_DOMAIN and COOKIE_DOMAIN != "localhost":
        response.delete_cookie("admin_token", domain=COOKIE_DOMAIN)
    else:
        response.delete_cookie("admin_token")
    return {"status": "ok"}


# =============================================================================
# FORWARD AUTH (for nginx auth_request)
# =============================================================================

@router.get("/api/auth/verify")
async def forward_auth_verify(
    request: Request,
    admin_token: Optional[str] = Cookie(default=None),
    x_original_uri: Optional[str] = Header(default=None, alias="X-Original-URI"),
    x_forwarded_host: Optional[str] = Header(default=None, alias="X-Forwarded-Host")
):
    """Verify authentication for nginx forward auth (auth_request)."""
    response_headers = {}

    # Check admin session first
    session = await validate_session(admin_token)
    if session and session["type"] == "admin":
        response_headers["X-Remote-User"] = "admin"
        response_headers["X-Remote-Email"] = ADMIN_EMAIL
        return Response(status_code=200, headers=response_headers)

    # Check friend session
    if session and session["type"] == "friend":
        async with await get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = await db.execute(
                "SELECT name FROM friends WHERE id = ?", (session["user_id"],)
            )
            friend = await cursor.fetchone()

            if friend:
                # Check if friend has access to this service (by subdomain)
                subdomain = x_forwarded_host.split(".")[0] if x_forwarded_host else ""
                cursor = await db.execute(
                    """SELECT s.name FROM services s
                       JOIN friend_services fs ON s.id = fs.service_id
                       WHERE fs.friend_id = ? AND s.subdomain = ?""",
                    (session["user_id"], subdomain)
                )
                has_access = await cursor.fetchone()

                if has_access:
                    response_headers["X-Remote-User"] = friend["name"]
                    response_headers["X-Remote-Email"] = f"{friend['name'].lower().replace(' ', '')}@friends.{BASE_DOMAIN}"
                    return Response(status_code=200, headers=response_headers)
                else:
                    return Response(status_code=403)

    return Response(status_code=401)


@router.post("/api/auth/friend-session")
async def create_friend_session(response: Response, request: Request, token: str = Form(...)):
    """Create a session for a friend using their token."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT id, name FROM friends WHERE token = ?", (token,))
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid token")

        user_agent = request.headers.get("user-agent", "")
        session_token, expires_at = await create_session(
            "friend", user_id=friend["id"], remember=True, user_agent=user_agent
        )

        cookie_kwargs = {
            "key": "admin_token",
            "value": session_token,
            "httponly": True,
            "samesite": "lax",
            "max_age": int(SESSION_DURATION_LONG.total_seconds()),
        }
        if COOKIE_DOMAIN and COOKIE_DOMAIN != "localhost":
            cookie_kwargs["domain"] = COOKIE_DOMAIN
            cookie_kwargs["secure"] = True
        response.set_cookie(**cookie_kwargs)
        return {"status": "ok", "name": friend["name"]}


# =============================================================================
# UNIFIED AUTH REDIRECT (for friends accessing services)
# =============================================================================

async def _auth_basic(subdomain: str) -> Response:
    """Generate preauth URL redirect for basic auth services."""
    if not BASIC_AUTH_PASS or not BASIC_AUTH_USER:
        raise HTTPException(status_code=500, detail="Basic auth not configured")
    from urllib.parse import quote
    user = quote(BASIC_AUTH_USER, safe='')
    passwd = quote(BASIC_AUTH_PASS, safe='')
    preauth_url = f"https://{user}:{passwd}@{subdomain}.{BASE_DOMAIN}/"
    return RedirectResponse(url=preauth_url, status_code=302)


async def _auth_ombi(friend: dict) -> Response:
    """Authenticate to Ombi and redirect to setup page on ombi subdomain.

    The localStorage must be set on the ombi subdomain, so we redirect
    to ombi.{BASE_DOMAIN}/blaha-auth-setup which proxies to our auth-setup endpoint.
    """
    if not OMBI_URL:
        raise HTTPException(status_code=400, detail="Ombi not configured")

    if not friend.get("ombi_user_id") or not friend.get("ombi_password"):
        raise HTTPException(status_code=403, detail="No Ombi account configured")

    access_token = await authenticate_ombi(friend["name"], friend["ombi_password"])
    if not access_token:
        raise HTTPException(status_code=401, detail="Ombi authentication failed")

    from urllib.parse import urlencode
    params = urlencode({"access_token": access_token})
    # Redirect to ombi subdomain so localStorage is set on correct domain
    return RedirectResponse(
        url=f"https://ombi.{BASE_DOMAIN}/blaha-auth-setup?{params}",
        status_code=302
    )


async def _auth_jellyfin(friend: dict) -> Response:
    """Authenticate to Jellyfin and redirect to setup page on jellyfin subdomain.

    The localStorage must be set on the jellyfin subdomain, so we redirect
    to jellyfin.{BASE_DOMAIN}/blaha-auth-setup which proxies to our auth-setup endpoint.
    """
    if not JELLYFIN_URL:
        raise HTTPException(status_code=400, detail="Jellyfin not configured")

    if not friend.get("jellyfin_user_id") or not friend.get("jellyfin_password"):
        raise HTTPException(status_code=403, detail="No Jellyfin account configured")

    auth_data = await authenticate_jellyfin(friend["name"], friend["jellyfin_password"])
    if not auth_data:
        raise HTTPException(status_code=401, detail="Jellyfin authentication failed")

    from urllib.parse import urlencode
    params = urlencode({
        "access_token": auth_data["access_token"],
        "user_id": auth_data["user_id"],
        "server_id": auth_data["server_id"]
    })
    # Redirect to jellyfin subdomain so localStorage is set on correct domain
    return RedirectResponse(
        url=f"https://jellyfin.{BASE_DOMAIN}/blaha-auth-setup?{params}",
        status_code=302
    )


async def _auth_overseerr(friend: dict) -> Response:
    """Authenticate to Overseerr and redirect to setup page on overseerr subdomain.

    Overseerr uses session cookies, so we redirect to overseerr.{BASE_DOMAIN}/blaha-auth-setup
    which proxies to our auth-setup endpoint that handles login and sets cookies.
    """
    if not OVERSEERR_URL:
        raise HTTPException(status_code=400, detail="Overseerr not configured")

    if not friend.get("overseerr_user_id") or not friend.get("overseerr_password"):
        raise HTTPException(status_code=403, detail="No Overseerr account configured")

    from urllib.parse import urlencode
    # Email format matches what we create in overseerr.py
    email = f"{friend['name'].lower().replace(' ', '')}@{BASE_DOMAIN}"
    params = urlencode({
        "email": email,
        "password": friend["overseerr_password"]
    })
    # Redirect to overseerr subdomain so cookies are set on correct domain
    return RedirectResponse(
        url=f"https://overseerr.{BASE_DOMAIN}/blaha-auth-setup?{params}",
        status_code=302
    )


@router.get("/auth/{subdomain}")
async def unified_auth_redirect(subdomain: str, admin_token: Optional[str] = Cookie(default=None)):
    """Unified auth endpoint for friends accessing services."""
    session = await validate_session(admin_token)
    if not session or session["type"] != "friend":
        return RedirectResponse(url="/?auth=required", status_code=302)

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (subdomain,)
        )
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        cursor = await db.execute(
            "SELECT 1 FROM friend_services WHERE friend_id = ? AND service_id = ?",
            (session["user_id"], service["id"])
        )
        has_access = await cursor.fetchone()

        if not has_access:
            return RedirectResponse(
                url=f"/?error=no_access&service={subdomain}",
                status_code=302
            )

        cursor = await db.execute(
            "SELECT * FROM friends WHERE id = ?", (session["user_id"],)
        )
        friend = await cursor.fetchone()

        auth_type = service.get("auth_type", "none")

        if auth_type == "basic":
            return await _auth_basic(subdomain)
        elif auth_type == "jellyfin":
            return await _auth_jellyfin(friend)
        elif auth_type == "ombi":
            return await _auth_ombi(friend)
        elif auth_type == "overseerr":
            return await _auth_overseerr(friend)
        else:
            return RedirectResponse(url=f"https://{subdomain}.{BASE_DOMAIN}/", status_code=302)


# Legacy endpoint for backwards compatibility
@router.get("/auth/jellyfin", include_in_schema=False)
async def jellyfin_auto_login_legacy(admin_token: Optional[str] = Cookie(default=None)):
    """Legacy endpoint - redirects to unified auth."""
    return await unified_auth_redirect("jellyfin", admin_token)
