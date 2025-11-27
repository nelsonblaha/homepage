"""Jitsi integration for blaha.io - participant count tracking"""
import os
import httpx
from fastapi import APIRouter

# Jicofo stats endpoint - internal Docker network
JICOFO_STATS_URL = os.environ.get("JICOFO_STATS_URL", "http://172.20.0.4:8888/stats")

router = APIRouter(prefix="/api/jitsi", tags=["jitsi"])


@router.get("/participants")
async def get_jitsi_participants():
    """Get total participant count from Jitsi."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JICOFO_STATS_URL, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "count": data.get("participants", 0),  # Current live count
                    "conferences": data.get("conferences", 0)
                }
    except Exception as e:
        print(f"Jitsi stats error: {e}")
    return {"count": 0, "conferences": 0}


@router.get("/status")
async def jitsi_status():
    """Check Jitsi connection status."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JICOFO_STATS_URL, timeout=5.0)
            if resp.status_code == 200:
                return {"connected": True}
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": False, "error": "Connection failed"}
