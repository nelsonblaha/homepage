"""Auto account management for blaha.io"""
from integrations.plex import create_plex_user, delete_plex_user, get_plex_account
from integrations.ombi import create_ombi_user, delete_ombi_user
from integrations.jellyfin import create_jellyfin_user, delete_jellyfin_user

# Service names that trigger auto-account creation (case-insensitive match)
# Plex removed - users need plex.tv accounts, we just skip basic auth for them
MANAGED_SERVICES = {
    "ombi": "ombi_user_id",
    "jellyfin": "jellyfin_user_id"
}


async def handle_service_grant(friend_id: int, friend_name: str, service_name: str, db) -> dict:
    """Handle automatic account creation when a service is granted."""
    service_lower = service_name.lower()
    result = {"service": service_name, "action": None, "success": False, "error": None}

    if service_lower == "plex":
        plex_result = await create_plex_user(friend_name)
        if plex_result:
            await db.execute(
                "UPDATE friends SET plex_user_id = ? WHERE id = ?",
                (plex_result["id"], friend_id)
            )
            result["action"] = "created"
            result["success"] = True
        else:
            result["error"] = "Failed to create Plex user"

    elif service_lower == "ombi":
        ombi_result = await create_ombi_user(friend_name)
        if ombi_result:
            await db.execute(
                "UPDATE friends SET ombi_user_id = ?, ombi_password = ? WHERE id = ?",
                (str(ombi_result["id"]), ombi_result.get("password", ""), friend_id)
            )
            result["action"] = "created"
            result["success"] = True
        else:
            result["error"] = "Failed to create Ombi user"

    elif service_lower == "jellyfin":
        jf_result = await create_jellyfin_user(friend_name)
        if jf_result:
            await db.execute(
                "UPDATE friends SET jellyfin_user_id = ?, jellyfin_password = ? WHERE id = ?",
                (str(jf_result["id"]), jf_result.get("password", ""), friend_id)
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
        if await delete_plex_user(friend[0]):
            await db.execute(
                "UPDATE friends SET plex_user_id = '', plex_pin = '' WHERE id = ?",
                (friend_id,)
            )
            result["action"] = "deleted"
            result["success"] = True
        else:
            result["error"] = "Failed to delete Plex user"

    elif service_lower == "ombi" and friend[1]:
        if await delete_ombi_user(friend[1]):
            await db.execute(
                "UPDATE friends SET ombi_user_id = '', ombi_password = '' WHERE id = ?",
                (friend_id,)
            )
            result["action"] = "deleted"
            result["success"] = True
        else:
            result["error"] = "Failed to delete Ombi user"

    elif service_lower == "jellyfin" and friend[2]:
        if await delete_jellyfin_user(friend[2]):
            await db.execute(
                "UPDATE friends SET jellyfin_user_id = '', jellyfin_password = '' WHERE id = ?",
                (friend_id,)
            )
            result["action"] = "deleted"
            result["success"] = True
        else:
            result["error"] = "Failed to delete Jellyfin user"

    return result
