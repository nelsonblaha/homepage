"""
Integration Base Classes - DRY Architecture for Service Integrations

This module provides abstract base classes for all service integrations.
Each integration strategy (token injection, cookie proxy, etc.) has its own
base class with common functionality.

Usage:
    class OmbiIntegration(TokenInjectionIntegration):
        SERVICE_NAME = "ombi"

        async def create_user(self, username: str) -> UserResult:
            # Ombi-specific implementation
            ...
"""

import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any

import httpx


# =============================================================================
# RESULT DATACLASSES
# =============================================================================

@dataclass
class UserResult:
    """Result of user creation/deletion operations."""
    success: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    email: Optional[str] = None
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class AuthResult:
    """Result of authentication operations."""
    success: bool
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    cookies: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class StatusResult:
    """Result of status check operations."""
    connected: bool
    server_name: Optional[str] = None
    error: Optional[str] = None
    extra: dict = field(default_factory=dict)


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class IntegrationBase(ABC):
    """
    Abstract base class for all service integrations.

    Subclasses must define SERVICE_NAME and implement the abstract methods.
    Common utilities like password generation and username sanitization
    are provided.
    """

    # Override in subclass
    SERVICE_NAME: str = ""
    ENV_PREFIX: str = ""

    # Database column names for this integration
    DB_USER_ID_COLUMN: str = ""
    DB_PASSWORD_COLUMN: str = ""

    def __init__(self):
        """Initialize with environment variables."""
        self.base_domain = os.environ.get("BASE_DOMAIN", "localhost")
        self.cookie_domain = os.environ.get("COOKIE_DOMAIN", "")

    # -------------------------------------------------------------------------
    # Configuration Properties (override in subclass or use env vars)
    # -------------------------------------------------------------------------

    @property
    def service_url(self) -> str:
        """Get the service URL from environment."""
        return os.environ.get(f"{self.ENV_PREFIX}_URL", "")

    @property
    def api_key(self) -> str:
        """Get the API key from environment."""
        return os.environ.get(f"{self.ENV_PREFIX}_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        """Check if the integration has required configuration."""
        return bool(self.service_url)

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    @staticmethod
    def generate_password(length: int = 16) -> str:
        """Generate a secure random password."""
        return secrets.token_urlsafe(length)

    def generate_email(self, username: str) -> str:
        """Generate an email address for a username."""
        safe_username = self.sanitize_username(username)
        return f"{safe_username}@{self.base_domain}"

    @staticmethod
    def sanitize_username(username: str) -> str:
        """Sanitize a username for use in APIs."""
        return username.lower().replace(" ", "_").replace("@", "")

    def get_public_url(self) -> str:
        """Get the public-facing URL for this service."""
        return f"https://{self.SERVICE_NAME}.{self.base_domain}"

    # -------------------------------------------------------------------------
    # Abstract Methods (must implement)
    # -------------------------------------------------------------------------

    @abstractmethod
    async def create_user(self, username: str) -> UserResult:
        """
        Create a user account in the service.

        Args:
            username: The friend's name to use for the account

        Returns:
            UserResult with success status and user details
        """
        pass

    @abstractmethod
    async def delete_user(self, user_id: str) -> bool:
        """
        Delete a user account from the service.

        Args:
            user_id: The service-specific user ID

        Returns:
            True if deletion was successful
        """
        pass

    @abstractmethod
    async def check_status(self) -> StatusResult:
        """
        Check if the service is online and configured.

        Returns:
            StatusResult with connection status
        """
        pass

    # -------------------------------------------------------------------------
    # Optional Methods (override as needed)
    # -------------------------------------------------------------------------

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Authenticate a user and get credentials for auto-login.

        Override this in integrations that support auto-login.

        Args:
            username: The username to authenticate
            password: The password to authenticate with

        Returns:
            AuthResult with authentication credentials
        """
        return AuthResult(success=False, error="Authentication not implemented")

    def build_auth_setup_html(self, auth_result: AuthResult) -> str:
        """
        Build the HTML page for auto-login setup.

        Override this in integrations that use token injection.

        Args:
            auth_result: The authentication result with credentials

        Returns:
            HTML string for the auth setup page
        """
        return "<html><body>Auth setup not implemented</body></html>"


# =============================================================================
# STRATEGY BASE CLASSES
# =============================================================================

class TokenInjectionIntegration(IntegrationBase):
    """
    Base class for services using localStorage token injection.

    Services: Ombi, Jellyfin

    Auto-login flow:
    1. Friend clicks service link
    2. Backend authenticates to service API
    3. Receives JWT/access token
    4. Redirects to {service}.domain/blaha-auth-setup
    5. Auth-setup page injects token into localStorage
    6. Redirects to service (now logged in)
    """

    # Override in subclass
    LOCAL_STORAGE_KEY: str = ""
    AUTH_HEADER_NAME: str = "Authorization"
    AUTH_HEADER_PREFIX: str = "Bearer"

    def build_auth_setup_html(self, auth_result: AuthResult) -> str:
        """Build HTML that injects token into localStorage."""
        redirect_url = self.get_public_url()

        return f"""<!DOCTYPE html>
<html>
<head><title>Signing into {self.SERVICE_NAME.title()}...</title></head>
<body style="background:#101010;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center">
<h2>Signing into {self.SERVICE_NAME.title()}...</h2>
<script>
localStorage.setItem('{self.LOCAL_STORAGE_KEY}', '{auth_result.access_token}');
window.location.href = '{redirect_url}';
</script>
<noscript>JavaScript is required. <a href="{redirect_url}">Go to {self.SERVICE_NAME.title()}</a></noscript>
</div>
</body>
</html>"""


class CookieProxyIntegration(IntegrationBase):
    """
    Base class for services using session cookie proxy.

    Services: Overseerr, Mattermost

    Auto-login flow:
    1. Friend clicks service link
    2. Backend proxies login to service API
    3. Captures session cookie from response
    4. Sets cookie on your domain
    5. Redirects to service (cookie authenticates)
    """

    # Override in subclass
    COOKIE_NAME: str = ""

    async def proxy_login_and_redirect(self, username: str, password: str) -> tuple[dict, str]:
        """
        Proxy login to service and return cookies + redirect URL.

        Returns:
            Tuple of (cookies dict, redirect URL)
        """
        auth_result = await self.authenticate(username, password)
        if not auth_result.success:
            return {}, ""

        return auth_result.cookies, self.get_public_url()


class CredentialDisplayIntegration(IntegrationBase):
    """
    Base class for services where credentials are displayed to user.

    Services: Nextcloud

    Flow:
    1. Friend clicks service link
    2. Modal shows username and password
    3. Friend copies credentials and logs in manually
    """

    def build_credentials_display_html(self, username: str, password: str) -> str:
        """Build HTML that displays credentials to user."""
        service_url = self.get_public_url()

        return f"""<!DOCTYPE html>
<html>
<head><title>Login to {self.SERVICE_NAME.title()}</title></head>
<body style="background:#0082c9;color:#fff;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center;padding:20px">
<h2>{self.SERVICE_NAME.title()} Login</h2>
<p>Your credentials:</p>
<p><strong>Username:</strong> {username}</p>
<p><strong>Password:</strong> <code style="background:#fff;color:#333;padding:4px 8px;border-radius:4px">{password}</code></p>
<p style="margin-top:20px"><a href="{service_url}" style="color:#fff;font-size:1.2em">Go to {self.SERVICE_NAME.title()} →</a></p>
</div>
</body>
</html>"""


class ExternalAuthIntegration(IntegrationBase):
    """
    Base class for services with external authentication.

    Services: Plex (managed users with optional PIN)

    These services manage their own authentication externally
    and may use PINs or parent account sharing.
    """
    pass


class StatsOnlyIntegration(IntegrationBase):
    """
    Base class for services that only provide stats, no user management.

    Services: Jitsi

    These integrations provide participant counts or activity stats
    but don't create/manage user accounts.
    """

    async def create_user(self, username: str) -> UserResult:
        """Stats-only integrations don't create users."""
        return UserResult(success=False, error="This service doesn't support user creation")

    async def delete_user(self, user_id: str) -> bool:
        """Stats-only integrations don't delete users."""
        return False

    @abstractmethod
    async def get_stats(self) -> dict:
        """Get current stats from the service (e.g., participant count)."""
        pass


# =============================================================================
# HTTP CLIENT HELPER
# =============================================================================

class HttpIntegrationMixin:
    """
    Mixin providing HTTP client utilities for integrations.

    Use this with any integration base class that needs HTTP requests.
    """

    async def _get(
        self,
        url: str,
        headers: Optional[dict] = None,
        timeout: float = 10.0,
        verify_ssl: bool = True
    ) -> httpx.Response:
        """Make a GET request."""
        async with httpx.AsyncClient(verify=verify_ssl) as client:
            return await client.get(url, headers=headers, timeout=timeout)

    async def _post(
        self,
        url: str,
        json: Optional[dict] = None,
        data: Optional[dict] = None,
        headers: Optional[dict] = None,
        auth: Optional[tuple] = None,
        timeout: float = 10.0,
        verify_ssl: bool = True
    ) -> httpx.Response:
        """Make a POST request."""
        async with httpx.AsyncClient(verify=verify_ssl) as client:
            return await client.post(
                url,
                json=json,
                data=data,
                headers=headers,
                auth=auth,
                timeout=timeout
            )

    async def _delete(
        self,
        url: str,
        headers: Optional[dict] = None,
        timeout: float = 10.0,
        verify_ssl: bool = True
    ) -> httpx.Response:
        """Make a DELETE request."""
        async with httpx.AsyncClient(verify=verify_ssl) as client:
            return await client.delete(url, headers=headers, timeout=timeout)
