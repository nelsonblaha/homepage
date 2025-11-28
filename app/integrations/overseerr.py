"""
Overseerr Integration - Auto-login via Session Cookie Proxy

This integration creates Overseerr local users with request permissions
and provides auto-login by proxying the login request and setting
the session cookie on your domain.

Auth Flow:
1. Friend clicks Overseerr link
2. Backend proxies login to Overseerr API
3. Captures session cookie from response
4. Sets cookie on your domain (with proper COOKIE_DOMAIN)
5. Redirects to Overseerr (cookie authenticates)
"""

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response, RedirectResponse

from integrations.base import (
    CookieProxyIntegration,
    UserResult,
    AuthResult,
    StatusResult,
    HttpIntegrationMixin,
)
from services.session import verify_admin


class OverseerrIntegration(CookieProxyIntegration, HttpIntegrationMixin):
    """Overseerr integration using cookie proxy for auto-login."""

    SERVICE_NAME = "overseerr"
    ENV_PREFIX = "OVERSEERR"
    COOKIE_NAME = "connect.sid"

    # Database columns
    DB_USER_ID_COLUMN = "overseerr_user_id"
    DB_PASSWORD_COLUMN = "overseerr_password"

    @property
    def is_configured(self) -> bool:
        """Overseerr requires both URL and API key."""
        return bool(self.service_url and self.api_key)

    def _get_headers(self) -> dict:
        """Get headers for Overseerr API requests."""
        return {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_user(self, username: str) -> UserResult:
        """
        Create an Overseerr local user with request + auto-approve permissions.

        Overseerr permissions are bit flags:
        - 2 = REQUEST
        - 32 = AUTO_APPROVE
        - 34 = REQUEST + AUTO_APPROVE
        """
        if not self.is_configured:
            return UserResult(success=False, error="Overseerr not configured")

        password = self.generate_password()
        email = self.generate_email(username)

        try:
            async with httpx.AsyncClient() as client:
                # Create user
                resp = await client.post(
                    f"{self.service_url}/api/v1/user",
                    headers=self._get_headers(),
                    json={
                        "email": email,
                        "username": username,
                        "permissions": 34  # REQUEST + AUTO_APPROVE
                    },
                    timeout=10.0
                )

                if resp.status_code not in (200, 201):
                    return UserResult(
                        success=False,
                        error=f"Overseerr create user failed: {resp.status_code} {resp.text}"
                    )

                data = resp.json()
                user_id = data.get("id")

                # Set password
                pwd_resp = await client.post(
                    f"{self.service_url}/api/v1/user/{user_id}/settings/password",
                    headers=self._get_headers(),
                    json={"newPassword": password},
                    timeout=10.0
                )

                if pwd_resp.status_code not in (200, 204):
                    print(f"Overseerr set password failed: {pwd_resp.status_code} {pwd_resp.text}")
                    # User created but password failed
                    return UserResult(
                        success=True,
                        user_id=str(user_id),
                        username=username,
                        email=email,
                        password=""
                    )

                return UserResult(
                    success=True,
                    user_id=str(user_id),
                    username=username,
                    email=email,
                    password=password
                )

        except Exception as e:
            return UserResult(success=False, error=f"Overseerr error: {e}")

    async def delete_user(self, user_id: str) -> bool:
        """Delete an Overseerr user by ID."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.service_url}/api/v1/user/{user_id}",
                    headers={"X-Api-Key": self.api_key},
                    timeout=10.0
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Overseerr delete error: {e}")
            return False

    async def authenticate(self, email: str, password: str) -> AuthResult:
        """
        Authenticate to Overseerr and capture session cookie.

        Note: Overseerr uses email for login, not username.
        """
        if not self.service_url:
            return AuthResult(success=False, error="Overseerr not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.service_url}/api/v1/auth/local",
                    json={"email": email, "password": password},
                    timeout=10.0
                )

                if resp.status_code == 200:
                    return AuthResult(
                        success=True,
                        cookies=dict(resp.cookies)
                    )

                return AuthResult(success=False, error=f"Auth failed: {resp.status_code}")
        except Exception as e:
            return AuthResult(success=False, error=f"Overseerr auth error: {e}")

    async def check_status(self) -> StatusResult:
        """Check Overseerr connection status."""
        if not self.is_configured:
            return StatusResult(connected=False, error="Not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.service_url}/api/v1/status",
                    headers={"X-Api-Key": self.api_key},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    return StatusResult(connected=True, server_name="Overseerr")
        except Exception as e:
            return StatusResult(connected=False, error=str(e))

        return StatusResult(connected=False, error="Connection failed")


# =============================================================================
# SINGLETON INSTANCE (for registry)
# =============================================================================

overseerr_integration = OverseerrIntegration()


# =============================================================================
# BACKWARDS-COMPATIBLE FUNCTIONS
# =============================================================================

async def create_overseerr_user(username: str) -> dict | None:
    """Create an Overseerr local user with password. Returns user info including password."""
    result = await overseerr_integration.create_user(username)
    if result.success:
        return {
            "id": result.user_id,
            "username": result.username,
            "email": result.email,
            "password": result.password
        }
    return None


async def delete_overseerr_user(user_id: str) -> bool:
    """Delete an Overseerr user by ID."""
    return await overseerr_integration.delete_user(user_id)


async def authenticate_overseerr(email: str, password: str) -> dict | None:
    """Authenticate to Overseerr and return session cookie."""
    result = await overseerr_integration.authenticate(email, password)
    if result.success:
        return {
            "success": True,
            "cookies": result.cookies
        }
    return None


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

router = APIRouter(prefix="/api/overseerr", tags=["overseerr"])


@router.get("/auth-setup")
async def overseerr_auth_setup(email: str, password: str):
    """
    Proxy login to Overseerr and set session cookie.

    This endpoint should be accessed via overseerr.{BASE_DOMAIN}/blaha-auth-setup
    so the cookie is set on the correct domain.
    """
    if not overseerr_integration.service_url:
        return Response(content="Overseerr not configured", status_code=500)

    result = await overseerr_integration.authenticate(email, password)

    if not result.success:
        return Response(content=f"Auth failed: {result.error}", status_code=401)

    # Create redirect response and set cookies
    redirect_url = overseerr_integration.get_public_url()
    redirect = RedirectResponse(url=redirect_url, status_code=302)

    for cookie_name, cookie_value in result.cookies.items():
        cookie_kwargs = {
            "key": cookie_name,
            "value": cookie_value,
            "httponly": True,
            "samesite": "lax"
        }
        # Only set domain and secure for non-localhost
        if overseerr_integration.cookie_domain:
            cookie_kwargs["domain"] = overseerr_integration.cookie_domain
            cookie_kwargs["secure"] = True
        redirect.set_cookie(**cookie_kwargs)

    return redirect


@router.get("/status")
async def overseerr_status(_: bool = Depends(verify_admin)):
    """Check Overseerr connection status."""
    result = await overseerr_integration.check_status()
    response = {"connected": result.connected}
    if result.error:
        response["error"] = result.error
    return response
