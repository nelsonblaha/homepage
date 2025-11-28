"""
Auto Account Management

This module handles automatic account creation/deletion when services
are granted to or revoked from friends. It uses the integration registry
for most services, with special handling for Plex.
"""

from integrations.registry import (
    get_integration,
    get_db_columns,
    handle_service_grant_v2,
    handle_service_revoke_v2,
)
from integrations.plex import create_plex_user, delete_plex_user


async def handle_service_grant(friend_id: int, friend_name: str, service_name: str, db) -> dict:
    """
    Handle automatic account creation when a service is granted.

    Uses the registry for standard integrations, special handling for Plex.

    Args:
        friend_id: Database ID of the friend
        friend_name: Name of the friend (used as username)
        service_name: Service identifier (e.g., "ombi", "jellyfin")
        db: Database connection

    Returns:
        Dict with service, action, success, and error keys
    """
    service_lower = service_name.lower()

    # Special handling for Plex (different auth model)
    if service_lower == "plex":
        result = {"service": service_name, "action": None, "success": False, "error": None}
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
        return result

    # Use registry for all other services
    return await handle_service_grant_v2(friend_id, friend_name, service_lower, db)


async def handle_service_revoke(friend_id: int, service_name: str, db) -> dict:
    """
    Handle automatic account deletion when a service is revoked.

    Uses the registry for standard integrations, special handling for Plex.

    Args:
        friend_id: Database ID of the friend
        service_name: Service identifier
        db: Database connection

    Returns:
        Dict with service, action, success, and error keys
    """
    service_lower = service_name.lower()

    # Special handling for Plex
    if service_lower == "plex":
        result = {"service": service_name, "action": None, "success": False, "error": None}

        # Get current Plex user ID
        cursor = await db.execute(
            "SELECT plex_user_id FROM friends WHERE id = ?",
            (friend_id,)
        )
        row = await cursor.fetchone()

        if row and row[0]:
            if await delete_plex_user(row[0]):
                await db.execute(
                    "UPDATE friends SET plex_user_id = '', plex_pin = '' WHERE id = ?",
                    (friend_id,)
                )
                result["action"] = "deleted"
                result["success"] = True
            else:
                result["error"] = "Failed to delete Plex user"

        return result

    # Use registry for all other services
    return await handle_service_revoke_v2(friend_id, service_lower, db)
