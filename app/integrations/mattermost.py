"""
Mattermost Integration - Auto-login via Session Cookie Proxy

This integration creates Mattermost users and adds them to a team,
providing auto-login by capturing the session token and setting it
as a cookie.

Auth Flow:
1. Friend clicks Mattermost link
2. Backend proxies login to Mattermost API
3. Captures MMAUTHTOKEN from response header
4. Sets cookie on your domain
5. Redirects to Mattermost (cookie authenticates)

Note: Mattermost uses a header token (not a cookie) in the login response,
which we convert to a cookie for browser-based auth.
"""

import os
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


class MattermostIntegration(CookieProxyIntegration, HttpIntegrationMixin):
    """Mattermost integration using cookie proxy for auto-login."""

    SERVICE_NAME = "mattermost"
    ENV_PREFIX = "MATTERMOST"
    COOKIE_NAME = "MMAUTHTOKEN"

    # Database columns
    DB_USER_ID_COLUMN = "mattermost_user_id"
    DB_PASSWORD_COLUMN = "mattermost_password"

    @property
    def team_id(self) -> str:
        """Get the Mattermost team ID."""
        return os.environ.get("MATTERMOST_TEAM_ID", "")

    @property
    def token(self) -> str:
        """Get the admin token (Mattermost uses MATTERMOST_TOKEN, not API_KEY)."""
        return os.environ.get("MATTERMOST_TOKEN", "")

    @property
    def is_configured(self) -> bool:
        """Mattermost requires URL and token."""
        return bool(self.service_url and self.token)

    def _get_headers(self) -> dict:
        """Get headers for Mattermost API requests."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_public_url(self) -> str:
        """Mattermost uses 'chat' subdomain by convention."""
        return f"https://chat.{self.base_domain}"

    async def create_user(self, username: str) -> UserResult:
        """
        Create a Mattermost user and add to team.

        Mattermost usernames must be lowercase alphanumeric + underscores.
        """
        if not self.is_configured:
            return UserResult(success=False, error="Mattermost not configured")

        password = self.generate_password()
        email = self.generate_email(username)
        # Mattermost requires lowercase alphanumeric usernames
        mm_username = self.sanitize_username(username)

        try:
            async with httpx.AsyncClient() as client:
                # Create user
                resp = await client.post(
                    f"{self.service_url}/api/v4/users",
                    headers=self._get_headers(),
                    json={
                        "email": email,
                        "username": mm_username,
                        "password": password,
                        "nickname": username  # Original name as display name
                    },
                    timeout=10.0
                )

                if resp.status_code not in (200, 201):
                    return UserResult(
                        success=False,
                        error=f"Mattermost create user failed: {resp.status_code} {resp.text}"
                    )

                data = resp.json()
                user_id = data.get("id")

                # Add user to team
                if self.team_id:
                    team_resp = await client.post(
                        f"{self.service_url}/api/v4/teams/{self.team_id}/members",
                        headers=self._get_headers(),
                        json={"team_id": self.team_id, "user_id": user_id},
                        timeout=10.0
                    )
                    if team_resp.status_code not in (200, 201):
                        print(f"Mattermost add to team failed: {team_resp.status_code}")

                return UserResult(
                    success=True,
                    user_id=user_id,
                    username=mm_username,
                    email=email,
                    password=password
                )

        except Exception as e:
            return UserResult(success=False, error=f"Mattermost error: {e}")

    async def delete_user(self, user_id: str) -> bool:
        """Delete a Mattermost user by ID."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"{self.service_url}/api/v4/users/{user_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=10.0
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            print(f"Mattermost delete error: {e}")
            return False

    async def authenticate(self, email: str, password: str) -> AuthResult:
        """
        Authenticate to Mattermost and get session token.

        Mattermost returns the token in a response header, not a cookie.
        """
        if not self.service_url:
            return AuthResult(success=False, error="Mattermost not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.service_url}/api/v4/users/login",
                    json={"login_id": email, "password": password},
                    timeout=10.0
                )

                if resp.status_code == 200:
                    token = resp.headers.get("Token")
                    return AuthResult(
                        success=True,
                        access_token=token,
                        # Store as cookie for the proxy flow
                        cookies={self.COOKIE_NAME: token}
                    )

                return AuthResult(success=False, error=f"Auth failed: {resp.status_code}")
        except Exception as e:
            return AuthResult(success=False, error=f"Mattermost auth error: {e}")

    async def check_status(self) -> StatusResult:
        """Check Mattermost connection status."""
        if not self.is_configured:
            return StatusResult(connected=False, error="Not configured")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.service_url}/api/v4/system/ping",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    return StatusResult(connected=True, server_name="Mattermost")
        except Exception as e:
            return StatusResult(connected=False, error=str(e))

        return StatusResult(connected=False, error="Connection failed")


# =============================================================================
# SINGLETON INSTANCE (for registry)
# =============================================================================

mattermost_integration = MattermostIntegration()


# =============================================================================
# BACKWARDS-COMPATIBLE FUNCTIONS
# =============================================================================

async def create_mattermost_user(username: str) -> dict | None:
    """Create a Mattermost user. Returns user info including password."""
    result = await mattermost_integration.create_user(username)
    if result.success:
        return {
            "id": result.user_id,
            "username": result.username,
            "email": result.email,
            "password": result.password
        }
    return None


async def delete_mattermost_user(user_id: str) -> bool:
    """Delete a Mattermost user by ID."""
    return await mattermost_integration.delete_user(user_id)


async def authenticate_mattermost(email: str, password: str) -> dict | None:
    """Authenticate to Mattermost and return session token."""
    result = await mattermost_integration.authenticate(email, password)
    if result.success:
        return {"success": True, "token": result.access_token}
    return None


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

router = APIRouter(prefix="/api/mattermost", tags=["mattermost"])


@router.get("/auth-setup")
async def mattermost_auth_setup(email: str, password: str):
    """
    Log into Mattermost and redirect with session cookie.

    This endpoint proxies the login and sets the MMAUTHTOKEN cookie.
    """
    if not mattermost_integration.service_url:
        return Response(content="Mattermost not configured", status_code=500)

    result = await mattermost_integration.authenticate(email, password)

    if not result.success:
        return Response(content=f"Auth failed: {result.error}", status_code=401)

    # Create redirect response and set cookie
    redirect_url = mattermost_integration.get_public_url()
    redirect = RedirectResponse(url=redirect_url, status_code=302)

    cookie_kwargs = {
        "key": mattermost_integration.COOKIE_NAME,
        "value": result.access_token,
        "httponly": True,
        "samesite": "lax"
    }
    if mattermost_integration.cookie_domain:
        cookie_kwargs["domain"] = mattermost_integration.cookie_domain
        cookie_kwargs["secure"] = True
    redirect.set_cookie(**cookie_kwargs)

    return redirect


@router.get("/status")
async def mattermost_status(_: bool = Depends(verify_admin)):
    """Check Mattermost connection status."""
    result = await mattermost_integration.check_status()
    response = {"connected": result.connected}
    if result.error:
        response["error"] = result.error
    return response
