"""
Jellyseerr Integration - Auto-login via Session Cookie Proxy

Jellyseerr is a fork of Overseerr with Jellyfin support.
It uses the same API, so this integration inherits from OverseerrIntegration.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response, RedirectResponse

from integrations.overseerr import OverseerrIntegration
from integrations.base import StatusResult
from services.session import verify_admin


class JellyseerrIntegration(OverseerrIntegration):
    """Jellyseerr integration - same API as Overseerr, different env vars."""

    SERVICE_NAME = "jellyseerr"
    ENV_PREFIX = "JELLYSEERR"
    DB_USER_ID_COLUMN = "jellyseerr_user_id"
    DB_PASSWORD_COLUMN = "jellyseerr_password"

    async def check_status(self) -> StatusResult:
        """Check Jellyseerr connection status."""
        result = await super().check_status()
        if result.connected:
            return StatusResult(connected=True, server_name="Jellyseerr")
        return result


# Singleton instance
jellyseerr_integration = JellyseerrIntegration()


# FastAPI router - minimal, delegates to integration
router = APIRouter(prefix="/api/jellyseerr", tags=["jellyseerr"])


@router.get("/auth-setup")
async def jellyseerr_auth_setup(email: str, password: str):
    """Proxy login to Jellyseerr and set session cookie."""
    if not jellyseerr_integration.service_url:
        return Response(content="Jellyseerr not configured", status_code=500)

    result = await jellyseerr_integration.authenticate(email, password)
    if not result.success:
        return Response(content=f"Auth failed: {result.error}", status_code=401)

    redirect = RedirectResponse(url=jellyseerr_integration.get_public_url(), status_code=302)
    for name, value in result.cookies.items():
        kwargs = {"key": name, "value": value, "httponly": True, "samesite": "lax"}
        if jellyseerr_integration.cookie_domain:
            kwargs["domain"] = jellyseerr_integration.cookie_domain
            kwargs["secure"] = True
        redirect.set_cookie(**kwargs)
    return redirect


@router.get("/status")
async def jellyseerr_status(_: bool = Depends(verify_admin)):
    """Check Jellyseerr connection status."""
    result = await jellyseerr_integration.check_status()
    return {"connected": result.connected, **({"error": result.error} if result.error else {})}
