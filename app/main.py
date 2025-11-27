import os
import uuid
import secrets
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from typing import Optional

from database import init_db, get_db, DB_PATH
from models import (
    Service, ServiceCreate,
    Friend, FriendCreate, FriendUpdate, FriendView,
    AdminLogin, TokenResponse
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "ben")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
PLEX_URL = os.environ.get("PLEX_URL", "http://localhost:32400")
OMBI_URL = os.environ.get("OMBI_URL", "")
OMBI_API_KEY = os.environ.get("OMBI_API_KEY", "")
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

# Store active admin sessions (in production, use Redis or similar)
admin_sessions: set[str] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="blaha.io", lifespan=lifespan)

# Dependency to verify admin session
async def verify_admin(admin_token: Optional[str] = Cookie(default=None)):
    if not admin_token or admin_token not in admin_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True

# =============================================================================
# ADMIN AUTH
# =============================================================================

@app.post("/api/admin/login")
async def admin_login(login: AdminLogin, response: Response):
    if login.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    session_token = secrets.token_hex(32)
    admin_sessions.add(session_token)
    response.set_cookie(
        key="admin_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400  # 24 hours
    )
    return {"status": "ok"}

@app.get("/api/admin/verify")
async def verify_admin_session(admin_token: Optional[str] = Cookie(default=None)):
    if admin_token and admin_token in admin_sessions:
        return {"authenticated": True}
    return {"authenticated": False}

@app.post("/api/admin/logout")
async def admin_logout(response: Response, admin_token: Optional[str] = Cookie(default=None)):
    if admin_token:
        admin_sessions.discard(admin_token)
    response.delete_cookie("admin_token")
    return {"status": "ok"}

# =============================================================================
# SERVICES (Admin only)
# =============================================================================

@app.get("/api/services", response_model=list[Service])
async def list_services(_: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            "SELECT * FROM services ORDER BY display_order, name"
        )
        rows = await cursor.fetchall()
        return rows

@app.post("/api/services", response_model=Service)
async def create_service(service: ServiceCreate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO services (name, url, icon, description, display_order, subdomain, stack, is_default)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0)
        )
        await db.commit()
        return Service(id=cursor.lastrowid, **service.model_dump())

@app.put("/api/services/{service_id}", response_model=Service)
async def update_service(service_id: int, service: ServiceCreate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        await db.execute(
            """UPDATE services SET name=?, url=?, icon=?, description=?, display_order=?,
               subdomain=?, stack=?, is_default=? WHERE id=?""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0, service_id)
        )
        await db.commit()
        return Service(id=service_id, **service.model_dump())

@app.delete("/api/services/{service_id}")
async def delete_service(service_id: int, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        await db.execute("DELETE FROM friend_services WHERE service_id = ?", (service_id,))
        await db.execute("DELETE FROM services WHERE id = ?", (service_id,))
        await db.commit()
        return {"status": "ok"}

@app.get("/api/services/{service_id}/preauth-url")
async def get_preauth_url(service_id: int, _: bool = Depends(verify_admin)):
    """Generate a pre-authenticated URL for a service with embedded basic auth credentials."""
    if not BASIC_AUTH_PASS:
        raise HTTPException(status_code=400, detail="Basic auth not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        if not service.get("subdomain"):
            raise HTTPException(status_code=400, detail="Service has no subdomain configured")

        # Build pre-auth URL with basic auth credentials
        from urllib.parse import quote
        user = quote(BASIC_AUTH_USER, safe='')
        passwd = quote(BASIC_AUTH_PASS, safe='')
        preauth_url = f"https://{user}:{passwd}@{service['subdomain']}.blaha.io/"

        return {"url": preauth_url, "service": service["name"]}

# =============================================================================
# PLEX INTEGRATION (Admin only)
# =============================================================================

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

@app.get("/api/plex/status")
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

@app.get("/api/plex/home-users")
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

@app.post("/api/friends/{friend_id}/plex-user")
async def create_plex_user_for_friend(friend_id: int, pin: str = "", _: bool = Depends(verify_admin)):
    """Create a Plex managed user for a friend."""
    account = get_plex_account()
    if not account:
        raise HTTPException(status_code=400, detail="Plex not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        if friend.get("plex_user_id"):
            raise HTTPException(status_code=400, detail="Friend already has Plex user")

        try:
            # Create managed user via Plex API
            # The createHomeUser method creates a managed/restricted user
            plex_user = account.createHomeUser(friend["name"], server=get_plex_server())

            # Set PIN if provided
            if pin:
                plex_user.updatePin(pin)

            # Store in database
            await db.execute(
                "UPDATE friends SET plex_user_id = ?, plex_pin = ? WHERE id = ?",
                (str(plex_user.id), pin, friend_id)
            )
            await db.commit()

            return {
                "status": "ok",
                "plex_user_id": str(plex_user.id),
                "plex_username": plex_user.title
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create Plex user: {str(e)}")

@app.delete("/api/friends/{friend_id}/plex-user")
async def remove_plex_user_for_friend(friend_id: int, delete_from_plex: bool = False, _: bool = Depends(verify_admin)):
    """Remove Plex managed user association, optionally delete from Plex too."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        if delete_from_plex:
            cursor = await db.execute("SELECT plex_user_id FROM friends WHERE id = ?", (friend_id,))
            friend = await cursor.fetchone()
            if friend and friend.get("plex_user_id"):
                account = get_plex_account()
                if account:
                    try:
                        for user in account.users():
                            if str(user.id) == friend["plex_user_id"]:
                                user.delete()
                                break
                    except Exception as e:
                        print(f"Failed to delete Plex user: {e}")

        await db.execute(
            "UPDATE friends SET plex_user_id = '', plex_pin = '' WHERE id = ?",
            (friend_id,)
        )
        await db.commit()
        return {"status": "ok"}

@app.put("/api/friends/{friend_id}/plex-pin")
async def update_plex_pin(friend_id: int, pin: str, _: bool = Depends(verify_admin)):
    """Update Plex PIN for a friend."""
    account = get_plex_account()
    if not account:
        raise HTTPException(status_code=400, detail="Plex not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()

        if not friend or not friend.get("plex_user_id"):
            raise HTTPException(status_code=404, detail="Friend has no Plex user")

        try:
            # Find and update the Plex user
            for user in account.users():
                if str(user.id) == friend["plex_user_id"]:
                    if pin:
                        user.updatePin(pin)
                    else:
                        user.removePin()
                    break

            await db.execute(
                "UPDATE friends SET plex_pin = ? WHERE id = ?",
                (pin, friend_id)
            )
            await db.commit()
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# OMBI INTEGRATION (Admin only)
# =============================================================================

import httpx

async def create_ombi_user(username: str) -> dict | None:
    """Create an Ombi user. Returns user info or None on failure."""
    if not OMBI_URL or not OMBI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            # Create user with a random password (they'll use Plex auth anyway)
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
                return {"id": data.get("id"), "username": username}
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

@app.get("/api/ombi/status")
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

# =============================================================================
# JELLYFIN INTEGRATION (Admin only)
# =============================================================================

async def create_jellyfin_user(username: str) -> dict | None:
    """Create a Jellyfin user. Returns user info or None on failure."""
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
                return {"id": data.get("Id"), "username": data.get("Name")}
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

@app.get("/api/jellyfin/status")
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

# =============================================================================
# AUTO ACCOUNT MANAGEMENT
# =============================================================================

# Service names that trigger auto-account creation (case-insensitive match)
MANAGED_SERVICES = {
    "plex": "plex_user_id",
    "ombi": "ombi_user_id",
    "jellyfin": "jellyfin_user_id"
}

async def handle_service_grant(friend_id: int, friend_name: str, service_name: str, db) -> dict:
    """Handle automatic account creation when a service is granted."""
    service_lower = service_name.lower()
    result = {"service": service_name, "action": None, "success": False, "error": None}

    if service_lower == "plex":
        account = get_plex_account()
        if account:
            try:
                plex_user = account.createHomeUser(friend_name, server=get_plex_server())
                await db.execute(
                    "UPDATE friends SET plex_user_id = ? WHERE id = ?",
                    (str(plex_user.id), friend_id)
                )
                result["action"] = "created"
                result["success"] = True
            except Exception as e:
                result["error"] = str(e)

    elif service_lower == "ombi":
        ombi_result = await create_ombi_user(friend_name)
        if ombi_result:
            await db.execute(
                "UPDATE friends SET ombi_user_id = ? WHERE id = ?",
                (str(ombi_result["id"]), friend_id)
            )
            result["action"] = "created"
            result["success"] = True
        else:
            result["error"] = "Failed to create Ombi user"

    elif service_lower == "jellyfin":
        jf_result = await create_jellyfin_user(friend_name)
        if jf_result:
            await db.execute(
                "UPDATE friends SET jellyfin_user_id = ? WHERE id = ?",
                (str(jf_result["id"]), friend_id)
            )
            result["action"] = "created"
            result["success"] = True
        else:
            result["error"] = "Failed to create Jellyfin user"

    return result

async def handle_service_revoke(friend_id: int, service_name: str, db) -> dict:
    """Handle automatic account deletion when a service is revoked."""
    service_lower = service_name.lower()
    result = {"service": service_name, "action": None, "success": False, "error": None}

    # Get current user IDs
    cursor = await db.execute(
        "SELECT plex_user_id, ombi_user_id, jellyfin_user_id FROM friends WHERE id = ?",
        (friend_id,)
    )
    friend = await cursor.fetchone()
    if not friend:
        return result

    if service_lower == "plex" and friend[0]:
        account = get_plex_account()
        if account:
            try:
                for user in account.users():
                    if str(user.id) == friend[0]:
                        user.delete()
                        break
                await db.execute(
                    "UPDATE friends SET plex_user_id = '', plex_pin = '' WHERE id = ?",
                    (friend_id,)
                )
                result["action"] = "deleted"
                result["success"] = True
            except Exception as e:
                result["error"] = str(e)

    elif service_lower == "ombi" and friend[1]:
        if await delete_ombi_user(friend[1]):
            await db.execute(
                "UPDATE friends SET ombi_user_id = '' WHERE id = ?",
                (friend_id,)
            )
            result["action"] = "deleted"
            result["success"] = True
        else:
            result["error"] = "Failed to delete Ombi user"

    elif service_lower == "jellyfin" and friend[2]:
        if await delete_jellyfin_user(friend[2]):
            await db.execute(
                "UPDATE friends SET jellyfin_user_id = '' WHERE id = ?",
                (friend_id,)
            )
            result["action"] = "deleted"
            result["success"] = True
        else:
            result["error"] = "Failed to delete Jellyfin user"

    return result

# =============================================================================
# FRIENDS (Admin only)
# =============================================================================

@app.get("/api/friends", response_model=list[Friend])
async def list_friends(_: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute("SELECT * FROM friends ORDER BY name")
        friends = await cursor.fetchall()

        for friend in friends:
            cursor = await db.execute(
                """SELECT s.* FROM services s
                   JOIN friend_services fs ON s.id = fs.service_id
                   WHERE fs.friend_id = ?
                   ORDER BY s.display_order, s.name""",
                (friend["id"],)
            )
            friend["services"] = await cursor.fetchall()

        return friends

@app.post("/api/friends", response_model=Friend)
async def create_friend(friend: FriendCreate, _: bool = Depends(verify_admin)):
    token = secrets.token_urlsafe(24)  # 32 char URL-safe token (24 bytes = 32 chars base64)

    async with await get_db() as db:
        cursor = await db.execute(
            "INSERT INTO friends (name, token) VALUES (?, ?)",
            (friend.name, token)
        )
        friend_id = cursor.lastrowid

        # Get default services if no specific services provided
        service_ids_to_add = friend.service_ids
        if not service_ids_to_add:
            cursor = await db.execute("SELECT id FROM services WHERE is_default = 1")
            default_services = await cursor.fetchall()
            service_ids_to_add = [row[0] for row in default_services]

        for service_id in service_ids_to_add:
            await db.execute(
                "INSERT OR IGNORE INTO friend_services (friend_id, service_id) VALUES (?, ?)",
                (friend_id, service_id)
            )

        await db.commit()

        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            """SELECT s.* FROM services s
               JOIN friend_services fs ON s.id = fs.service_id
               WHERE fs.friend_id = ?""",
            (friend_id,)
        )
        services = await cursor.fetchall()

        return Friend(
            id=friend_id,
            name=friend.name,
            token=token,
            services=services
        )

@app.put("/api/friends/{friend_id}", response_model=Friend)
async def update_friend(friend_id: int, update: FriendUpdate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Get friend info
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()
        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        if update.name is not None:
            await db.execute(
                "UPDATE friends SET name = ? WHERE id = ?",
                (update.name, friend_id)
            )

        account_results = []
        if update.service_ids is not None:
            # Get current services to detect changes
            cursor = await db.execute(
                """SELECT s.id, s.name FROM services s
                   JOIN friend_services fs ON s.id = fs.service_id
                   WHERE fs.friend_id = ?""",
                (friend_id,)
            )
            current_services = {row["id"]: row["name"] for row in await cursor.fetchall()}

            # Get all services to map IDs to names
            cursor = await db.execute("SELECT id, name FROM services")
            all_services = {row["id"]: row["name"] for row in await cursor.fetchall()}

            current_ids = set(current_services.keys())
            new_ids = set(update.service_ids)

            # Services being added
            added_ids = new_ids - current_ids
            # Services being removed
            removed_ids = current_ids - new_ids

            # Handle auto-account creation for added managed services
            for service_id in added_ids:
                service_name = all_services.get(service_id, "")
                if service_name.lower() in MANAGED_SERVICES:
                    # Check if user already has this account
                    col = MANAGED_SERVICES[service_name.lower()]
                    if not friend.get(col):
                        result = await handle_service_grant(friend_id, friend["name"], service_name, db)
                        account_results.append(result)

            # Handle auto-account deletion for removed managed services
            for service_id in removed_ids:
                service_name = current_services.get(service_id, "")
                if service_name.lower() in MANAGED_SERVICES:
                    result = await handle_service_revoke(friend_id, service_name, db)
                    account_results.append(result)

            # Update service associations
            await db.execute(
                "DELETE FROM friend_services WHERE friend_id = ?",
                (friend_id,)
            )
            for service_id in update.service_ids:
                await db.execute(
                    "INSERT INTO friend_services (friend_id, service_id) VALUES (?, ?)",
                    (friend_id, service_id)
                )

        await db.commit()

        # Reload friend with updated data
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()

        cursor = await db.execute(
            """SELECT s.* FROM services s
               JOIN friend_services fs ON s.id = fs.service_id
               WHERE fs.friend_id = ?""",
            (friend_id,)
        )
        friend["services"] = await cursor.fetchall()

        # Include account operation results in response
        if account_results:
            friend["account_operations"] = account_results

        return friend

@app.delete("/api/friends/{friend_id}")
async def delete_friend(friend_id: int, delete_accounts: bool = True, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Delete managed accounts if requested
        if delete_accounts:
            cursor = await db.execute(
                "SELECT plex_user_id, ombi_user_id, jellyfin_user_id FROM friends WHERE id = ?",
                (friend_id,)
            )
            friend = await cursor.fetchone()
            if friend:
                # Delete Plex user
                if friend.get("plex_user_id"):
                    account = get_plex_account()
                    if account:
                        try:
                            for user in account.users():
                                if str(user.id) == friend["plex_user_id"]:
                                    user.delete()
                                    break
                        except Exception as e:
                            print(f"Failed to delete Plex user: {e}")

                # Delete Ombi user
                if friend.get("ombi_user_id"):
                    await delete_ombi_user(friend["ombi_user_id"])

                # Delete Jellyfin user
                if friend.get("jellyfin_user_id"):
                    await delete_jellyfin_user(friend["jellyfin_user_id"])

        await db.execute("DELETE FROM friend_services WHERE friend_id = ?", (friend_id,))
        await db.execute("DELETE FROM friends WHERE id = ?", (friend_id,))
        await db.commit()
        return {"status": "ok"}

# =============================================================================
# FRIEND VIEW (Public with token)
# =============================================================================

@app.get("/api/f/{token}", response_model=FriendView)
async def get_friend_view(token: str):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        # Update last visit
        await db.execute(
            "UPDATE friends SET last_visit = ? WHERE id = ?",
            (datetime.now().isoformat(), friend["id"])
        )
        await db.commit()

        cursor = await db.execute(
            """SELECT s.* FROM services s
               JOIN friend_services fs ON s.id = fs.service_id
               WHERE fs.friend_id = ?
               ORDER BY s.display_order, s.name""",
            (friend["id"],)
        )
        services = await cursor.fetchall()

        return FriendView(name=friend["name"], services=services)

# =============================================================================
# FORWARD AUTH (for nginx auth_request)
# =============================================================================

@app.get("/api/auth/verify")
async def verify_forward_auth(
    request: Request,
    friend_token: Optional[str] = Cookie(default=None)
):
    """
    Forward auth endpoint for nginx auth_request.
    Validates friend token and checks service access.
    Returns 200 with user headers if authorized, 401/403 otherwise.
    """
    if not friend_token:
        raise HTTPException(status_code=401, detail="No token")

    # Get the requested service from X-Forwarded-Host header
    forwarded_host = request.headers.get("X-Forwarded-Host", "")
    # Extract subdomain (e.g., "ombi" from "ombi.blaha.io")
    subdomain = forwarded_host.split(".")[0] if forwarded_host else ""

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Validate token and get friend
        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?", (friend_token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Find service by subdomain
        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (subdomain,)
        )
        service = await cursor.fetchone()

        if not service:
            # Service not configured for SSO, allow through (or deny?)
            # For now, return 200 but without service-specific checks
            return Response(
                status_code=200,
                headers={
                    "X-Remote-User": friend["name"],
                    "X-Remote-Email": f"{friend['token']}@blaha.io",
                    "X-Friend-Token": friend["token"]
                }
            )

        # Check if friend has access to this service
        cursor = await db.execute(
            """SELECT 1 FROM friend_services
               WHERE friend_id = ? AND service_id = ?""",
            (friend["id"], service["id"])
        )
        has_access = await cursor.fetchone()

        if not has_access:
            # Return 403 with redirect info for access request page
            raise HTTPException(
                status_code=403,
                detail=f"No access to {service['name']}",
                headers={"X-Redirect-To": f"https://blaha.io/request-access?service={subdomain}"}
            )

        # Friend has access - return success with user headers
        return Response(
            status_code=200,
            headers={
                "X-Remote-User": friend["name"],
                "X-Remote-Email": f"{friend['token']}@blaha.io",
                "X-Friend-Token": friend["token"],
                "X-Friend-Id": str(friend["id"])
            }
        )

# =============================================================================
# ACCESS REQUESTS
# =============================================================================

@app.post("/api/access-requests")
async def create_access_request(
    service: str,  # subdomain
    friend_token: Optional[str] = Cookie(default=None)
):
    """Create an access request for a service."""
    if not friend_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Get friend
        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?", (friend_token,)
        )
        friend = await cursor.fetchone()
        if not friend:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get service by subdomain
        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (service,)
        )
        svc = await cursor.fetchone()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")

        # Check if already has access
        cursor = await db.execute(
            "SELECT 1 FROM friend_services WHERE friend_id = ? AND service_id = ?",
            (friend["id"], svc["id"])
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Already have access")

        # Check for existing pending request
        cursor = await db.execute(
            """SELECT 1 FROM access_requests
               WHERE friend_id = ? AND service_id = ? AND status = 'pending'""",
            (friend["id"], svc["id"])
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Request already pending")

        # Create request
        await db.execute(
            "INSERT INTO access_requests (friend_id, service_id) VALUES (?, ?)",
            (friend["id"], svc["id"])
        )
        await db.commit()

        return {"status": "ok", "message": f"Access requested for {svc['name']}"}

@app.get("/api/access-requests")
async def list_access_requests(_: bool = Depends(verify_admin)):
    """List all pending access requests (admin only)."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("""
            SELECT ar.*, f.name as friend_name, f.token as friend_token, s.name as service_name, s.subdomain
            FROM access_requests ar
            JOIN friends f ON ar.friend_id = f.id
            JOIN services s ON ar.service_id = s.id
            WHERE ar.status = 'pending'
            ORDER BY ar.requested_at DESC
        """)
        return await cursor.fetchall()

@app.post("/api/access-requests/{request_id}/approve")
async def approve_access_request(request_id: int, _: bool = Depends(verify_admin)):
    """Approve an access request."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Get the request
        cursor = await db.execute(
            "SELECT * FROM access_requests WHERE id = ?", (request_id,)
        )
        req = await cursor.fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")

        # Grant access
        await db.execute(
            "INSERT OR IGNORE INTO friend_services (friend_id, service_id) VALUES (?, ?)",
            (req["friend_id"], req["service_id"])
        )

        # Update request status
        await db.execute(
            "UPDATE access_requests SET status = 'approved' WHERE id = ?",
            (request_id,)
        )
        await db.commit()

        return {"status": "ok"}

@app.post("/api/access-requests/{request_id}/deny")
async def deny_access_request(request_id: int, _: bool = Depends(verify_admin)):
    """Deny an access request."""
    async with await get_db() as db:
        await db.execute(
            "UPDATE access_requests SET status = 'denied' WHERE id = ?",
            (request_id,)
        )
        await db.commit()
        return {"status": "ok"}

@app.get("/api/request-access-info")
async def get_request_access_info(
    service: str,
    friend_token: Optional[str] = Cookie(default=None)
):
    """Get info for the request access page."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        # Get service info
        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (service,)
        )
        svc = await cursor.fetchone()

        friend_name = None
        has_pending = False

        if friend_token:
            cursor = await db.execute(
                "SELECT * FROM friends WHERE token = ?", (friend_token,)
            )
            friend = await cursor.fetchone()
            if friend:
                friend_name = friend["name"]
                # Check for pending request
                if svc:
                    cursor = await db.execute(
                        """SELECT 1 FROM access_requests
                           WHERE friend_id = ? AND service_id = ? AND status = 'pending'""",
                        (friend["id"], svc["id"])
                    )
                    has_pending = await cursor.fetchone() is not None

        return {
            "service": svc,
            "friend_name": friend_name,
            "has_pending_request": has_pending
        }

# =============================================================================
# STATIC FILES & ROUTES
# =============================================================================

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/admin")
async def admin_page():
    return FileResponse("static/index.html")

@app.get("/request-access")
async def request_access_page():
    return FileResponse("static/index.html")

@app.get("/f/{token}")
async def friend_page(token: str, response: Response):
    # Validate token exists before setting cookie
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM friends WHERE token = ?", (token,)
        )
        friend = await cursor.fetchone()
        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

    # Set cookie for SSO across subdomains
    response.set_cookie(
        key="friend_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",  # Allow cross-subdomain
        domain=".blaha.io",  # Works for all *.blaha.io subdomains
        max_age=86400 * 30  # 30 days
    )
    return FileResponse("static/index.html")

# Mount static files last to avoid overriding API routes
app.mount("/static", StaticFiles(directory="static"), name="static")
