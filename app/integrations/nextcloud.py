"""
Nextcloud Integration - Credential Display Authentication

This integration creates Nextcloud users via the OCS API and displays
the credentials to the user for manual login.

Auth Flow:
1. Friend clicks Nextcloud link
2. Credentials are displayed in a modal/page
3. User copies credentials and logs in manually

Note: Nextcloud's session auth requires CSRF tokens which makes auto-login
complex. Displaying credentials is simpler and more reliable.
"""

import os
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
import xml.etree.ElementTree as ET

from integrations.base import (
    CredentialDisplayIntegration,
    UserResult,
    AuthResult,
    StatusResult,
    HttpIntegrationMixin,
)
from services.session import verify_admin


class NextcloudIntegration(CredentialDisplayIntegration, HttpIntegrationMixin):
    """Nextcloud integration using credential display."""

    SERVICE_NAME = "nextcloud"
    ENV_PREFIX = "NEXTCLOUD"

    # Database columns
    DB_USER_ID_COLUMN = "nextcloud_user_id"
    DB_PASSWORD_COLUMN = "nextcloud_password"

    @property
    def admin_user(self) -> str:
        """Get the Nextcloud admin username."""
        return os.environ.get("NEXTCLOUD_ADMIN_USER", "admin")

    @property
    def admin_pass(self) -> str:
        """Get the Nextcloud admin password."""
        return os.environ.get("NEXTCLOUD_ADMIN_PASS", "")

    @property
    def host_header(self) -> str:
        """Get the Host header for Nextcloud requests."""
        return os.environ.get("NEXTCLOUD_HOST", f"nextcloud.{self.base_domain}")

    @property
    def is_configured(self) -> bool:
        """Nextcloud requires URL and admin credentials."""
        return bool(self.service_url and self.admin_pass)

    def _get_auth(self) -> tuple[str, str]:
        """Get basic auth credentials."""
        return (self.admin_user, self.admin_pass)

    def _get_headers(self) -> dict:
        """Get headers for Nextcloud OCS API requests."""
        return {
            "OCS-APIRequest": "true",
            "Host": self.host_header
        }

    def _parse_ocs_response(self, response_text: str) -> tuple[bool, str]:
        """
        Parse OCS API XML response.

        Returns (success, message).
        """
        try:
            root = ET.fromstring(response_text)
            status_code = root.find(".//statuscode")
            if status_code is not None and status_code.text == "100":
                return True, "OK"

            message = root.find(".//message")
            return False, message.text if message is not None else "Unknown error"
        except ET.ParseError:
            return False, "Invalid XML response"

    async def create_user(self, username: str) -> UserResult:
        """
        Create a Nextcloud user via OCS API.

        Note: Nextcloud uses username as the user ID.
        """
        if not self.is_configured:
            return UserResult(success=False, error="Nextcloud not configured")

        password = self.generate_password()

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    f"{self.service_url}/ocs/v1.php/cloud/users",
                    auth=self._get_auth(),
                    headers={
                        **self._get_headers(),
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    data={
                        "userid": username,
                        "password": password
                    },
                    timeout=15.0
                )

                if resp.status_code != 200:
                    return UserResult(
                        success=False,
                        error=f"Nextcloud create user failed: {resp.status_code}"
                    )

                success, message = self._parse_ocs_response(resp.text)
                if success:
                    return UserResult(
                        success=True,
                        user_id=username,  # Nextcloud uses username as ID
                        username=username,
                        password=password
                    )

                return UserResult(success=False, error=f"Nextcloud error: {message}")

        except Exception as e:
            return UserResult(success=False, error=f"Nextcloud error: {e}")

    async def delete_user(self, user_id: str) -> bool:
        """Delete a Nextcloud user by username/ID."""
        if not self.is_configured:
            return False

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.delete(
                    f"{self.service_url}/ocs/v1.php/cloud/users/{user_id}",
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    timeout=10.0
                )

                if resp.status_code == 200:
                    success, _ = self._parse_ocs_response(resp.text)
                    return success
        except Exception as e:
            print(f"Nextcloud delete error: {e}")

        return False

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Verify Nextcloud credentials are valid.

        We don't actually use this for auto-login, just validation.
        """
        if not self.service_url:
            return AuthResult(success=False, error="Nextcloud not configured")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(
                    f"{self.service_url}/ocs/v1.php/cloud/capabilities",
                    auth=(username, password),
                    headers=self._get_headers(),
                    timeout=10.0
                )

                if resp.status_code == 200:
                    return AuthResult(
                        success=True,
                        extra={"username": username, "password": password, "valid": True}
                    )

                return AuthResult(success=False, error="Invalid credentials")
        except Exception as e:
            return AuthResult(success=False, error=f"Nextcloud auth error: {e}")

    async def check_status(self) -> StatusResult:
        """Check Nextcloud connection status."""
        if not self.is_configured:
            return StatusResult(connected=False, error="Not configured")

        try:
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.get(
                    f"{self.service_url}/ocs/v1.php/cloud/capabilities",
                    auth=self._get_auth(),
                    headers=self._get_headers(),
                    timeout=5.0
                )
                if resp.status_code == 200:
                    return StatusResult(connected=True, server_name="Nextcloud")
        except Exception as e:
            return StatusResult(connected=False, error=str(e))

        return StatusResult(connected=False, error="Connection failed")


# =============================================================================
# SINGLETON INSTANCE (for registry)
# =============================================================================

nextcloud_integration = NextcloudIntegration()


# =============================================================================
# BACKWARDS-COMPATIBLE FUNCTIONS
# =============================================================================

async def create_nextcloud_user(username: str) -> dict | None:
    """Create a Nextcloud user with a password. Returns user info or None on failure."""
    result = await nextcloud_integration.create_user(username)
    if result.success:
        return {
            "id": result.user_id,
            "username": result.username,
            "password": result.password
        }
    return None


async def delete_nextcloud_user(user_id: str) -> bool:
    """Delete a Nextcloud user by username/ID."""
    return await nextcloud_integration.delete_user(user_id)


async def authenticate_nextcloud(username: str, password: str) -> dict | None:
    """Authenticate to Nextcloud and return login flow token."""
    result = await nextcloud_integration.authenticate(username, password)
    if result.success:
        return {
            "username": username,
            "password": password,
            "valid": True
        }
    return None


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

router = APIRouter(prefix="/api/nextcloud", tags=["nextcloud"])


@router.get("/auth-setup")
async def nextcloud_auth_setup(username: str, password: str):
    """
    Display Nextcloud credentials for manual login.

    Since Nextcloud uses session-based auth with CSRF, we show credentials
    rather than attempting auto-login.
    """
    html = nextcloud_integration.build_credentials_display_html(username, password)
    return HTMLResponse(content=html)


@router.get("/status")
async def nextcloud_status(_: bool = Depends(verify_admin)):
    """Check Nextcloud connection status."""
    result = await nextcloud_integration.check_status()
    response = {"connected": result.connected}
    if result.server_name:
        response["serverName"] = result.server_name
    if result.error:
        response["error"] = result.error
    return response
