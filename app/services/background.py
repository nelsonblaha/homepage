"""
Background tasks for real-time status updates.

Runs periodic health checks on services and pushes updates via WebSocket.
"""

import asyncio
from typing import List
import httpx

from database import get_db
from websocket import manager as ws_manager


# Health check interval in seconds
HEALTH_CHECK_INTERVAL = 30
JITSI_CHECK_INTERVAL = 5
INFRA_HEALTH_INTERVAL = 30
HEALTH_DAEMON_URL = "http://blaha-health-daemon:8000"


async def check_service_health(service_id: int, url: str) -> str:
    """
    Check if a service is accessible.

    Returns:
        'up' - Service responding with 200
        'down' - Service unreachable or error
        'auth_required' - Service returns 401 (basic auth)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 401:
                return "auth_required"
            elif response.status_code < 500:
                return "up"
            else:
                return "down"
    except Exception:
        return "down"


async def health_check_loop():
    """Periodically check all service health statuses."""
    while True:
        try:
            async with await get_db() as db:
                db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                cursor = await db.execute(
                    "SELECT id, url, subdomain FROM services WHERE url IS NOT NULL AND url != ''"
                )
                services = await cursor.fetchall()

            for service in services:
                url = service.get("url", "")
                if not url:
                    continue

                health = await check_service_health(service["id"], url)
                await ws_manager.update_service_status(service["id"], health)

        except Exception as e:
            print(f"Health check error: {e}")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


async def jitsi_check_loop():
    """Periodically check Jitsi participant count."""
    import os

    jitsi_url = os.environ.get("JITSI_URL", "")
    if not jitsi_url:
        return  # Jitsi not configured

    while True:
        try:
            # Try to get participant count from Jitsi
            # This typically requires hitting the SRMS API or parsing room info
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try common Jitsi stats endpoints
                stats_url = f"{jitsi_url.rstrip('/')}/room-stats"
                try:
                    response = await client.get(stats_url)
                    if response.status_code == 200:
                        data = response.json()
                        count = data.get("participants", 0)
                        await ws_manager.update_jitsi_participants(count)
                except Exception:
                    # Stats endpoint not available, try alternative
                    pass

        except Exception as e:
            print(f"Jitsi check error: {e}")

        await asyncio.sleep(JITSI_CHECK_INTERVAL)


async def infra_health_check_loop():
    """Periodically fetch infrastructure health from blaha-health-daemon."""
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/results")
                if response.status_code == 200:
                    data = response.json()
                    await ws_manager.update_infra_health(data)
        except Exception as e:
            print(f"Infra health check error: {e}")

        await asyncio.sleep(INFRA_HEALTH_INTERVAL)


async def start_background_tasks() -> List[asyncio.Task]:
    """Start all background tasks and return task handles."""
    tasks = [
        asyncio.create_task(health_check_loop()),
        asyncio.create_task(jitsi_check_loop()),
        asyncio.create_task(infra_health_check_loop()),
    ]
    return tasks
