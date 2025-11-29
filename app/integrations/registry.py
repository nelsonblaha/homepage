"""
Integration Registry - Service Dispatch and Discovery

This module provides a registry for all integration implementations.
It bridges the capabilities registry (what services CAN do) with the
actual implementations (code that DOES things).

Usage:
    from integrations.registry import get_integration, handle_service_grant

    # Get an integration instance
    integration = get_integration("ombi")
    if integration:
        result = await integration.create_user("Alice")

    # Or use the high-level handlers
    result = await handle_service_grant(friend_id, "Alice", "ombi", db)
"""

from typing import Optional, TYPE_CHECKING

from integrations.base import IntegrationBase, UserResult

if TYPE_CHECKING:
    import aiosqlite


# =============================================================================
# INTEGRATION REGISTRY
# =============================================================================

# Map service slugs to their integration instances
# This is populated lazily on first access to avoid circular imports
_INTEGRATIONS: dict[str, IntegrationBase] = {}
_REGISTRY_INITIALIZED = False


def _init_registry():
    """Initialize the registry with all available integrations."""
    global _REGISTRY_INITIALIZED, _INTEGRATIONS

    if _REGISTRY_INITIALIZED:
        return

    # Import integration modules here to avoid circular imports
    # Each integration module should export a singleton instance
    try:
        from integrations.ombi import ombi_integration
        _INTEGRATIONS["ombi"] = ombi_integration
    except ImportError:
        pass

    try:
        from integrations.jellyfin import jellyfin_integration
        _INTEGRATIONS["jellyfin"] = jellyfin_integration
    except ImportError:
        pass

    try:
        from integrations.overseerr import overseerr_integration
        _INTEGRATIONS["overseerr"] = overseerr_integration
    except ImportError:
        pass

    try:
        from integrations.mattermost import mattermost_integration
        _INTEGRATIONS["mattermost"] = mattermost_integration
        _INTEGRATIONS["chat"] = mattermost_integration  # Alias
    except ImportError:
        pass

    try:
        from integrations.nextcloud import nextcloud_integration
        _INTEGRATIONS["nextcloud"] = nextcloud_integration
    except ImportError:
        pass

    try:
        from integrations.plex import plex_integration
        _INTEGRATIONS["plex"] = plex_integration
    except ImportError:
        pass

    _REGISTRY_INITIALIZED = True


def get_integration(slug: str) -> Optional[IntegrationBase]:
    """
    Get an integration instance by slug.

    Args:
        slug: Service slug (e.g., "ombi", "jellyfin")

    Returns:
        Integration instance or None if not found/not implemented
    """
    _init_registry()
    return _INTEGRATIONS.get(slug.lower())


def get_all_integrations() -> dict[str, IntegrationBase]:
    """Get all registered integration instances."""
    _init_registry()
    return _INTEGRATIONS.copy()


def is_managed_service(slug: str) -> bool:
    """Check if a service has user management capabilities."""
    integration = get_integration(slug)
    return integration is not None


# =============================================================================
# DATABASE COLUMN MAPPING
# =============================================================================

# Maps service slugs to their database column names
# This centralizes the knowledge of how user IDs are stored
SERVICE_DB_COLUMNS = {
    "plex": ("plex_user_id", "plex_pin"),
    "ombi": ("ombi_user_id", "ombi_password"),
    "jellyfin": ("jellyfin_user_id", "jellyfin_password"),
    "nextcloud": ("nextcloud_user_id", "nextcloud_password"),
    "overseerr": ("overseerr_user_id", "overseerr_password"),
    "mattermost": ("mattermost_user_id", "mattermost_password"),
    "chat": ("mattermost_user_id", "mattermost_password"),  # Alias
}


def get_db_columns(slug: str) -> tuple[str, str]:
    """
    Get database column names for a service.

    Returns:
        Tuple of (user_id_column, password_column)
    """
    return SERVICE_DB_COLUMNS.get(slug.lower(), ("", ""))


# =============================================================================
# HIGH-LEVEL HANDLERS (for use in accounts.py)
# =============================================================================

async def handle_service_grant_v2(
    friend_id: int,
    friend_name: str,
    service_slug: str,
    db: "aiosqlite.Connection"
) -> dict:
    """
    Handle automatic account creation when a service is granted.

    This is the registry-based replacement for the if/elif chain in accounts.py.

    Args:
        friend_id: Database ID of the friend
        friend_name: Name of the friend (used as username)
        service_slug: Service identifier (e.g., "ombi")
        db: Database connection

    Returns:
        Dict with service, action, success, and error keys
    """
    result = {
        "service": service_slug,
        "action": None,
        "success": False,
        "error": None
    }

    integration = get_integration(service_slug)
    if not integration:
        # Not a managed service, skip silently
        return result

    # Create the user
    user_result = await integration.create_user(friend_name)

    if user_result.success:
        # Update database with user ID and password
        user_id_col, password_col = get_db_columns(service_slug)
        if user_id_col:
            await db.execute(
                f"UPDATE friends SET {user_id_col} = ?, {password_col} = ? WHERE id = ?",
                (user_result.user_id, user_result.password or "", friend_id)
            )

        result["action"] = "created"
        result["success"] = True
    else:
        result["error"] = user_result.error or f"Failed to create {service_slug} user"

    return result


async def handle_service_revoke_v2(
    friend_id: int,
    service_slug: str,
    db: "aiosqlite.Connection"
) -> dict:
    """
    Handle automatic account deletion when a service is revoked.

    Args:
        friend_id: Database ID of the friend
        service_slug: Service identifier
        db: Database connection

    Returns:
        Dict with service, action, success, and error keys
    """
    result = {
        "service": service_slug,
        "action": None,
        "success": False,
        "error": None
    }

    integration = get_integration(service_slug)
    if not integration:
        return result

    # Get the user ID from database
    user_id_col, password_col = get_db_columns(service_slug)
    if not user_id_col:
        return result

    cursor = await db.execute(
        f"SELECT {user_id_col} FROM friends WHERE id = ?",
        (friend_id,)
    )
    row = await cursor.fetchone()

    # Support both tuple and dict row formats (depends on row_factory setting)
    if isinstance(row, dict):
        user_id = row.get(user_id_col)
    else:
        user_id = row[0] if row else None

    if not user_id:
        # No user ID stored, nothing to delete
        return result

    # Delete the user
    if await integration.delete_user(user_id):
        await db.execute(
            f"UPDATE friends SET {user_id_col} = '', {password_col} = '' WHERE id = ?",
            (friend_id,)
        )
        result["action"] = "deleted"
        result["success"] = True
    else:
        result["error"] = f"Failed to delete {service_slug} user"

    return result


# =============================================================================
# STATUS CHECKING
# =============================================================================

async def check_all_integrations_status() -> dict[str, dict]:
    """
    Check status of all configured integrations.

    Returns:
        Dict mapping service slugs to their status
    """
    _init_registry()
    results = {}

    for slug, integration in _INTEGRATIONS.items():
        if slug in ("chat",):  # Skip aliases
            continue

        if not integration.is_configured:
            results[slug] = {"connected": False, "error": "Not configured"}
            continue

        try:
            status = await integration.check_status()
            results[slug] = {
                "connected": status.connected,
                "serverName": status.server_name,
                "error": status.error
            }
        except Exception as e:
            results[slug] = {"connected": False, "error": str(e)}

    return results
