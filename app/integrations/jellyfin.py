"""
Jellyfin Integration - Auto-login via localStorage Token Injection

This integration creates Jellyfin users and provides auto-login via
a credentials object injected into localStorage.

Auth Flow:
1. Friend clicks Jellyfin link
2. Backend authenticates to Jellyfin API with stored credentials
3. Receives access token, user ID, and server ID
4. Redirects to jellyfin.{domain}/blaha-auth-setup
5. Auth-setup page injects credentials object into localStorage
6. Redirects to Jellyfin (now logged in)

Note: Jellyfin requires a more complex localStorage structure than Ombi,
storing server info along with the access token.
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from integrations.base import (
    TokenInjectionIntegration,
    UserResult,
    AuthResult,
    StatusResult,
    HttpIntegrationMixin,
)
from services.session import verify_admin


class JellyfinIntegration(TokenInjectionIntegration, HttpIntegrationMixin):
    """Jellyfin integration using token injection for auto-login."""

    SERVICE_NAME = "jellyfin"
    ENV_PREFIX = "JELLYFIN"
    LOCAL_STORAGE_KEY = "jellyfin_credentials"

    # Database columns
    DB_USER_ID_COLUMN = "jellyfin_user_id"
    DB_PASSWORD_COLUMN = "jellyfin_password"

    # Jellyfin-specific: auth header name
    AUTH_HEADER_NAME = "X-Emby-Token"

    @property
    def is_configured(self) -> bool:
        """Jellyfin requires both URL and API key."""
        return bool(self.service_url and self.api_key)

    def _get_headers(self) -> dict:
        """Get headers for Jellyfin API requests."""
        return {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_user(self, username: str) -> UserResult:
        """
        Create a Jellyfin user.

        Jellyfin creates users without a password, so we set one after creation.
        """
        if not self.is_configured:
            return UserResult(success=False, error="Jellyfin not configured")

        try:
            async with httpx.AsyncClient() as client:
                # Create user
                resp = await client.post(
                    f"{self.service_url}/Users/New",
                    headers=self._get_headers(),
                    json={"Name": username},
                    timeout=10.0
                )

                if resp.status_code not in (200, 201):
                    return UserResult(
                        success=False,
                        error=f"Jellyfin create user failed: {resp.status_code} {resp.text}"
                    )

                data = resp.json()
                user_id = data.get("Id")

                # Set password
                password = self.generate_password()
                pwd_resp = await client.post(
                    f"{self.service_url}/Users/{user_id}/Password",
                    headers=self._get_headers(),
                    json={"NewPw": password},
                    timeout=10.0
                )

                if pwd_resp.status_code not in (200, 204):
                    print(f"Jellyfin set password failed: {pwd_resp.status_code}")
                    # Continue anyway - user was created

                return UserResult(
                    success=True,
                    user_id=user_id,
                    username=data.get("Name"),
                    password=password
                )

        except Exception as e:
            return UserResult(success=False, error=f"Jellyfin error: {e}")

    async def delete_user(self, user_id: str) -> bool:
        """Delete a Jellyfin user by ID."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.service_url}/Users/{user_id}",
                    headers={"X-Emby-Token": self.api_key},
                    timeout=10.0
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Jellyfin delete error: {e}")
            return False

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Authenticate to Jellyfin and get access token + server info.

        Jellyfin requires additional info (user_id, server_id) for auto-login.
        """
        if not self.service_url:
            return AuthResult(success=False, error="Jellyfin not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.service_url}/Users/AuthenticateByName",
                    headers={
                        "Content-Type": "application/json",
                        "X-Emby-Authorization": f'MediaBrowser Client="{self.base_domain}", Device="Web", DeviceId="blaha-auto-login", Version="1.0"'
                    },
                    json={"Username": username, "Pw": password},
                    timeout=10.0
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return AuthResult(
                        success=True,
                        access_token=data.get("AccessToken"),
                        user_id=data.get("User", {}).get("Id"),
                        extra={
                            "server_id": data.get("ServerId")
                        }
                    )

                return AuthResult(success=False, error=f"Auth failed: {resp.status_code}")
        except Exception as e:
            return AuthResult(success=False, error=f"Jellyfin auth error: {e}")

    async def check_status(self) -> StatusResult:
        """Check Jellyfin connection status."""
        if not self.is_configured:
            return StatusResult(connected=False, error="Not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.service_url}/System/Info",
                    headers={"X-Emby-Token": self.api_key},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return StatusResult(
                        connected=True,
                        server_name=data.get("ServerName", "Jellyfin")
                    )
        except Exception as e:
            return StatusResult(connected=False, error=str(e))

        return StatusResult(connected=False, error="Connection failed")

    def build_auth_setup_html(self, auth_result: AuthResult) -> str:
        """
        Build HTML that injects Jellyfin credentials into localStorage.

        Jellyfin requires a complex credentials object with server info.
        """
        jellyfin_base = self.get_public_url()
        server_id = auth_result.extra.get("server_id", "")

        return f"""<!DOCTYPE html>
<html>
<head><title>Signing into Jellyfin...</title></head>
<body style="background:#101010;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>Signing into Jellyfin...</h2>
<script>
const credentials = {{
    Servers: [{{
        Id: "{server_id}",
        Name: "Jellyfin",
        LocalAddress: "{self.service_url}",
        ManualAddress: "{jellyfin_base}",
        AccessToken: "{auth_result.access_token}",
        UserId: "{auth_result.user_id}",
        DateLastAccessed: Date.now()
    }}]
}};
localStorage.setItem('{self.LOCAL_STORAGE_KEY}', JSON.stringify(credentials));
window.location.href = '{jellyfin_base}/web/index.html#!/home.html';
</script>
<noscript>JavaScript is required. <a href="{jellyfin_base}">Go to Jellyfin</a></noscript>
</div>
</body>
</html>"""


# =============================================================================
# SINGLETON INSTANCE (for registry)
# =============================================================================

jellyfin_integration = JellyfinIntegration()


# =============================================================================
# BACKWARDS-COMPATIBLE FUNCTIONS
# =============================================================================

async def create_jellyfin_user(username: str) -> dict | None:
    """Create a Jellyfin user with a password. Returns user info or None on failure."""
    result = await jellyfin_integration.create_user(username)
    if result.success:
        return {
            "id": result.user_id,
            "username": result.username,
            "password": result.password
        }
    return None


async def delete_jellyfin_user(user_id: str) -> bool:
    """Delete a Jellyfin user by ID."""
    return await jellyfin_integration.delete_user(user_id)


async def authenticate_jellyfin(username: str, password: str) -> dict | None:
    """Authenticate to Jellyfin and return token info."""
    result = await jellyfin_integration.authenticate(username, password)
    if result.success:
        return {
            "access_token": result.access_token,
            "user_id": result.user_id,
            "server_id": result.extra.get("server_id")
        }
    return None


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

router = APIRouter(prefix="/api/jellyfin", tags=["jellyfin"])


@router.get("/auth-setup")
async def jellyfin_auth_setup(access_token: str, user_id: str, server_id: str):
    """
    Serve the localStorage setup page for Jellyfin auto-login.

    This endpoint is accessed via jellyfin.{BASE_DOMAIN}/blaha-auth-setup so that
    localStorage is set on the correct domain.
    """
    auth_result = AuthResult(
        success=True,
        access_token=access_token,
        user_id=user_id,
        extra={"server_id": server_id}
    )
    html = jellyfin_integration.build_auth_setup_html(auth_result)
    return HTMLResponse(content=html)


@router.get("/status")
async def jellyfin_status(_: bool = Depends(verify_admin)):
    """Check Jellyfin connection status."""
    result = await jellyfin_integration.check_status()
    response = {"connected": result.connected}
    if result.server_name:
        response["serverName"] = result.server_name
    if result.error:
        response["error"] = result.error
    return response
