"""Service management routes - CRUD for services"""
import os
from fastapi import APIRouter, HTTPException, Depends

from database import get_db
from models import Service, ServiceCreate
from services.session import verify_admin
from integrations.registry import SERVICE_DB_COLUMNS, get_integration

BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "admin")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")

# Map service names to their integration slugs
SERVICE_NAME_TO_SLUG = {
    "plex": "plex",
    "ombi": "ombi",
    "jellyfin": "jellyfin",
    "nextcloud": "nextcloud",
    "overseerr": "overseerr",
    "mattermost": "mattermost",
    "chat": "mattermost",
}

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
            """INSERT INTO services (name, url, icon, description, display_order, subdomain, stack, is_default, auth_type, github_repo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0, service.auth_type, service.github_repo)
        )
        await db.commit()
        return Service(id=cursor.lastrowid, **service.model_dump())


@router.put("/{service_id}", response_model=Service)
async def update_service(service_id: int, service: ServiceCreate, _: bool = Depends(verify_admin)):
    async with await get_db() as db:
        await db.execute(
            """UPDATE services SET name=?, url=?, icon=?, description=?, display_order=?,
               subdomain=?, stack=?, is_default=?, auth_type=?, github_repo=? WHERE id=?""",
            (service.name, service.url, service.icon, service.description, service.display_order,
             service.subdomain, service.stack, 1 if service.is_default else 0, service.auth_type, service.github_repo, service_id)
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


@router.post("/{service_id}/toggle-visibility")
async def toggle_service_visibility(service_id: int, _: bool = Depends(verify_admin)):
    """Toggle whether a service is visible for assignment to friends."""
    async with await get_db() as db:
        cursor = await db.execute("SELECT visible_to_friends FROM services WHERE id = ?", (service_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Service not found")

        new_value = 0 if row[0] else 1
        await db.execute("UPDATE services SET visible_to_friends = ? WHERE id = ?", (new_value, service_id))
        await db.commit()
        return {"status": "ok", "visible_to_friends": bool(new_value)}


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
        preauth_url = f"https://{user}:{passwd}@{service['subdomain']}.{BASE_DOMAIN}/"

        return {"url": preauth_url, "service": service["name"]}


@router.get("/{service_id}/integration-status")
async def get_integration_status(service_id: int, _: bool = Depends(verify_admin)):
    """Get integration status for a managed service (Plex, Ombi, Jellyfin, etc.)."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        service = await cursor.fetchone()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        service_slug = SERVICE_NAME_TO_SLUG.get(service["name"].lower())
        if not service_slug:
            return {"managed": False}

        # Get db columns for this service
        columns = SERVICE_DB_COLUMNS.get(service_slug)
        if not columns:
            return {"managed": False}

        user_id_col = columns[0]

        # Count friends with accounts for this service
        cursor = await db.execute(
            f"""SELECT COUNT(*) as count FROM friends
               WHERE {user_id_col} IS NOT NULL AND {user_id_col} != ''"""
        )
        account_count = (await cursor.fetchone())["count"]

        # Count friends granted access to this service
        cursor = await db.execute(
            """SELECT COUNT(*) as count FROM friend_services WHERE service_id = ?""",
            (service_id,)
        )
        granted_count = (await cursor.fetchone())["count"]

        # Check if integration is connected (has status endpoint)
        integration = get_integration(service_slug)
        connected = False
        if integration and hasattr(integration, "check_status"):
            try:
                status = await integration.check_status()
                connected = status.get("connected", False)
            except Exception:
                connected = False

        return {
            "managed": True,
            "slug": service_slug,
            "connected": connected,
            "accounts_created": account_count,
            "friends_granted": granted_count,
        }


@router.get("/integrations-summary")
async def get_integrations_summary(_: bool = Depends(verify_admin)):
    """Get summary of all managed service integrations."""
    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

        summary = {}
        for slug, columns in SERVICE_DB_COLUMNS.items():
            if slug == "chat":  # Skip alias
                continue

            user_id_col = columns[0]

            # Count friends with accounts
            cursor = await db.execute(
                f"""SELECT COUNT(*) as count FROM friends
                   WHERE {user_id_col} IS NOT NULL AND {user_id_col} != ''"""
            )
            account_count = (await cursor.fetchone())["count"]

            # Check if integration is connected
            integration = get_integration(slug)
            connected = False
            if integration and hasattr(integration, "check_status"):
                try:
                    status = await integration.check_status()
                    connected = status.get("connected", False)
                except Exception:
                    connected = False

            summary[slug] = {
                "connected": connected,
                "accounts_created": account_count,
            }

        return summary


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


@router.get("/ci-status")
async def get_ci_status(_: bool = Depends(verify_admin)):
    """Get GitHub Actions CI status for all services with github_repo configured."""
    import httpx

    async with await get_db() as db:
        db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cursor = await db.execute(
            "SELECT id, name, github_repo FROM services WHERE github_repo IS NOT NULL AND github_repo != ''"
        )
        services = await cursor.fetchall()

    results = {}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        for service in services:
            repo = service["github_repo"]
            try:
                # Fetch latest workflow run from GitHub API
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/actions/runs",
                    params={"per_page": 1, "branch": "main"},
                    headers=headers
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("workflow_runs"):
                        run = data["workflow_runs"][0]
                        results[service["id"]] = {
                            "status": run.get("status"),  # queued, in_progress, completed
                            "conclusion": run.get("conclusion"),  # success, failure, cancelled, etc.
                            "url": run.get("html_url"),
                            "created_at": run.get("created_at"),
                        }
                    else:
                        results[service["id"]] = {"status": "no_runs", "conclusion": None, "url": None}
                else:
                    # Try master branch if main fails
                    resp = await client.get(
                        f"https://api.github.com/repos/{repo}/actions/runs",
                        params={"per_page": 1, "branch": "master"},
                        headers=headers
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("workflow_runs"):
                            run = data["workflow_runs"][0]
                            results[service["id"]] = {
                                "status": run.get("status"),
                                "conclusion": run.get("conclusion"),
                                "url": run.get("html_url"),
                                "created_at": run.get("created_at"),
                            }
                        else:
                            results[service["id"]] = {"status": "no_runs", "conclusion": None, "url": None}
                    else:
                        results[service["id"]] = {"status": "error", "conclusion": None, "url": None}
            except Exception:
                results[service["id"]] = {"status": "error", "conclusion": None, "url": None}

    return results
