"""Access request routes for blaha.io"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Cookie

from database import get_db
from services.session import verify_admin

router = APIRouter(prefix="/api", tags=["requests"])


@router.post("/access-requests")
async def create_access_request(
    service: str,  # subdomain
    friend_token: Optional[str] = Cookie(default=None)
):
    """Create an access request for a service."""
    if not friend_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM friends WHERE token = ?", (friend_token,)
        )
        friend = await cursor.fetchone()
        if not friend:
            raise HTTPException(status_code=401, detail="Invalid token")

        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (service,)
        )
        svc = await cursor.fetchone()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")

        # Check if already has access
        cursor = await db.execute(
            "SELECT 1 FROM friend_services WHERE friend_id = ? AND service_id = ?",
            (friend["id"], svc["id"])
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Already have access")

        # Check for existing pending request
        cursor = await db.execute(
            """SELECT 1 FROM access_requests
               WHERE friend_id = ? AND service_id = ? AND status = 'pending'""",
            (friend["id"], svc["id"])
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail="Request already pending")

        # Create request
        await db.execute(
            "INSERT INTO access_requests (friend_id, service_id) VALUES (?, ?)",
            (friend["id"], svc["id"])
        )
        await db.commit()

        return {"status": "ok", "message": f"Access requested for {svc['name']}"}


@router.get("/access-requests")
async def list_access_requests(_: bool = Depends(verify_admin)):
    """List all pending access requests (admin only)."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("""
            SELECT ar.*, f.name as friend_name, f.token as friend_token, s.name as service_name, s.subdomain
            FROM access_requests ar
            JOIN friends f ON ar.friend_id = f.id
            JOIN services s ON ar.service_id = s.id
            WHERE ar.status = 'pending'
            ORDER BY ar.requested_at DESC
        """)
        return await cursor.fetchall()


@router.post("/access-requests/{request_id}/approve")
async def approve_access_request(request_id: int, _: bool = Depends(verify_admin)):
    """Approve an access request."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM access_requests WHERE id = ?", (request_id,)
        )
        req = await cursor.fetchone()
        if not req:
            raise HTTPException(status_code=404, detail="Request not found")

        await db.execute(
            "INSERT OR IGNORE INTO friend_services (friend_id, service_id) VALUES (?, ?)",
            (req["friend_id"], req["service_id"])
        )

        await db.execute(
            "UPDATE access_requests SET status = 'approved' WHERE id = ?",
            (request_id,)
        )
        await db.commit()

        return {"status": "ok"}


@router.post("/access-requests/{request_id}/deny")
async def deny_access_request(request_id: int, _: bool = Depends(verify_admin)):
    """Deny an access request."""
    async with await get_db() as db:
        await db.execute(
            "UPDATE access_requests SET status = 'denied' WHERE id = ?",
            (request_id,)
        )
        await db.commit()
        return {"status": "ok"}


@router.get("/request-access-info")
async def get_request_access_info(
    service: str,
    friend_token: Optional[str] = Cookie(default=None)
):
    """Get info for the request access page."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        cursor = await db.execute(
            "SELECT * FROM services WHERE subdomain = ?", (service,)
        )
        svc = await cursor.fetchone()

        friend_name = None
        has_pending = False

        if friend_token:
            cursor = await db.execute(
                "SELECT * FROM friends WHERE token = ?", (friend_token,)
            )
            friend = await cursor.fetchone()
            if friend:
                friend_name = friend["name"]
                if svc:
                    cursor = await db.execute(
                        """SELECT 1 FROM access_requests
                           WHERE friend_id = ? AND service_id = ? AND status = 'pending'""",
                        (friend["id"], svc["id"])
                    )
                    has_pending = await cursor.fetchone() is not None

        return {
            "service": svc,
            "friend_name": friend_name,
            "has_pending_request": has_pending
        }
