"""Activity tracking service for admin dashboard."""
from datetime import datetime
from typing import Optional


# Activity types
ACTION_PAGE_VIEW = "page_view"          # Friend viewed their homepage
ACTION_SERVICE_CLICK = "service_click"  # Friend clicked a service link
ACTION_AUTH_LOGIN = "auth_login"        # Friend authenticated (password/TOTP)
ACTION_CREDENTIAL_VIEW = "credential_view"  # Friend viewed credentials


async def log_activity(
    db,
    action: str,
    friend_id: Optional[int] = None,
    service_id: Optional[int] = None,
    details: str = ""
):
    """
    Log an activity event.

    Args:
        db: Database connection
        action: Type of action (see ACTION_* constants)
        friend_id: ID of the friend (if applicable)
        service_id: ID of the service (if applicable)
        details: Additional details about the action
    """
    await db.execute(
        """INSERT INTO activity_log (friend_id, service_id, action, details, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (friend_id, service_id, action, details, datetime.now().isoformat())
    )
    # Note: caller should commit


async def get_recent_activity(db, limit: int = 50, friend_id: Optional[int] = None):
    """
    Get recent activity log entries.

    Args:
        db: Database connection
        limit: Maximum number of entries to return
        friend_id: Filter by specific friend (optional)

    Returns:
        List of activity entries with friend and service names
    """
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    if friend_id:
        cursor = await db.execute(
            """SELECT
                a.id, a.action, a.details, a.created_at,
                f.id as friend_id, f.name as friend_name,
                s.id as service_id, s.name as service_name
               FROM activity_log a
               LEFT JOIN friends f ON a.friend_id = f.id
               LEFT JOIN services s ON a.service_id = s.id
               WHERE a.friend_id = ?
               ORDER BY a.created_at DESC
               LIMIT ?""",
            (friend_id, limit)
        )
    else:
        cursor = await db.execute(
            """SELECT
                a.id, a.action, a.details, a.created_at,
                f.id as friend_id, f.name as friend_name,
                s.id as service_id, s.name as service_name
               FROM activity_log a
               LEFT JOIN friends f ON a.friend_id = f.id
               LEFT JOIN services s ON a.service_id = s.id
               ORDER BY a.created_at DESC
               LIMIT ?""",
            (limit,)
        )

    return await cursor.fetchall()


async def get_activity_stats(db, days: int = 7):
    """
    Get activity statistics for the admin dashboard.

    Args:
        db: Database connection
        days: Number of days to include in stats

    Returns:
        Dict with activity counts and top services
    """
    db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

    # Total page views in period
    cursor = await db.execute(
        """SELECT COUNT(*) as count FROM activity_log
           WHERE action = ? AND created_at >= datetime('now', ?)""",
        (ACTION_PAGE_VIEW, f"-{days} days")
    )
    page_views = (await cursor.fetchone())["count"]

    # Total service clicks in period
    cursor = await db.execute(
        """SELECT COUNT(*) as count FROM activity_log
           WHERE action = ? AND created_at >= datetime('now', ?)""",
        (ACTION_SERVICE_CLICK, f"-{days} days")
    )
    service_clicks = (await cursor.fetchone())["count"]

    # Unique active friends in period
    cursor = await db.execute(
        """SELECT COUNT(DISTINCT friend_id) as count FROM activity_log
           WHERE friend_id IS NOT NULL AND created_at >= datetime('now', ?)""",
        (f"-{days} days",)
    )
    active_friends = (await cursor.fetchone())["count"]

    # Top services by clicks
    cursor = await db.execute(
        """SELECT s.name, COUNT(*) as clicks
           FROM activity_log a
           JOIN services s ON a.service_id = s.id
           WHERE a.action = ? AND a.created_at >= datetime('now', ?)
           GROUP BY s.id
           ORDER BY clicks DESC
           LIMIT 5""",
        (ACTION_SERVICE_CLICK, f"-{days} days")
    )
    top_services = await cursor.fetchall()

    # Most active friends
    cursor = await db.execute(
        """SELECT f.name, COUNT(*) as visits
           FROM activity_log a
           JOIN friends f ON a.friend_id = f.id
           WHERE a.action = ? AND a.created_at >= datetime('now', ?)
           GROUP BY f.id
           ORDER BY visits DESC
           LIMIT 5""",
        (ACTION_PAGE_VIEW, f"-{days} days")
    )
    top_friends = await cursor.fetchall()

    return {
        "period_days": days,
        "page_views": page_views,
        "service_clicks": service_clicks,
        "active_friends": active_friends,
        "top_services": top_services,
        "top_friends": top_friends
    }
