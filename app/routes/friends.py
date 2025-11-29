"""Friend management routes - CRUD and service access"""
import secrets
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie

from database import get_db
from models import Friend, FriendCreate, FriendUpdate, FriendView
from services.session import verify_admin, SESSION_DURATION_LONG
from services.accounts import MANAGED_SERVICES, handle_service_grant, handle_service_revoke
from services.friend_auth import (
    check_auth_requirements, increment_usage, verify_password, verify_totp,
    hash_password, generate_totp_secret, get_totp_uri,
    PASSWORD_NOT_REQUIRED, PASSWORD_ALWAYS_REQUIRED, PASSWORD_AFTER_THRESHOLD
)
from services.activity import (
    log_activity, ACTION_PAGE_VIEW, ACTION_SERVICE_CLICK,
    ACTION_AUTH_LOGIN, ACTION_CREDENTIAL_VIEW
)
from integrations.plex import get_plex_account, delete_plex_user
from integrations.ombi import delete_ombi_user
from integrations.jellyfin import delete_jellyfin_user
from integrations.nextcloud import delete_nextcloud_user
from integrations.overseerr import delete_overseerr_user
from integrations.jellyseerr import jellyseerr_integration
from integrations.mattermost import delete_mattermost_user

router = APIRouter(prefix="/api/friends", tags=["friends"])


@router.get("", response_model=list[Friend])
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


@router.post("", response_model=Friend)
async def create_friend(friend: FriendCreate, _: bool = Depends(verify_admin)):
    token = secrets.token_urlsafe(24)

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

        # Get service names to check for managed services
        if service_ids_to_add:
            placeholders = ",".join("?" * len(service_ids_to_add))
            cursor = await db.execute(
                f"SELECT id, name FROM services WHERE id IN ({placeholders})",
                service_ids_to_add
            )
            services_info = await cursor.fetchall()

            # Create accounts for managed services (Ombi, Jellyfin, Plex)
            for service_id, service_name in services_info:
                if service_name.lower() in MANAGED_SERVICES:
                    await handle_service_grant(friend_id, friend.name, service_name, db)

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


@router.put("/{friend_id}", response_model=Friend)
async def update_friend(friend_id: int, update: FriendUpdate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

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

            cursor = await db.execute("SELECT id, name FROM services")
            all_services = {row["id"]: row["name"] for row in await cursor.fetchall()}

            current_ids = set(current_services.keys())
            new_ids = set(update.service_ids)

            added_ids = new_ids - current_ids
            removed_ids = current_ids - new_ids

            # Handle auto-account creation for added managed services
            for service_id in added_ids:
                service_name = all_services.get(service_id, "")
                if service_name.lower() in MANAGED_SERVICES:
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

        if account_results:
            friend["account_operations"] = account_results

        return friend


@router.delete("/{friend_id}")
async def delete_friend(friend_id: int, delete_accounts: bool = True, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        if delete_accounts:
            cursor = await db.execute(
                "SELECT plex_user_id, ombi_user_id, jellyfin_user_id, nextcloud_user_id, overseerr_user_id, jellyseerr_user_id, mattermost_user_id FROM friends WHERE id = ?",
                (friend_id,)
            )
            friend = await cursor.fetchone()
            if friend:
                if friend.get("plex_user_id"):
                    await delete_plex_user(friend["plex_user_id"])
                if friend.get("ombi_user_id"):
                    await delete_ombi_user(friend["ombi_user_id"])
                if friend.get("jellyfin_user_id"):
                    await delete_jellyfin_user(friend["jellyfin_user_id"])
                if friend.get("nextcloud_user_id"):
                    await delete_nextcloud_user(friend["nextcloud_user_id"])
                if friend.get("overseerr_user_id"):
                    await delete_overseerr_user(friend["overseerr_user_id"])
                if friend.get("jellyseerr_user_id"):
                    await jellyseerr_integration.delete_user(friend["jellyseerr_user_id"])
                if friend.get("mattermost_user_id"):
                    await delete_mattermost_user(friend["mattermost_user_id"])

        await db.execute("DELETE FROM friend_services WHERE friend_id = ?", (friend_id,))
        await db.execute("DELETE FROM friends WHERE id = ?", (friend_id,))
        await db.commit()
        return {"status": "ok"}


# =============================================================================
# FRIEND VIEW (Public with token)
# =============================================================================

# Note: This is mounted at /api, so full path is /api/f/{token}
public_router = APIRouter(tags=["friends-public"])


@public_router.get("/f/{token}")
async def get_friend_view(token: str, authenticated: bool = False):
    """
    Get friend view with services.

    Returns auth requirements if the friend needs to authenticate.
    The 'authenticated' param is set by the login route after successful auth.
    """
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        # Check auth requirements
        auth_req = check_auth_requirements(friend)

        # Check if expired
        if auth_req.is_expired:
            raise HTTPException(status_code=403, detail=auth_req.error_message or "Access expired")

        # Increment usage count on each visit
        new_count = await increment_usage(db, friend["id"])

        # Update last visit
        await db.execute(
            "UPDATE friends SET last_visit = ? WHERE id = ?",
            (datetime.now().isoformat(), friend["id"])
        )

        # Log page view activity
        await log_activity(db, ACTION_PAGE_VIEW, friend_id=friend["id"])
        await db.commit()

        # Re-check auth requirements after incrementing (threshold may have been crossed)
        friend["usage_count"] = new_count
        auth_req = check_auth_requirements(friend)

        # Build response
        cursor = await db.execute(
            """SELECT s.* FROM services s
               JOIN friend_services fs ON s.id = fs.service_id
               WHERE fs.friend_id = ?
               ORDER BY s.display_order, s.name""",
            (friend["id"],)
        )
        services = await cursor.fetchall()

        response = {
            "id": friend["id"],
            "name": friend["name"],
            "services": services,
            "usage_count": new_count,
        }

        # Include auth requirement info if needed
        if auth_req.needs_password or auth_req.needs_totp:
            response["auth_required"] = True
            response["needs_password"] = auth_req.needs_password
            response["needs_totp"] = auth_req.needs_totp

        if auth_req.usage_warning:
            password_threshold = friend.get("password_required_after", 10)
            remaining = password_threshold - new_count
            response["usage_warning"] = True
            response["uses_remaining"] = remaining

        return response


@public_router.post("/f/{token}/login")
async def friend_login(token: str, password: str = None, totp_code: str = None):
    """
    Authenticate a friend with password and/or TOTP.

    Returns success status and session token on successful auth.
    """
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        auth_req = check_auth_requirements(friend)

        if auth_req.is_expired:
            raise HTTPException(status_code=403, detail="Access expired")

        # Verify password if required
        if auth_req.needs_password:
            if not password:
                raise HTTPException(status_code=400, detail="Password required")
            if not verify_password(password, friend.get("password_hash", "")):
                raise HTTPException(status_code=401, detail="Invalid password")

        # Verify TOTP if required
        if auth_req.needs_totp:
            if not totp_code:
                raise HTTPException(status_code=400, detail="2FA code required")
            if not verify_totp(friend.get("totp_secret", ""), totp_code):
                raise HTTPException(status_code=401, detail="Invalid 2FA code")

        return {"status": "ok", "authenticated": True}


@public_router.post("/f/{token}/setup-password")
async def setup_friend_password(token: str, password: str):
    """
    Set up password for a friend (when required after threshold).

    Password must be at least 8 characters.
    """
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        password_hash = hash_password(password)
        await db.execute(
            "UPDATE friends SET password_hash = ? WHERE id = ?",
            (password_hash, friend["id"])
        )
        await db.commit()

        return {"status": "ok"}


@public_router.post("/f/{token}/setup-totp")
async def setup_friend_totp(token: str):
    """
    Generate a new TOTP secret for a friend.

    Returns the secret and a QR code URI for authenticator apps.
    """
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        secret = generate_totp_secret()
        uri = get_totp_uri(secret, friend["name"])

        # Store secret (will be confirmed after first successful verify)
        await db.execute(
            "UPDATE friends SET totp_secret = ? WHERE id = ?",
            (secret, friend["id"])
        )
        await db.commit()

        return {"secret": secret, "uri": uri}


@public_router.post("/f/{token}/verify-totp")
async def verify_friend_totp(token: str, code: str):
    """
    Verify a TOTP code to confirm 2FA setup.
    """
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        if not friend.get("totp_secret"):
            raise HTTPException(status_code=400, detail="No TOTP secret configured")

        if verify_totp(friend["totp_secret"], code):
            return {"status": "ok", "verified": True}
        else:
            raise HTTPException(status_code=401, detail="Invalid code")


@public_router.get("/f/{token}/credentials/{service_key}")
async def get_friend_credentials(token: str, service_key: str):
    """Get stored credentials for a service (Nextcloud, etc.)"""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        # Map service key to credential fields
        credential_map = {
            "nextcloud": ("nextcloud_user_id", "nextcloud_password"),
            "ombi": ("ombi_user_id", "ombi_password"),
            "jellyfin": ("jellyfin_user_id", "jellyfin_password"),
            "overseerr": ("overseerr_user_id", "overseerr_password"),
            "jellyseerr": ("jellyseerr_user_id", "jellyseerr_password"),
            "mattermost": ("mattermost_user_id", "mattermost_password"),
            "chat": ("mattermost_user_id", "mattermost_password"),  # alias for subdomain
        }

        service_lower = service_key.lower()
        if service_lower not in credential_map:
            raise HTTPException(status_code=404, detail="No credentials for this service")

        user_field, pass_field = credential_map[service_lower]
        username = friend.get(user_field, "")
        password = friend.get(pass_field, "")

        if not username or not password:
            raise HTTPException(status_code=404, detail="No credentials stored")

        # Log credential view
        await log_activity(
            db, ACTION_CREDENTIAL_VIEW,
            friend_id=friend["id"],
            details=service_key
        )
        await db.commit()

        return {"username": username, "password": password}


@public_router.post("/f/{token}/click/{service_id}")
async def log_service_click(token: str, service_id: int):
    """Log when a friend clicks a service link."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT id FROM friends WHERE token = ?",
            (token,)
        )
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

        # Verify service exists and friend has access
        cursor = await db.execute(
            """SELECT s.name FROM services s
               JOIN friend_services fs ON s.id = fs.service_id
               WHERE s.id = ? AND fs.friend_id = ?""",
            (service_id, friend["id"])
        )
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        await log_activity(
            db, ACTION_SERVICE_CLICK,
            friend_id=friend["id"],
            service_id=service_id
        )
        await db.commit()

        return {"status": "ok"}
