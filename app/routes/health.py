"""
Health check routes - proxy to blaha-health-daemon.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from services.session import verify_admin

router = APIRouter(prefix="/api/health", tags=["health"])

HEALTH_DAEMON_URL = "http://localhost:9876"


@router.get("/status")
async def health_status(_: bool = Depends(verify_admin)):
    """Get health summary counts."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/status")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Health daemon error: {e}")


@router.get("/results")
async def health_results(_: bool = Depends(verify_admin)):
    """Get all health check results."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/results")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Health daemon error: {e}")


@router.get("/containers")
async def health_containers(_: bool = Depends(verify_admin)):
    """Get health results grouped by container."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/containers")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Health daemon error: {e}")


@router.get("/infra")
async def health_infra(_: bool = Depends(verify_admin)):
    """Get infrastructure-only health checks."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{HEALTH_DAEMON_URL}/api/health/infra")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Health daemon error: {e}")


@router.post("/refresh")
async def health_refresh(_: bool = Depends(verify_admin)):
    """Trigger immediate health check refresh."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{HEALTH_DAEMON_URL}/api/health/refresh")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Health daemon error: {e}")
