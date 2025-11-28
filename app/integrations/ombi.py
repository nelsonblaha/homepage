"""
Ombi Integration - Auto-login via localStorage Token Injection

This integration creates Ombi users with movie/TV request permissions
and provides auto-login via JWT token injection into localStorage.

Auth Flow:
1. Friend clicks Ombi link
2. Backend authenticates to Ombi API with stored credentials
3. Receives JWT access token
4. Redirects to ombi.{domain}/blaha-auth-setup
5. Auth-setup page injects token into localStorage
6. Redirects to Ombi (now logged in)
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


class OmbiIntegration(TokenInjectionIntegration, HttpIntegrationMixin):
    """Ombi integration using token injection for auto-login."""

    SERVICE_NAME = "ombi"
    ENV_PREFIX = "OMBI"
    LOCAL_STORAGE_KEY = "id_token"

    # Database columns
    DB_USER_ID_COLUMN = "ombi_user_id"
    DB_PASSWORD_COLUMN = "ombi_password"

    @property
    def is_configured(self) -> bool:
        """Ombi requires both URL and API key."""
        return bool(self.service_url and self.api_key)

    def _get_headers(self) -> dict:
        """Get headers for Ombi API requests."""
        return {
            "ApiKey": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_user(self, username: str) -> UserResult:
        """
        Create an Ombi user with movie/TV request permissions.

        Ombi's API doesn't return the user ID on creation, so we need
        to fetch the user list to get it.
        """
        if not self.is_configured:
            return UserResult(success=False, error="Ombi not configured")

        password = self.generate_password()

        try:
            async with httpx.AsyncClient() as client:
                # Create user with request permissions
                resp = await client.post(
                    f"{self.service_url}/api/v1/Identity",
                    headers=self._get_headers(),
                    json={
                        "userName": username,
                        "password": password,
                        "claims": [
                            {"value": "RequestMovie", "enabled": True},
                            {"value": "RequestTv", "enabled": True}
                        ]
                    },
                    timeout=10.0
                )

                if resp.status_code not in (200, 201):
                    return UserResult(
                        success=False,
                        error=f"Ombi create user failed: {resp.status_code} {resp.text}"
                    )

                data = resp.json()
                user_id = data.get("id")

                # Ombi API doesn't return ID on creation, fetch it
                if not user_id:
                    users_resp = await client.get(
                        f"{self.service_url}/api/v1/Identity/Users",
                        headers=self._get_headers(),
                        timeout=10.0
                    )
                    if users_resp.status_code == 200:
                        for user in users_resp.json():
                            if user.get("userName") == username:
                                user_id = user.get("id")
                                break

                return UserResult(
                    success=True,
                    user_id=str(user_id) if user_id else None,
                    username=username,
                    password=password
                )

        except Exception as e:
            return UserResult(success=False, error=f"Ombi error: {e}")

    async def delete_user(self, user_id: str) -> bool:
        """Delete an Ombi user by ID."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.service_url}/api/v1/Identity/{user_id}",
                    headers={"ApiKey": self.api_key},
                    timeout=10.0
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Ombi delete error: {e}")
            return False

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """Authenticate to Ombi and get JWT token."""
        if not self.service_url:
            return AuthResult(success=False, error="Ombi not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.service_url}/api/v1/Token",
                    headers={"Content-Type": "application/json"},
                    json={"username": username, "password": password},
                    timeout=10.0
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return AuthResult(
                        success=True,
                        access_token=data.get("access_token")
                    )

                return AuthResult(success=False, error=f"Auth failed: {resp.status_code}")
        except Exception as e:
            return AuthResult(success=False, error=f"Ombi auth error: {e}")

    async def check_status(self) -> StatusResult:
        """Check Ombi connection status."""
        if not self.is_configured:
            return StatusResult(connected=False, error="Not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.service_url}/api/v1/Status",
                    headers={"ApiKey": self.api_key},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    return StatusResult(connected=True, server_name="Ombi")
        except Exception as e:
            return StatusResult(connected=False, error=str(e))

        return StatusResult(connected=False, error="Connection failed")


# =============================================================================
# SINGLETON INSTANCE (for registry)
# =============================================================================

ombi_integration = OmbiIntegration()


# =============================================================================
# BACKWARDS-COMPATIBLE EXPORTS
# =============================================================================
# These maintain compatibility with existing code in auth.py and accounts.py

# Export OMBI_URL for auth.py compatibility
OMBI_URL = ombi_integration.service_url


async def create_ombi_user(username: str) -> dict | None:
    """Create an Ombi user with password. Returns user info including password."""
    result = await ombi_integration.create_user(username)
    if result.success:
        return {
            "id": result.user_id,
            "username": result.username,
            "password": result.password
        }
    return None


async def delete_ombi_user(user_id: str) -> bool:
    """Delete an Ombi user by ID."""
    return await ombi_integration.delete_user(user_id)


async def authenticate_ombi(username: str, password: str) -> str | None:
    """Authenticate to Ombi and return JWT token."""
    result = await ombi_integration.authenticate(username, password)
    return result.access_token if result.success else None


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

router = APIRouter(prefix="/api/ombi", tags=["ombi"])


@router.get("/auth-setup")
async def ombi_auth_setup(access_token: str):
    """
    Serve the localStorage setup page for Ombi auto-login.

    This endpoint is accessed via ombi.{BASE_DOMAIN}/blaha-auth-setup so that
    localStorage is set on the correct domain.
    """
    auth_result = AuthResult(success=True, access_token=access_token)
    html = ombi_integration.build_auth_setup_html(auth_result)
    return HTMLResponse(content=html)


@router.get("/status")
async def ombi_status(_: bool = Depends(verify_admin)):
    """Check Ombi connection status."""
    result = await ombi_integration.check_status()
    response = {"connected": result.connected}
    if result.error:
        response["error"] = result.error
    return response
