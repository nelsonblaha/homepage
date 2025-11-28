"""Tests for integration base classes."""
import pytest
from dataclasses import asdict


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
    monkeypatch.setenv("TEST_URL", "http://localhost:9999")
    monkeypatch.setenv("TEST_API_KEY", "testkey123")


# =============================================================================
# DATACLASS TESTS
# =============================================================================

def test_user_result_defaults():
    """Test UserResult has correct defaults."""
    from integrations.base import UserResult

    result = UserResult(success=True)
    assert result.success is True
    assert result.user_id is None
    assert result.username is None
    assert result.password is None
    assert result.email is None
    assert result.error is None
    assert result.extra == {}


def test_user_result_with_values():
    """Test UserResult with all values."""
    from integrations.base import UserResult

    result = UserResult(
        success=True,
        user_id="123",
        username="testuser",
        password="secret",
        email="test@example.com",
        extra={"foo": "bar"}
    )
    assert result.user_id == "123"
    assert result.username == "testuser"
    assert result.extra["foo"] == "bar"


def test_auth_result_defaults():
    """Test AuthResult has correct defaults."""
    from integrations.base import AuthResult

    result = AuthResult(success=False, error="Test error")
    assert result.success is False
    assert result.access_token is None
    assert result.cookies == {}
    assert result.error == "Test error"


def test_auth_result_with_cookies():
    """Test AuthResult with cookies."""
    from integrations.base import AuthResult

    result = AuthResult(
        success=True,
        access_token="token123",
        cookies={"session": "abc123"}
    )
    assert result.cookies["session"] == "abc123"


def test_status_result():
    """Test StatusResult dataclass."""
    from integrations.base import StatusResult

    result = StatusResult(connected=True, server_name="TestServer")
    assert result.connected is True
    assert result.server_name == "TestServer"
    assert result.error is None


# =============================================================================
# INTEGRATION BASE TESTS
# =============================================================================

class TestIntegrationBase:
    """Tests for IntegrationBase utility methods."""

    def test_generate_password_length(self, mock_env):
        """Test password generation creates expected length."""
        from integrations.base import IntegrationBase

        # Generate multiple passwords and check they're all different
        passwords = [IntegrationBase.generate_password() for _ in range(5)]
        assert len(set(passwords)) == 5  # All unique

        # Check approximate length (base64 encoding expands by ~4/3)
        for pwd in passwords:
            assert len(pwd) >= 16

    def test_generate_password_custom_length(self, mock_env):
        """Test password generation with custom length."""
        from integrations.base import IntegrationBase

        # Shorter password
        short = IntegrationBase.generate_password(8)
        assert len(short) >= 8

        # Longer password
        long = IntegrationBase.generate_password(32)
        assert len(long) >= 32

    def test_sanitize_username(self, mock_env):
        """Test username sanitization."""
        from integrations.base import IntegrationBase

        assert IntegrationBase.sanitize_username("John Doe") == "john_doe"
        assert IntegrationBase.sanitize_username("Test@User") == "testuser"
        assert IntegrationBase.sanitize_username("UPPERCASE") == "uppercase"
        assert IntegrationBase.sanitize_username("already_clean") == "already_clean"

    def test_generate_email(self, mock_env):
        """Test email generation."""
        from integrations.base import TokenInjectionIntegration

        # Create a concrete implementation for testing
        class TestIntegration(TokenInjectionIntegration):
            SERVICE_NAME = "test"
            ENV_PREFIX = "TEST"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        email = integration.generate_email("John Doe")
        assert email == "john_doe@test.local"

    def test_get_public_url(self, mock_env):
        """Test public URL generation."""
        from integrations.base import TokenInjectionIntegration

        class TestIntegration(TokenInjectionIntegration):
            SERVICE_NAME = "myservice"
            ENV_PREFIX = "TEST"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        url = integration.get_public_url()
        assert url == "https://myservice.test.local"

    def test_service_url_from_env(self, mock_env):
        """Test service URL from environment."""
        from integrations.base import IntegrationBase

        class TestIntegration(IntegrationBase):
            SERVICE_NAME = "test"
            ENV_PREFIX = "TEST"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        assert integration.service_url == "http://localhost:9999"
        assert integration.api_key == "testkey123"

    def test_is_configured(self, mock_env):
        """Test is_configured property."""
        from integrations.base import IntegrationBase

        class TestIntegration(IntegrationBase):
            SERVICE_NAME = "test"
            ENV_PREFIX = "TEST"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        assert integration.is_configured is True

        # Test unconfigured
        class UnconfiguredIntegration(IntegrationBase):
            SERVICE_NAME = "unconfigured"
            ENV_PREFIX = "NONEXISTENT"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        unconfigured = UnconfiguredIntegration()
        assert unconfigured.is_configured is False


# =============================================================================
# TOKEN INJECTION TESTS
# =============================================================================

class TestTokenInjectionIntegration:
    """Tests for TokenInjectionIntegration."""

    def test_build_auth_setup_html(self, mock_env):
        """Test auth setup HTML generation."""
        from integrations.base import TokenInjectionIntegration, AuthResult

        class TestIntegration(TokenInjectionIntegration):
            SERVICE_NAME = "testservice"
            ENV_PREFIX = "TEST"
            LOCAL_STORAGE_KEY = "test_token"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        auth_result = AuthResult(success=True, access_token="mytoken123")

        html = integration.build_auth_setup_html(auth_result)

        # Check key elements are present
        assert "test_token" in html  # localStorage key
        assert "mytoken123" in html  # token value
        assert "https://testservice.test.local" in html  # redirect URL
        assert "Signing into Testservice" in html  # title


# =============================================================================
# CREDENTIAL DISPLAY TESTS
# =============================================================================

class TestCredentialDisplayIntegration:
    """Tests for CredentialDisplayIntegration."""

    def test_build_credentials_display_html(self, mock_env):
        """Test credentials display HTML generation."""
        from integrations.base import CredentialDisplayIntegration

        class TestIntegration(CredentialDisplayIntegration):
            SERVICE_NAME = "nextcloud"
            ENV_PREFIX = "TEST"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        html = integration.build_credentials_display_html("testuser", "secretpass")

        # Check key elements are present
        assert "testuser" in html
        assert "secretpass" in html
        assert "https://nextcloud.test.local" in html
        assert "Nextcloud Login" in html


# =============================================================================
# STATS ONLY TESTS
# =============================================================================

class TestStatsOnlyIntegration:
    """Tests for StatsOnlyIntegration."""

    @pytest.mark.asyncio
    async def test_create_user_returns_error(self, mock_env):
        """Test that create_user returns error for stats-only."""
        from integrations.base import StatsOnlyIntegration

        class TestStats(StatsOnlyIntegration):
            SERVICE_NAME = "jitsi"
            ENV_PREFIX = "TEST"

            async def check_status(self):
                pass

            async def get_stats(self):
                return {"participants": 5}

        integration = TestStats()
        result = await integration.create_user("testuser")

        assert result.success is False
        assert "doesn't support" in result.error

    @pytest.mark.asyncio
    async def test_delete_user_returns_false(self, mock_env):
        """Test that delete_user returns False for stats-only."""
        from integrations.base import StatsOnlyIntegration

        class TestStats(StatsOnlyIntegration):
            SERVICE_NAME = "jitsi"
            ENV_PREFIX = "TEST"

            async def check_status(self):
                pass

            async def get_stats(self):
                return {"participants": 5}

        integration = TestStats()
        result = await integration.delete_user("123")

        assert result is False


# =============================================================================
# DEFAULT AUTHENTICATE TESTS
# =============================================================================

class TestDefaultAuthenticate:
    """Tests for default authenticate method."""

    @pytest.mark.asyncio
    async def test_default_authenticate_not_implemented(self, mock_env):
        """Test default authenticate returns not implemented."""
        from integrations.base import TokenInjectionIntegration

        class TestIntegration(TokenInjectionIntegration):
            SERVICE_NAME = "test"
            ENV_PREFIX = "TEST"
            LOCAL_STORAGE_KEY = "test"

            async def create_user(self, username):
                pass

            async def delete_user(self, user_id):
                pass

            async def check_status(self):
                pass

        integration = TestIntegration()
        result = await integration.authenticate("user", "pass")

        assert result.success is False
        assert "not implemented" in result.error.lower()
