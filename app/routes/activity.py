"""Activity routes - admin dashboard activity log and stats."""
from typing import Optional
from fastapi import APIRouter, Depends, Query

from database import get_db
from services.session import verify_admin
from services.activity import get_recent_activity, get_activity_stats

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
async def list_activity(
    limit: int = Query(default=50, le=200),
    friend_id: Optional[int] = None,
    _: bool = Depends(verify_admin)
):
    """Get recent activity log entries."""
    async with await get_db() as db:
        activities = await get_recent_activity(db, limit=limit, friend_id=friend_id)
        return activities


@router.get("/stats")
async def activity_stats(
    days: int = Query(default=7, le=90),
    _: bool = Depends(verify_admin)
):
    """Get activity statistics for the dashboard."""
    async with await get_db() as db:
        stats = await get_activity_stats(db, days=days)
        return stats
