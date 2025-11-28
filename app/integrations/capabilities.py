"""
Service Capabilities Registry - Single Source of Truth

This file defines the capabilities of each integration. It is the authoritative
source for what features each service supports.

When adding a new service:
1. Add a ServiceCapabilities entry here
2. Implement the integration module in app/integrations/<service>.py
3. Add CI tests in docker-compose.ci.yml and cypress/e2e/integration/<service>.cy.js

When this registry says a service has a capability, there MUST be:
- Implementation code for that capability
- Tests proving that capability works
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class AuthStrategy(Enum):
    """How users are authenticated to the service."""
    TOKEN_INJECTION = auto()      # localStorage token (Ombi, Jellyfin)
    COOKIE_PROXY = auto()         # Session cookie (Overseerr, Mattermost)
    CREDENTIAL_DISPLAY = auto()   # Show credentials in modal (Nextcloud)
    EXTERNAL_PIN = auto()         # External auth with optional PIN (Plex)
    STATS_ONLY = auto()           # No user auth, just stats (Jitsi)
    NONE = auto()                 # No authentication support


class UserManagement(Enum):
    """How users are created/deleted in the service."""
    FULL_API = auto()             # Create, delete, list via API
    CREATE_ONLY = auto()          # Can create but not easily delete
    MANAGED_USERS = auto()        # Uses parent account's managed users (Plex)
    NONE = auto()                 # No user management


@dataclass
class ServiceCapabilities:
    """Defines what a service integration can do."""

    # Identity
    name: str                          # Display name
    slug: str                          # URL-safe identifier (used in routes, DB)
    icon: str = "fas fa-cube"          # FontAwesome icon

    # Core capabilities
    auth_strategy: AuthStrategy = AuthStrategy.NONE
    user_management: UserManagement = UserManagement.NONE

    # Auto-login specifics
    auto_login: bool = False           # Can users be automatically logged in?
    requires_auth_setup_proxy: bool = False  # Needs /blaha-auth-setup nginx route?
    local_storage_key: Optional[str] = None  # localStorage key for token injection
    cookie_name: Optional[str] = None        # Cookie name for cookie proxy

    # User creation specifics
    can_create_users: bool = False
    can_delete_users: bool = False
    can_set_permissions: bool = False
    generates_password: bool = False   # Service auto-generates password

    # Status and monitoring
    has_status_check: bool = False     # Can check if service is online
    has_user_stats: bool = False       # Can get user activity stats

    # Environment variable prefixes
    env_prefix: str = ""               # e.g., "OMBI" -> OMBI_URL, OMBI_API_KEY

    # Testing
    ci_container_image: Optional[str] = None  # Docker image for CI testing
    ci_port: Optional[int] = None             # Port for CI testing
    test_file: Optional[str] = None           # Cypress test file


# =============================================================================
# SERVICE REGISTRY - The Single Source of Truth
# =============================================================================

SERVICES = {
    # Token Injection Services
    "ombi": ServiceCapabilities(
        name="Ombi",
        slug="ombi",
        icon="fa-film",
        auth_strategy=AuthStrategy.TOKEN_INJECTION,
        user_management=UserManagement.FULL_API,
        auto_login=True,
        requires_auth_setup_proxy=True,
        local_storage_key="id_token",
        can_create_users=True,
        can_delete_users=True,
        can_set_permissions=True,
        generates_password=True,
        has_status_check=True,
        env_prefix="OMBI",
        ci_container_image="linuxserver/ombi:latest",
        ci_port=3580,
        test_file="cypress/e2e/integration/ombi.cy.js",
    ),

    "jellyfin": ServiceCapabilities(
        name="Jellyfin",
        slug="jellyfin",
        icon="fa-play-circle",
        auth_strategy=AuthStrategy.TOKEN_INJECTION,
        user_management=UserManagement.FULL_API,
        auto_login=True,
        requires_auth_setup_proxy=True,
        local_storage_key="jellyfin_credentials",
        can_create_users=True,
        can_delete_users=True,
        can_set_permissions=True,
        generates_password=True,
        has_status_check=True,
        env_prefix="JELLYFIN",
        ci_container_image="linuxserver/jellyfin:latest",
        ci_port=8196,
        test_file="cypress/e2e/integration/jellyfin.cy.js",
    ),

    # Cookie Proxy Services
    "overseerr": ServiceCapabilities(
        name="Overseerr",
        slug="overseerr",
        icon="fa-ticket",
        auth_strategy=AuthStrategy.COOKIE_PROXY,
        user_management=UserManagement.FULL_API,
        auto_login=True,
        requires_auth_setup_proxy=False,
        cookie_name="connect.sid",
        can_create_users=True,
        can_delete_users=True,
        can_set_permissions=True,
        generates_password=True,
        has_status_check=True,
        env_prefix="OVERSEERR",
        ci_container_image="lscr.io/linuxserver/overseerr:latest",
        ci_port=5155,
        test_file="cypress/e2e/integration/overseerr.cy.js",
    ),

    "mattermost": ServiceCapabilities(
        name="Mattermost",
        slug="mattermost",
        icon="fa-comments",
        auth_strategy=AuthStrategy.COOKIE_PROXY,
        user_management=UserManagement.FULL_API,
        auto_login=True,
        requires_auth_setup_proxy=False,
        cookie_name="MMAUTHTOKEN",
        can_create_users=True,
        can_delete_users=True,
        can_set_permissions=True,
        generates_password=True,
        has_status_check=True,
        env_prefix="MATTERMOST",
        ci_container_image="mattermost/mattermost-preview:latest",
        ci_port=8165,
        test_file="cypress/e2e/integration/mattermost.cy.js",
    ),

    # Credential Display Services
    "nextcloud": ServiceCapabilities(
        name="Nextcloud",
        slug="nextcloud",
        icon="fa-cloud",
        auth_strategy=AuthStrategy.CREDENTIAL_DISPLAY,
        user_management=UserManagement.FULL_API,
        auto_login=False,  # Shows credentials, user logs in manually
        requires_auth_setup_proxy=False,
        can_create_users=True,
        can_delete_users=True,
        can_set_permissions=True,
        generates_password=True,
        has_status_check=True,
        env_prefix="NEXTCLOUD",
        ci_container_image="linuxserver/nextcloud:latest",
        ci_port=8186,
        test_file="cypress/e2e/integration/nextcloud.cy.js",
    ),

    # External/PIN Services
    "plex": ServiceCapabilities(
        name="Plex",
        slug="plex",
        icon="fa-play",
        auth_strategy=AuthStrategy.EXTERNAL_PIN,
        user_management=UserManagement.MANAGED_USERS,
        auto_login=False,  # Uses Plex managed users
        requires_auth_setup_proxy=False,
        can_create_users=True,  # Creates managed users
        can_delete_users=True,
        can_set_permissions=False,  # Permissions managed by Plex
        generates_password=False,  # PIN-based or passwordless
        has_status_check=True,
        env_prefix="PLEX",
        ci_container_image=None,  # Plex requires license, skip in CI
        ci_port=None,
        test_file=None,
    ),

    # Stats-Only Services
    "jitsi": ServiceCapabilities(
        name="Jitsi Meet",
        slug="jitsi",
        icon="fa-video",
        auth_strategy=AuthStrategy.STATS_ONLY,
        user_management=UserManagement.NONE,
        auto_login=False,
        requires_auth_setup_proxy=False,
        can_create_users=False,  # Jitsi users are ephemeral
        can_delete_users=False,
        has_status_check=True,
        has_user_stats=True,  # Can show active participants
        env_prefix="JITSI",
        ci_container_image=None,  # Jitsi is complex to test in CI
        ci_port=None,
        test_file=None,
    ),

    # Mastodon (not yet fully integrated)
    "mastodon": ServiceCapabilities(
        name="Mastodon",
        slug="mastodon",
        icon="fa-mastodon",
        auth_strategy=AuthStrategy.NONE,  # TODO: Implement OAuth
        user_management=UserManagement.NONE,
        auto_login=False,
        requires_auth_setup_proxy=False,
        can_create_users=False,
        can_delete_users=False,
        has_status_check=True,
        env_prefix="MASTODON",
        ci_container_image=None,
        ci_port=None,
        test_file=None,
    ),
}


def get_service(slug: str) -> Optional[ServiceCapabilities]:
    """Get capabilities for a service by slug."""
    return SERVICES.get(slug)


def get_auto_login_services() -> list[ServiceCapabilities]:
    """Get all services that support auto-login."""
    return [s for s in SERVICES.values() if s.auto_login]


def get_user_creation_services() -> list[ServiceCapabilities]:
    """Get all services that support user creation."""
    return [s for s in SERVICES.values() if s.can_create_users]


def get_testable_services() -> list[ServiceCapabilities]:
    """Get all services that have CI tests configured."""
    return [s for s in SERVICES.values() if s.ci_container_image]


def get_token_injection_services() -> list[ServiceCapabilities]:
    """Get services using token injection auth."""
    return [s for s in SERVICES.values() if s.auth_strategy == AuthStrategy.TOKEN_INJECTION]


def get_cookie_proxy_services() -> list[ServiceCapabilities]:
    """Get services using cookie proxy auth."""
    return [s for s in SERVICES.values() if s.auth_strategy == AuthStrategy.COOKIE_PROXY]
