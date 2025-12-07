"""Authentication routes - admin login and service SSO"""
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Cookie, Request, Header, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse

from database import get_db
from models import AdminLogin
from services.session import (
    create_session, validate_session, delete_session, verify_admin,
    SESSION_DURATION_SHORT, SESSION_DURATION_LONG
)
from integrations.ombi import authenticate_ombi, OMBI_URL
from integrations.jellyfin import authenticate_jellyfin, JELLYFIN_URL
from integrations.overseerr import OVERSEERR_URL
from services.activity import log_activity, ACTION_SERVICE_CLICK

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")
COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "")  # e.g., ".example.com" - leave empty for localhost
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")  # e.g., "example.com"
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Ben")  # Display name for admin in services
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
        response_headers["X-Remote-User"] = ADMIN_NAME
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
                    """SELECT s.id, s.name FROM services s
                       JOIN friend_services fs ON s.id = fs.service_id
                       WHERE fs.friend_id = ? AND s.subdomain = ?""",
                    (session["user_id"], subdomain)
                )
                service = await cursor.fetchone()

                if service:
                    # Log service access (forward auth is called on each request,
                    # so we only log the first access per path to avoid spam)
                    path = x_original_uri or "/"
                    if path == "/" or path.endswith("/"):
                        await log_activity(
                            db, ACTION_SERVICE_CLICK,
                            friend_id=session["user_id"],
                            service_id=service["id"],
                            details=f"nginx:{subdomain}"
                        )
                        await db.commit()

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


async def _auth_mattermost(friend: dict) -> Response:
    """Authenticate to Mattermost and redirect to setup page on chat subdomain.

    Mattermost uses session cookies, so we redirect to chat.{BASE_DOMAIN}/api/mattermost/auth-setup
    which handles login and sets cookies.
    """
    from integrations.mattermost import mattermost_integration

    if not mattermost_integration.service_url:
        raise HTTPException(status_code=400, detail="Mattermost not configured")

    if not friend.get("mattermost_user_id") or not friend.get("mattermost_password"):
        raise HTTPException(status_code=403, detail="No Mattermost account configured")

    from urllib.parse import urlencode
    # Email format matches what we create in mattermost.py
    email = f"{friend['name'].lower().replace(' ', '')}@{BASE_DOMAIN}"
    params = urlencode({
        "email": email,
        "password": friend["mattermost_password"]
    })
    # Redirect to chat subdomain so cookies are set on correct domain
    return RedirectResponse(
        url=f"https://chat.{BASE_DOMAIN}/api/mattermost/auth-setup?{params}",
        status_code=302
    )


async def _auth_nextcloud(friend: dict, subdomain: str) -> Response:
    """Display Nextcloud credentials for manual login.

    Nextcloud uses credential-display auth - we show the username/password
    for the user to copy and paste into the login form.
    """
    if not friend.get("nextcloud_user_id") or not friend.get("nextcloud_password"):
        raise HTTPException(status_code=403, detail="No Nextcloud account configured")

    # Display credentials page
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Nextcloud Login - {friend['name']}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                max-width: 400px;
                width: 90%;
            }}
            h1 {{
                margin: 0 0 0.5rem 0;
                color: #333;
                font-size: 1.5rem;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 1.5rem;
                font-size: 0.9rem;
            }}
            .credential {{
                margin: 1rem 0;
            }}
            label {{
                display: block;
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: #555;
                font-size: 0.9rem;
            }}
            .value {{
                background: #f5f5f5;
                padding: 0.75rem;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                word-break: break-all;
                position: relative;
            }}
            .copy-btn {{
                background: #667eea;
                color: white;
                border: none;
                padding: 0.6rem 1.2rem;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.9rem;
                margin-top: 0.5rem;
                width: 100%;
                font-weight: 600;
            }}
            .copy-btn:hover {{
                background: #5568d3;
            }}
            .continue-btn {{
                background: #10b981;
                color: white;
                text-decoration: none;
                display: block;
                text-align: center;
                padding: 0.75rem;
                border-radius: 6px;
                margin-top: 1.5rem;
                font-weight: 600;
            }}
            .continue-btn:hover {{
                background: #059669;
            }}
            .instructions {{
                background: #fef3c7;
                padding: 1rem;
                border-radius: 6px;
                margin-top: 1.5rem;
                font-size: 0.85rem;
                color: #92400e;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Nextcloud Access</h1>
            <div class="subtitle">Hi {friend['name']}! Use these credentials to log in:</div>

            <div class="credential">
                <label>Username</label>
                <div class="value" id="username">{friend['nextcloud_user_id']}</div>
                <button class="copy-btn" onclick="copy('username')">Copy Username</button>
            </div>

            <div class="credential">
                <label>Password</label>
                <div class="value" id="password">{friend['nextcloud_password']}</div>
                <button class="copy-btn" onclick="copy('password')">Copy Password</button>
            </div>

            <a href="https://{subdomain}.{BASE_DOMAIN}/" class="continue-btn">Continue to Nextcloud →</a>

            <div class="instructions">
                <strong>Instructions:</strong><br>
                1. Copy your username and password<br>
                2. Click "Continue to Nextcloud"<br>
                3. Paste your credentials into the login form
            </div>
        </div>
        <script>
            function copy(id) {{
                const text = document.getElementById(id).textContent;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = event.target;
                    const original = btn.textContent;
                    btn.textContent = '✓ Copied!';
                    btn.style.background = '#10b981';
                    setTimeout(() => {{
                        btn.textContent = original;
                        btn.style.background = '#667eea';
                    }}, 2000);
                }});
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


async def _auth_basic_credentials(friend: dict, subdomain: str, service_name: str, username: str, password: str, try_auto: bool = True) -> Response:
    """Display HTTP Basic Auth credentials with auto-inject attempt.

    For services protected by HTTP basic auth (nginx level), we:
    1. Try to auto-inject credentials via URL (if try_auto=True)
    2. Fall back to displaying credentials for manual entry

    Args:
        friend: Friend dict with id and name
        subdomain: Service subdomain (e.g., "sonarr")
        service_name: Display name of service
        username: Basic auth username for this friend+service
        password: Basic auth password for this friend+service
        try_auto: Whether to attempt auto-inject (default True)
    """
    if not username or not password:
        raise HTTPException(status_code=500, detail="Credentials not provisioned for this service")

    # If try_auto, show auto-inject page that attempts redirect with credentials
    if try_auto:
        from urllib.parse import quote
        user_enc = quote(username, safe='')
        pass_enc = quote(password, safe='')
        preauth_url = f"https://{user_enc}:{pass_enc}@{subdomain}.{BASE_DOMAIN}/"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{service_name} - Auto Login</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 2rem;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    max-width: 400px;
                    width: 90%;
                    text-align: center;
                }}
                h1 {{
                    margin: 0 0 1rem 0;
                    color: #333;
                    font-size: 1.5rem;
                }}
                .spinner {{
                    border: 3px solid #f3f3f3;
                    border-top: 3px solid #667eea;
                    border-radius: 50%;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 1rem auto;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
                .fallback {{
                    display: none;
                    margin-top: 1.5rem;
                }}
                .show-creds-btn {{
                    background: #667eea;
                    color: white;
                    border: none;
                    padding: 0.75rem 1.5rem;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 1rem;
                    font-weight: 600;
                    margin-top: 1rem;
                }}
                .show-creds-btn:hover {{
                    background: #5568d3;
                }}
                .credentials {{
                    display: none;
                    text-align: left;
                    margin-top: 1.5rem;
                }}
                .credential {{
                    margin: 1rem 0;
                }}
                label {{
                    display: block;
                    font-weight: 600;
                    margin-bottom: 0.5rem;
                    color: #555;
                    font-size: 0.9rem;
                }}
                .value {{
                    background: #f5f5f5;
                    padding: 0.75rem;
                    border-radius: 6px;
                    font-family: 'Courier New', monospace;
                    word-break: break-all;
                }}
                .copy-btn {{
                    background: #667eea;
                    color: white;
                    border: none;
                    padding: 0.6rem 1.2rem;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 0.9rem;
                    margin-top: 0.5rem;
                    width: 100%;
                    font-weight: 600;
                }}
                .copy-btn:hover {{
                    background: #5568d3;
                }}
                .continue-btn {{
                    background: #10b981;
                    color: white;
                    text-decoration: none;
                    display: block;
                    text-align: center;
                    padding: 0.75rem;
                    border-radius: 6px;
                    margin-top: 1rem;
                    font-weight: 600;
                }}
                .continue-btn:hover {{
                    background: #059669;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Logging you into {service_name}...</h1>
                <div class="spinner"></div>
                <p style="color: #666; margin-top: 1rem;">Redirecting in <span id="countdown">3</span> seconds...</p>

                <div class="fallback" id="fallback">
                    <p style="color: #666;">If you're not redirected automatically:</p>
                    <button class="show-creds-btn" onclick="showCredentials()">Show My Credentials</button>

                    <div class="credentials" id="credentials">
                        <div class="credential">
                            <label>Username</label>
                            <div class="value" id="username">{username}</div>
                            <button class="copy-btn" onclick="copy('username')">Copy Username</button>
                        </div>

                        <div class="credential">
                            <label>Password</label>
                            <div class="value" id="password">{password}</div>
                            <button class="copy-btn" onclick="copy('password')">Copy Password</button>
                        </div>

                        <a href="https://{subdomain}.{BASE_DOMAIN}/" class="continue-btn">Continue to {service_name} →</a>
                    </div>
                </div>
            </div>
            <script>
                let countdown = 3;
                const countdownEl = document.getElementById('countdown');
                const fallbackEl = document.getElementById('fallback');

                // Countdown timer
                const timer = setInterval(() => {{
                    countdown--;
                    countdownEl.textContent = countdown;
                    if (countdown <= 0) {{
                        clearInterval(timer);
                        window.location.href = '{preauth_url}';
                    }}
                }}, 1000);

                // Show fallback after 5 seconds
                setTimeout(() => {{
                    fallbackEl.style.display = 'block';
                }}, 5000);

                function showCredentials() {{
                    document.getElementById('credentials').style.display = 'block';
                    event.target.style.display = 'none';
                }}

                function copy(id) {{
                    const text = document.getElementById(id).textContent;
                    navigator.clipboard.writeText(text).then(() => {{
                        const btn = event.target;
                        const original = btn.textContent;
                        btn.textContent = '✓ Copied!';
                        btn.style.background = '#10b981';
                        setTimeout(() => {{
                            btn.textContent = original;
                            btn.style.background = '#667eea';
                        }}, 2000);
                    }});
                }}
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

    # Fallback: just show credentials modal
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{service_name} Login - {friend['name']}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 2rem;
                border-radius: 12px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                max-width: 400px;
                width: 90%;
            }}
            h1 {{
                margin: 0 0 0.5rem 0;
                color: #333;
                font-size: 1.5rem;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 1.5rem;
                font-size: 0.9rem;
            }}
            .credential {{
                margin: 1rem 0;
            }}
            label {{
                display: block;
                font-weight: 600;
                margin-bottom: 0.5rem;
                color: #555;
                font-size: 0.9rem;
            }}
            .value {{
                background: #f5f5f5;
                padding: 0.75rem;
                border-radius: 6px;
                font-family: 'Courier New', monospace;
                word-break: break-all;
                position: relative;
            }}
            .copy-btn {{
                background: #667eea;
                color: white;
                border: none;
                padding: 0.6rem 1.2rem;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.9rem;
                margin-top: 0.5rem;
                width: 100%;
                font-weight: 600;
            }}
            .copy-btn:hover {{
                background: #5568d3;
            }}
            .continue-btn {{
                background: #10b981;
                color: white;
                text-decoration: none;
                display: block;
                text-align: center;
                padding: 0.75rem;
                border-radius: 6px;
                margin-top: 1.5rem;
                font-weight: 600;
            }}
            .continue-btn:hover {{
                background: #059669;
            }}
            .instructions {{
                background: #fef3c7;
                padding: 1rem;
                border-radius: 6px;
                margin-top: 1.5rem;
                font-size: 0.85rem;
                color: #92400e;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{service_name} Access</h1>
            <div class="subtitle">Hi {friend['name']}! Use these credentials to log in:</div>

            <div class="credential">
                <label>Username</label>
                <div class="value" id="username">{username}</div>
                <button class="copy-btn" onclick="copy('username')">Copy Username</button>
            </div>

            <div class="credential">
                <label>Password</label>
                <div class="value" id="password">{password}</div>
                <button class="copy-btn" onclick="copy('password')">Copy Password</button>
            </div>

            <a href="https://{subdomain}.{BASE_DOMAIN}/" class="continue-btn">Continue to {service_name} →</a>

            <div class="instructions">
                <strong>Instructions:</strong><br>
                1. Copy the username and password<br>
                2. Click "Continue to {service_name}"<br>
                3. Enter the credentials when prompted by your browser
            </div>
        </div>
        <script>
            function copy(id) {{
                const text = document.getElementById(id).textContent;
                navigator.clipboard.writeText(text).then(() => {{
                    const btn = event.target;
                    const original = btn.textContent;
                    btn.textContent = '✓ Copied!';
                    btn.style.background = '#10b981';
                    setTimeout(() => {{
                        btn.textContent = original;
                        btn.style.background = '#667eea';
                    }}, 2000);
                }});
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/auth/{subdomain}")
async def unified_auth_redirect(subdomain: str, admin_token: Optional[str] = Cookie(default=None)):
    """Unified auth endpoint for friends and admin accessing services."""
    session = await validate_session(admin_token)
    if not session:
        return RedirectResponse(url="/?auth=required", status_code=302)

    is_admin = (session["type"] == "admin")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (subdomain,)
        )
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # For admin, skip access check and create pseudo-friend object
        if is_admin:
            friend = {
                "id": 0,
                "name": ADMIN_NAME,
                "token": "admin"
            }
        else:
            # For friend users, check access
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
        service_name = service.get("name", subdomain.title())

        if auth_type == "basic":
            # For basic auth services, retrieve friend's personal credentials
            if is_admin:
                # Admin uses the shared admin credentials
                username = BASIC_AUTH_USER
                password = BASIC_AUTH_PASS
            else:
                # Friend uses their per-service credentials
                cursor = await db.execute(
                    """SELECT fs.basic_auth_username, fs.basic_auth_password
                       FROM friend_services fs
                       WHERE fs.friend_id = ? AND fs.service_id = ?""",
                    (friend["id"], service["id"])
                )
                creds = await cursor.fetchone()

                if not creds or not creds["basic_auth_username"]:
                    raise HTTPException(
                        status_code=403,
                        detail="Credentials not provisioned for this service. Contact admin."
                    )

                username = creds["basic_auth_username"]
                password = creds["basic_auth_password"]

            # Show credentials page with auto-inject attempt
            return await _auth_basic_credentials(friend, subdomain, service_name, username, password)
        elif auth_type == "jellyfin":
            return await _auth_jellyfin(friend)
        elif auth_type == "ombi":
            return await _auth_ombi(friend)
        elif auth_type == "overseerr":
            return await _auth_overseerr(friend)
        elif auth_type == "nextcloud":
            return await _auth_nextcloud(friend, subdomain)
        elif auth_type == "mattermost":
            return await _auth_mattermost(friend)
        elif auth_type == "none" or auth_type == "forward-auth":
            # Services with no custom auth - just redirect
            return RedirectResponse(url=f"https://{subdomain}.{BASE_DOMAIN}/", status_code=302)
        else:
            # Unknown auth type - redirect anyway
            return RedirectResponse(url=f"https://{subdomain}.{BASE_DOMAIN}/", status_code=302)


@router.get("/api/admin/credentials/{subdomain}")
async def get_admin_credentials(subdomain: str, _: bool = Depends(verify_admin)):
    """Get credentials for services requiring basic auth (for admin modal)."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            "SELECT auth_type FROM services WHERE subdomain = ?", (subdomain,)
        )
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        auth_type = service.get("auth_type", "none")

        if auth_type == "basic":
            # Return HTTP basic auth credentials
            return {
                "username": BASIC_AUTH_USER,
                "password": BASIC_AUTH_PASS
            }
        else:
            raise HTTPException(status_code=400, detail="Service does not use basic auth")


# Legacy endpoint for backwards compatibility
@router.get("/auth/jellyfin", include_in_schema=False)
async def jellyfin_auto_login_legacy(admin_token: Optional[str] = Cookie(default=None)):
    """Legacy endpoint - redirects to unified auth."""
    return await unified_auth_redirect("jellyfin", admin_token)
