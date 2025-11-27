"""Friend management routes for blaha.io"""
import secrets
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie

from database import get_db
from models import Friend, FriendCreate, FriendUpdate, FriendView
from services.session import verify_admin, SESSION_DURATION_LONG
from services.accounts import MANAGED_SERVICES, handle_service_grant, handle_service_revoke
from integrations.plex import get_plex_account, delete_plex_user
from integrations.ombi import delete_ombi_user
from integrations.jellyfin import delete_jellyfin_user
from integrations.nextcloud import delete_nextcloud_user
from integrations.overseerr import delete_overseerr_user

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
                "SELECT plex_user_id, ombi_user_id, jellyfin_user_id, nextcloud_user_id, overseerr_user_id FROM friends WHERE id = ?",
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

        await db.execute("DELETE FROM friend_services WHERE friend_id = ?", (friend_id,))
        await db.execute("DELETE FROM friends WHERE id = ?", (friend_id,))
        await db.commit()
        return {"status": "ok"}


# =============================================================================
# FRIEND VIEW (Public with token)
# =============================================================================

# Note: This is mounted at /api, so full path is /api/f/{token}
public_router = APIRouter(tags=["friends-public"])


@public_router.get("/f/{token}", response_model=FriendView)
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
        }

        service_lower = service_key.lower()
        if service_lower not in credential_map:
            raise HTTPException(status_code=404, detail="No credentials for this service")

        user_field, pass_field = credential_map[service_lower]
        username = friend.get(user_field, "")
        password = friend.get(pass_field, "")

        if not username or not password:
            raise HTTPException(status_code=404, detail="No credentials stored")

        return {"username": username, "password": password}
