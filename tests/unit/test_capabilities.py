"""Tests for the service capabilities registry."""
import pytest
from integrations.capabilities import (
    AuthStrategy,
    UserManagement,
    ServiceCapabilities,
    SERVICES,
    get_service,
    get_auto_login_services,
    get_user_creation_services,
    get_testable_services,
    get_token_injection_services,
    get_cookie_proxy_services,
)


class TestAuthStrategy:
    """Tests for AuthStrategy enum."""

    def test_all_strategies_defined(self):
        """Verify all expected auth strategies exist."""
        assert AuthStrategy.TOKEN_INJECTION
        assert AuthStrategy.COOKIE_PROXY
        assert AuthStrategy.CREDENTIAL_DISPLAY
        assert AuthStrategy.EXTERNAL_PIN
        assert AuthStrategy.STATS_ONLY
        assert AuthStrategy.NONE

    def test_strategies_are_unique(self):
        """Each strategy should have a unique value."""
        values = [s.value for s in AuthStrategy]
        assert len(values) == len(set(values))


class TestUserManagement:
    """Tests for UserManagement enum."""

    def test_all_management_types_defined(self):
        """Verify all expected user management types exist."""
        assert UserManagement.FULL_API
        assert UserManagement.CREATE_ONLY
        assert UserManagement.MANAGED_USERS
        assert UserManagement.NONE

    def test_types_are_unique(self):
        """Each type should have a unique value."""
        values = [t.value for t in UserManagement]
        assert len(values) == len(set(values))


class TestServiceCapabilities:
    """Tests for ServiceCapabilities dataclass."""

    def test_minimal_service(self):
        """Can create a service with only required fields."""
        service = ServiceCapabilities(name="Test", slug="test")
        assert service.name == "Test"
        assert service.slug == "test"
        assert service.auth_strategy == AuthStrategy.NONE
        assert service.auto_login is False

    def test_full_service_config(self):
        """Can create a service with all fields configured."""
        service = ServiceCapabilities(
            name="Full Service",
            slug="full",
            icon="fa-star",
            auth_strategy=AuthStrategy.TOKEN_INJECTION,
            user_management=UserManagement.FULL_API,
            auto_login=True,
            requires_auth_setup_proxy=True,
            local_storage_key="auth_token",
            can_create_users=True,
            can_delete_users=True,
            can_set_permissions=True,
            generates_password=True,
            has_status_check=True,
            env_prefix="FULL",
            ci_container_image="test/image:latest",
            ci_port=8080,
            test_file="test.cy.js",
        )
        assert service.name == "Full Service"
        assert service.auth_strategy == AuthStrategy.TOKEN_INJECTION
        assert service.auto_login is True
        assert service.ci_port == 8080


class TestServicesRegistry:
    """Tests for the SERVICES registry."""

    def test_registry_not_empty(self):
        """Registry should contain services."""
        assert len(SERVICES) > 0

    def test_ombi_in_registry(self):
        """Ombi should be in the registry with correct config."""
        assert "ombi" in SERVICES
        ombi = SERVICES["ombi"]
        assert ombi.name == "Ombi"
        assert ombi.auth_strategy == AuthStrategy.TOKEN_INJECTION
        assert ombi.auto_login is True
        assert ombi.can_create_users is True

    def test_jellyfin_in_registry(self):
        """Jellyfin should be in the registry with correct config."""
        assert "jellyfin" in SERVICES
        jellyfin = SERVICES["jellyfin"]
        assert jellyfin.name == "Jellyfin"
        assert jellyfin.auth_strategy == AuthStrategy.TOKEN_INJECTION
        assert jellyfin.local_storage_key == "jellyfin_credentials"

    def test_overseerr_uses_cookie_proxy(self):
        """Overseerr should use cookie proxy auth."""
        assert "overseerr" in SERVICES
        overseerr = SERVICES["overseerr"]
        assert overseerr.auth_strategy == AuthStrategy.COOKIE_PROXY
        assert overseerr.cookie_name == "connect.sid"

    def test_mattermost_uses_cookie_proxy(self):
        """Mattermost should use cookie proxy auth."""
        assert "mattermost" in SERVICES
        mattermost = SERVICES["mattermost"]
        assert mattermost.auth_strategy == AuthStrategy.COOKIE_PROXY
        assert mattermost.cookie_name == "MMAUTHTOKEN"

    def test_nextcloud_uses_credential_display(self):
        """Nextcloud should use credential display auth."""
        assert "nextcloud" in SERVICES
        nextcloud = SERVICES["nextcloud"]
        assert nextcloud.auth_strategy == AuthStrategy.CREDENTIAL_DISPLAY
        assert nextcloud.auto_login is False

    def test_plex_uses_external_pin(self):
        """Plex should use external PIN auth."""
        assert "plex" in SERVICES
        plex = SERVICES["plex"]
        assert plex.auth_strategy == AuthStrategy.EXTERNAL_PIN
        assert plex.user_management == UserManagement.MANAGED_USERS

    def test_jitsi_is_stats_only(self):
        """Jitsi should be stats-only."""
        assert "jitsi" in SERVICES
        jitsi = SERVICES["jitsi"]
        assert jitsi.auth_strategy == AuthStrategy.STATS_ONLY
        assert jitsi.can_create_users is False
        assert jitsi.has_user_stats is True

    def test_all_services_have_slug_matching_key(self):
        """Each service's slug should match its registry key."""
        for key, service in SERVICES.items():
            assert service.slug == key, f"Service {key} has mismatched slug: {service.slug}"

    def test_all_services_have_name(self):
        """Each service should have a non-empty name."""
        for key, service in SERVICES.items():
            assert service.name, f"Service {key} has no name"


class TestGetService:
    """Tests for get_service function."""

    def test_get_existing_service(self):
        """Can retrieve an existing service."""
        service = get_service("ombi")
        assert service is not None
        assert service.name == "Ombi"

    def test_get_nonexistent_service(self):
        """Returns None for unknown service."""
        service = get_service("nonexistent")
        assert service is None


class TestGetAutoLoginServices:
    """Tests for get_auto_login_services function."""

    def test_returns_list(self):
        """Should return a list."""
        services = get_auto_login_services()
        assert isinstance(services, list)

    def test_all_have_auto_login(self):
        """All returned services should have auto_login=True."""
        services = get_auto_login_services()
        for service in services:
            assert service.auto_login is True

    def test_includes_known_auto_login_services(self):
        """Should include Ombi, Jellyfin, Overseerr, Mattermost."""
        services = get_auto_login_services()
        slugs = [s.slug for s in services]
        assert "ombi" in slugs
        assert "jellyfin" in slugs
        assert "overseerr" in slugs
        assert "mattermost" in slugs


class TestGetUserCreationServices:
    """Tests for get_user_creation_services function."""

    def test_returns_list(self):
        """Should return a list."""
        services = get_user_creation_services()
        assert isinstance(services, list)

    def test_all_can_create_users(self):
        """All returned services should have can_create_users=True."""
        services = get_user_creation_services()
        for service in services:
            assert service.can_create_users is True


class TestGetTestableServices:
    """Tests for get_testable_services function."""

    def test_returns_list(self):
        """Should return a list."""
        services = get_testable_services()
        assert isinstance(services, list)

    def test_all_have_ci_image(self):
        """All returned services should have a CI container image."""
        services = get_testable_services()
        for service in services:
            assert service.ci_container_image is not None

    def test_excludes_plex_and_jitsi(self):
        """Should exclude Plex and Jitsi (no CI images)."""
        services = get_testable_services()
        slugs = [s.slug for s in services]
        assert "plex" not in slugs
        assert "jitsi" not in slugs


class TestGetTokenInjectionServices:
    """Tests for get_token_injection_services function."""

    def test_returns_list(self):
        """Should return a list."""
        services = get_token_injection_services()
        assert isinstance(services, list)

    def test_all_use_token_injection(self):
        """All returned services should use token injection."""
        services = get_token_injection_services()
        for service in services:
            assert service.auth_strategy == AuthStrategy.TOKEN_INJECTION

    def test_includes_ombi_and_jellyfin(self):
        """Should include Ombi and Jellyfin."""
        services = get_token_injection_services()
        slugs = [s.slug for s in services]
        assert "ombi" in slugs
        assert "jellyfin" in slugs


class TestGetCookieProxyServices:
    """Tests for get_cookie_proxy_services function."""

    def test_returns_list(self):
        """Should return a list."""
        services = get_cookie_proxy_services()
        assert isinstance(services, list)

    def test_all_use_cookie_proxy(self):
        """All returned services should use cookie proxy."""
        services = get_cookie_proxy_services()
        for service in services:
            assert service.auth_strategy == AuthStrategy.COOKIE_PROXY

    def test_includes_overseerr_and_mattermost(self):
        """Should include Overseerr and Mattermost."""
        services = get_cookie_proxy_services()
        slugs = [s.slug for s in services]
        assert "overseerr" in slugs
        assert "mattermost" in slugs
