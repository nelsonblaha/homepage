"""Service management routes for blaha.io"""
import os
from fastapi import APIRouter, HTTPException, Depends

from database import get_db
from models import Service, ServiceCreate
from services.session import verify_admin

BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "ben")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")

router = APIRouter(prefix="/api/services", tags=["services"])


@router.get("", response_model=list[Service])
async def list_services(_: bool = Depends(verify_admin)):
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            "SELECT * FROM services ORDER BY display_order, name"
        )
        rows = await cursor.fetchall()
        return rows


@router.post("", response_model=Service)
async def create_service(service: ServiceCreate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO services (name, url, icon, description, display_order, subdomain, stack, is_default)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0)
        )
        await db.commit()
        return Service(id=cursor.lastrowid, **service.model_dump())


@router.put("/{service_id}", response_model=Service)
async def update_service(service_id: int, service: ServiceCreate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        await db.execute(
            """UPDATE services SET name=?, url=?, icon=?, description=?, display_order=?,
               subdomain=?, stack=?, is_default=? WHERE id=?""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0, service_id)
        )
        await db.commit()
        return Service(id=service_id, **service.model_dump())


@router.delete("/{service_id}")
async def delete_service(service_id: int, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        await db.execute("DELETE FROM friend_services WHERE service_id = ?", (service_id,))
        await db.execute("DELETE FROM services WHERE id = ?", (service_id,))
        await db.commit()
        return {"status": "ok"}


@router.post("/{service_id}/toggle-default")
async def toggle_service_default(service_id: int, _: bool = Depends(verify_admin)):
    """Toggle whether a service is granted by default to new friends."""
    async with await get_db() as db:
        cursor = await db.execute("SELECT is_default FROM services WHERE id = ?", (service_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Service not found")

        new_value = 0 if row[0] else 1
        await db.execute("UPDATE services SET is_default = ? WHERE id = ?", (new_value, service_id))
        await db.commit()
        return {"status": "ok", "is_default": bool(new_value)}


@router.get("/{service_id}/preauth-url")
async def get_preauth_url(service_id: int, _: bool = Depends(verify_admin)):
    """Generate a pre-authenticated URL for a service with embedded basic auth credentials."""
    if not BASIC_AUTH_PASS:
        raise HTTPException(status_code=400, detail="Basic auth not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        if not service.get("subdomain"):
            raise HTTPException(status_code=400, detail="Service has no subdomain configured")

        from urllib.parse import quote
        user = quote(BASIC_AUTH_USER, safe='')
        passwd = quote(BASIC_AUTH_PASS, safe='')
        preauth_url = f"https://{user}:{passwd}@{service['subdomain']}.blaha.io/"

        return {"url": preauth_url, "service": service["name"]}
