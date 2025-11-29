"""Homepage - Friend access portal and service management"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db, get_db
from websocket import manager as ws_manager

# Import routers
from routes.auth import router as auth_router
from routes.services import router as services_router
from routes.friends import router as friends_router, public_router as friends_public_router
from routes.requests import router as requests_router
from routes.activity import router as activity_router
from integrations.plex import router as plex_router
from integrations.ombi import router as ombi_router
from integrations.jellyfin import router as jellyfin_router
from integrations.nextcloud import router as nextcloud_router
from integrations.overseerr import router as overseerr_router
from integrations.jellyseerr import router as jellyseerr_router
from integrations.jitsi import router as jitsi_router
from integrations.mattermost import router as mattermost_router
from routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Start background tasks
    from services.background import start_background_tasks
    background_tasks = await start_background_tasks()

    yield

    # Cancel background tasks on shutdown
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Homepage", lifespan=lifespan)

# Include all routers
app.include_router(auth_router)
app.include_router(services_router)
app.include_router(friends_router)
app.include_router(friends_public_router, prefix="/api")
app.include_router(requests_router)
app.include_router(activity_router)
app.include_router(plex_router)
app.include_router(ombi_router)
app.include_router(jellyfin_router)
app.include_router(nextcloud_router)
app.include_router(overseerr_router)
app.include_router(jellyseerr_router)
app.include_router(jitsi_router)
app.include_router(mattermost_router)
app.include_router(health_router)


# =============================================================================
# PLEX USER MANAGEMENT (additional routes using plex integration)
# =============================================================================

from fastapi import HTTPException, Depends
from services.session import verify_admin
from integrations.plex import get_plex_account, get_plex_server


@app.post("/api/friends/{friend_id}/plex-user")
async def create_plex_user_for_friend(friend_id: int, pin: str = "", _: bool = Depends(verify_admin)):
    """Create a Plex managed user for a friend."""
    account = get_plex_account()
    if not account:
        raise HTTPException(status_code=400, detail="Plex not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()

        if not friend:
            raise HTTPException(status_code=404, detail="Friend not found")

        if friend.get("plex_user_id"):
            raise HTTPException(status_code=400, detail="Friend already has Plex user")

        try:
            plex_user = account.createHomeUser(friend["name"], server=get_plex_server())

            if pin:
                plex_user.updatePin(pin)

            await db.execute(
                "UPDATE friends SET plex_user_id = ?, plex_pin = ? WHERE id = ?",
                (str(plex_user.id), pin, friend_id)
            )
            await db.commit()

            return {
                "status": "ok",
                "plex_user_id": str(plex_user.id),
                "plex_username": plex_user.title
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create Plex user: {str(e)}")


@app.delete("/api/friends/{friend_id}/plex-user")
async def remove_plex_user_for_friend(friend_id: int, delete_from_plex: bool = False, _: bool = Depends(verify_admin)):
    """Remove Plex managed user association, optionally delete from Plex too."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        if delete_from_plex:
            cursor = await db.execute("SELECT plex_user_id FROM friends WHERE id = ?", (friend_id,))
            friend = await cursor.fetchone()
            if friend and friend.get("plex_user_id"):
                account = get_plex_account()
                if account:
                    try:
                        for user in account.users():
                            if str(user.id) == friend["plex_user_id"]:
                                user.delete()
                                break
                    except Exception as e:
                        print(f"Failed to delete Plex user: {e}")

        await db.execute(
            "UPDATE friends SET plex_user_id = '', plex_pin = '' WHERE id = ?",
            (friend_id,)
        )
        await db.commit()
        return {"status": "ok"}


@app.put("/api/friends/{friend_id}/plex-pin")
async def update_plex_pin(friend_id: int, pin: str, _: bool = Depends(verify_admin)):
    """Update Plex PIN for a friend."""
    account = get_plex_account()
    if not account:
        raise HTTPException(status_code=400, detail="Plex not configured")

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM friends WHERE id = ?", (friend_id,))
        friend = await cursor.fetchone()

        if not friend or not friend.get("plex_user_id"):
            raise HTTPException(status_code=404, detail="Friend has no Plex user")

        try:
            for user in account.users():
                if str(user.id) == friend["plex_user_id"]:
                    if pin:
                        user.updatePin(pin)
                    else:
                        user.removePin()
                    break

            await db.execute(
                "UPDATE friends SET plex_pin = ? WHERE id = ?",
                (pin, friend_id)
            )
            await db.commit()
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """WebSocket endpoint for real-time updates.

    Connect without token for admin view, or with friend token for friend view.
    """
    # Validate friend token if provided
    if token:
        async with await get_db() as db:
            cursor = await db.execute(
                "SELECT id FROM friends WHERE token = ?", (token,)
            )
            friend = await cursor.fetchone()
            if not friend:
                await websocket.close(code=4001, reason="Invalid token")
                return

    await ws_manager.connect(websocket, token)
    try:
        while True:
            # Keep connection alive, handle any client messages
            data = await websocket.receive_text()
            # Currently we don't expect client messages, but could add ping/pong
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, token)


# =============================================================================
# STATIC FILES & ROUTES
# =============================================================================

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/admin")
async def admin_page():
    return FileResponse("static/index.html")


@app.get("/admin/{path:path}")
async def admin_subpage(path: str):
    return FileResponse("static/index.html")


@app.get("/request-access")
async def request_access_page():
    return FileResponse("static/index.html")


@app.get("/f/{token}")
async def friend_page(token: str, response: Response):
    # Validate token exists before setting cookie
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM friends WHERE token = ?", (token,)
        )
        friend = await cursor.fetchone()
        if not friend:
            raise HTTPException(status_code=404, detail="Invalid link")

    # Set cookie for SSO across subdomains
    import os
    cookie_domain = os.environ.get("COOKIE_DOMAIN", "")
    cookie_kwargs = {
        "key": "friend_token",
        "value": token,
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "max_age": 86400 * 30
    }
    if cookie_domain and cookie_domain != "localhost":
        cookie_kwargs["domain"] = cookie_domain
    response.set_cookie(**cookie_kwargs)
    return FileResponse("static/index.html")


# Mount static files last to avoid overriding API routes
app.mount("/static", StaticFiles(directory="static"), name="static")
