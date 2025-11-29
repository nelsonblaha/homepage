"""Tests for integration modules with mocked HTTP."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
    monkeypatch.setenv("OMBI_URL", "http://localhost:3579")
    monkeypatch.setenv("OMBI_API_KEY", "testkey123")
    monkeypatch.setenv("JELLYFIN_URL", "http://localhost:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "testkey456")
    monkeypatch.setenv("OVERSEERR_URL", "http://localhost:5055")
    monkeypatch.setenv("OVERSEERR_API_KEY", "testkey789")


def make_mock_response(status_code=200, json_data=None, cookies=None, text=""):
    """Create a mock HTTP response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = text
    mock.cookies = cookies or {}
    return mock


# =============================================================================
# OMBI INTEGRATION TESTS
# =============================================================================

class TestOmbiIntegration:
    """Tests for Ombi integration with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_env):
        """Test successful Ombi user creation."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            # Mock user creation response
            mock_ctx.post.return_value = make_mock_response(
                status_code=200,
                json_data={"id": "123", "userName": "testuser"}
            )

            result = await ombi_integration.create_user("testuser")

            assert result.success is True
            assert result.user_id == "123"
            assert result.username == "testuser"
            assert result.password is not None  # Generated password

    @pytest.mark.asyncio
    async def test_create_user_failure(self, mock_env):
        """Test Ombi user creation failure."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(
                status_code=400,
                text="User already exists"
            )

            result = await ombi_integration.create_user("existinguser")

            assert result.success is False
            assert result.error is not None
            assert "400" in result.error

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_env):
        """Test successful Ombi user deletion."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=200)

            result = await ombi_integration.delete_user("123")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_failure(self, mock_env):
        """Test Ombi user deletion failure."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=404)

            result = await ombi_integration.delete_user("nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_env):
        """Test successful Ombi authentication."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(
                status_code=200,
                json_data={"access_token": "jwt-token-here"}
            )

            result = await ombi_integration.authenticate("user", "pass")

            assert result.success is True
            assert result.access_token == "jwt-token-here"

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mock_env):
        """Test failed Ombi authentication."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(status_code=401)

            result = await ombi_integration.authenticate("user", "wrongpass")

            assert result.success is False
            assert result.access_token is None

    @pytest.mark.asyncio
    async def test_check_status_connected(self, mock_env):
        """Test Ombi status check when connected."""
        from integrations.ombi import ombi_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(
                status_code=200,
                json_data={"applicationUrl": "http://ombi.test"}
            )

            result = await ombi_integration.check_status()

            assert result.connected is True


# =============================================================================
# JELLYFIN INTEGRATION TESTS
# =============================================================================

class TestJellyfinIntegration:
    """Tests for Jellyfin integration with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_env):
        """Test successful Jellyfin user creation."""
        from integrations.jellyfin import jellyfin_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            # Mock user creation
            mock_ctx.post.side_effect = [
                make_mock_response(200, {"Id": "user-uuid", "Name": "testuser"}),
                make_mock_response(204)  # Password set
            ]

            result = await jellyfin_integration.create_user("testuser")

            assert result.success is True
            assert result.user_id == "user-uuid"
            assert result.username == "testuser"
            assert result.password is not None

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mock_env):
        """Test successful Jellyfin authentication."""
        from integrations.jellyfin import jellyfin_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(
                status_code=200,
                json_data={
                    "AccessToken": "token123",
                    "User": {"Id": "user-uuid"},
                    "ServerId": "server-uuid"
                }
            )

            result = await jellyfin_integration.authenticate("user", "pass")

            assert result.success is True
            assert result.access_token == "token123"
            assert result.user_id == "user-uuid"
            assert result.extra["server_id"] == "server-uuid"

    @pytest.mark.asyncio
    async def test_check_status_returns_server_name(self, mock_env):
        """Test Jellyfin status returns server name."""
        from integrations.jellyfin import jellyfin_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(
                status_code=200,
                json_data={"ServerName": "My Jellyfin Server"}
            )

            result = await jellyfin_integration.check_status()

            assert result.connected is True
            assert result.server_name == "My Jellyfin Server"

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_env):
        """Test successful Jellyfin user deletion."""
        from integrations.jellyfin import jellyfin_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=204)

            result = await jellyfin_integration.delete_user("user-uuid-123")

            assert result is True
            mock_ctx.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_user_failure(self, mock_env):
        """Test Jellyfin user deletion failure."""
        from integrations.jellyfin import jellyfin_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=404)

            result = await jellyfin_integration.delete_user("nonexistent")

            assert result is False


# =============================================================================
# OVERSEERR INTEGRATION TESTS
# =============================================================================

class TestOverseerrIntegration:
    """Tests for Overseerr integration with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_create_user_with_permissions(self, mock_env):
        """Test Overseerr user creation includes permissions."""
        from integrations.overseerr import overseerr_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            mock_ctx.post.side_effect = [
                make_mock_response(200, {"id": 42}),  # User creation
                make_mock_response(204)  # Password set
            ]

            result = await overseerr_integration.create_user("testuser")

            assert result.success is True
            assert result.user_id == "42"
            # Verify permissions were sent (bit 34 = REQUEST + AUTO_APPROVE)
            call_args = mock_ctx.post.call_args_list[0]
            assert call_args.kwargs["json"]["permissions"] == 34

    @pytest.mark.asyncio
    async def test_authenticate_returns_cookies(self, mock_env):
        """Test Overseerr auth returns session cookies."""
        from integrations.overseerr import overseerr_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.cookies = {"connect.sid": "session-cookie-value"}
            mock_ctx.post.return_value = mock_response

            result = await overseerr_integration.authenticate("test@test.local", "pass")

            assert result.success is True
            assert "connect.sid" in result.cookies

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_env):
        """Test successful Overseerr user deletion."""
        from integrations.overseerr import overseerr_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=204)

            result = await overseerr_integration.delete_user("42")

            assert result is True
            mock_ctx.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_user_failure(self, mock_env):
        """Test Overseerr user deletion failure."""
        from integrations.overseerr import overseerr_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=404)

            result = await overseerr_integration.delete_user("nonexistent")

            assert result is False


# =============================================================================
# INTEGRATION NOT CONFIGURED TESTS
# =============================================================================

class TestIntegrationNotConfigured:
    """Test behavior when integrations are not configured."""

    def test_ombi_not_configured(self, monkeypatch):
        """Test Ombi returns not configured when env vars missing."""
        monkeypatch.delenv("OMBI_URL", raising=False)
        monkeypatch.delenv("OMBI_API_KEY", raising=False)
        monkeypatch.setenv("BASE_DOMAIN", "test.local")

        # Need to reimport to pick up new env
        import importlib
        import integrations.ombi
        importlib.reload(integrations.ombi)

        assert integrations.ombi.ombi_integration.is_configured is False

    @pytest.mark.asyncio
    async def test_create_user_when_not_configured(self, monkeypatch):
        """Test create_user returns error when not configured."""
        monkeypatch.delenv("JELLYFIN_URL", raising=False)
        monkeypatch.delenv("JELLYFIN_API_KEY", raising=False)
        monkeypatch.setenv("BASE_DOMAIN", "test.local")

        import importlib
        import integrations.jellyfin
        importlib.reload(integrations.jellyfin)

        result = await integrations.jellyfin.jellyfin_integration.create_user("test")
        assert result.success is False
        assert "not configured" in result.error.lower()


# =============================================================================
# MATTERMOST INTEGRATION TESTS
# =============================================================================

class TestMattermostIntegration:
    """Tests for Mattermost integration with mocked HTTP."""

    @pytest.fixture
    def mm_env(self, monkeypatch):
        """Set up Mattermost-specific environment variables."""
        monkeypatch.setenv("BASE_DOMAIN", "test.local")
        monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
        monkeypatch.setenv("MATTERMOST_URL", "http://localhost:8065")
        monkeypatch.setenv("MATTERMOST_TOKEN", "testtoken123")
        monkeypatch.setenv("MATTERMOST_TEAM_ID", "team-uuid-123")

    @pytest.mark.asyncio
    async def test_create_user_success(self, mm_env):
        """Test successful Mattermost user creation."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            # Mock user creation and team add
            mock_ctx.post.side_effect = [
                make_mock_response(200, {"id": "user-uuid-123", "username": "testuser"}),
                make_mock_response(200)  # Team add
            ]

            result = await mattermost_integration.create_user("testuser")

            assert result.success is True
            assert result.user_id == "user-uuid-123"
            assert result.password is not None

    @pytest.mark.asyncio
    async def test_create_user_failure(self, mm_env):
        """Test Mattermost user creation failure."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(
                status_code=400,
                text="User already exists"
            )

            result = await mattermost_integration.create_user("existinguser")

            assert result.success is False
            assert "400" in result.error

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mm_env):
        """Test successful Mattermost user deletion."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=200)

            result = await mattermost_integration.delete_user("user-uuid-123")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_failure(self, mm_env):
        """Test Mattermost user deletion failure."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=404)

            result = await mattermost_integration.delete_user("nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mm_env):
        """Test successful Mattermost authentication with header token."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Token": "session-token-abc"}
            mock_ctx.post.return_value = mock_response

            result = await mattermost_integration.authenticate("user@test.local", "pass")

            assert result.success is True
            assert result.access_token == "session-token-abc"
            assert "MMAUTHTOKEN" in result.cookies

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, mm_env):
        """Test failed Mattermost authentication."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.post.return_value = make_mock_response(status_code=401)

            result = await mattermost_integration.authenticate("user@test.local", "wrong")

            assert result.success is False

    @pytest.mark.asyncio
    async def test_check_status_connected(self, mm_env):
        """Test Mattermost status check when connected."""
        from integrations.mattermost import mattermost_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(status_code=200)

            result = await mattermost_integration.check_status()

            assert result.connected is True
            assert result.server_name == "Mattermost"


# =============================================================================
# NEXTCLOUD INTEGRATION TESTS
# =============================================================================

class TestNextcloudIntegration:
    """Tests for Nextcloud integration with mocked HTTP."""

    @pytest.fixture
    def nc_env(self, monkeypatch):
        """Set up Nextcloud-specific environment variables."""
        monkeypatch.setenv("BASE_DOMAIN", "test.local")
        monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
        monkeypatch.setenv("NEXTCLOUD_URL", "https://localhost:8443")
        monkeypatch.setenv("NEXTCLOUD_ADMIN_USER", "admin")
        monkeypatch.setenv("NEXTCLOUD_ADMIN_PASS", "adminpass")
        monkeypatch.setenv("NEXTCLOUD_HOST", "nextcloud.test.local")

    @pytest.mark.asyncio
    async def test_create_user_success(self, nc_env):
        """Test successful Nextcloud user creation."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            # OCS success response
            xml_response = """<?xml version="1.0"?>
            <ocs><meta><statuscode>100</statuscode></meta></ocs>"""
            mock_ctx.post.return_value = make_mock_response(200, text=xml_response)

            result = await nextcloud_integration.create_user("testuser")

            assert result.success is True
            assert result.user_id == "testuser"  # Nextcloud uses username as ID
            assert result.password is not None

    @pytest.mark.asyncio
    async def test_create_user_failure(self, nc_env):
        """Test Nextcloud user creation failure."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            # OCS failure response
            xml_response = """<?xml version="1.0"?>
            <ocs><meta><statuscode>102</statuscode><message>User already exists</message></meta></ocs>"""
            mock_ctx.post.return_value = make_mock_response(200, text=xml_response)

            result = await nextcloud_integration.create_user("existinguser")

            assert result.success is False
            assert "User already exists" in result.error

    @pytest.mark.asyncio
    async def test_delete_user_success(self, nc_env):
        """Test successful Nextcloud user deletion."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx

            xml_response = """<?xml version="1.0"?>
            <ocs><meta><statuscode>100</statuscode></meta></ocs>"""
            mock_ctx.delete.return_value = make_mock_response(200, text=xml_response)

            result = await nextcloud_integration.delete_user("testuser")

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_failure(self, nc_env):
        """Test Nextcloud user deletion failure."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.delete.return_value = make_mock_response(status_code=404)

            result = await nextcloud_integration.delete_user("nonexistent")

            assert result is False

    @pytest.mark.asyncio
    async def test_authenticate_success(self, nc_env):
        """Test Nextcloud credential validation."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(status_code=200)

            result = await nextcloud_integration.authenticate("user", "pass")

            assert result.success is True
            assert result.extra["valid"] is True

    @pytest.mark.asyncio
    async def test_authenticate_failure(self, nc_env):
        """Test Nextcloud authentication failure."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(status_code=401)

            result = await nextcloud_integration.authenticate("user", "wrong")

            assert result.success is False

    @pytest.mark.asyncio
    async def test_check_status_connected(self, nc_env):
        """Test Nextcloud status check when connected."""
        from integrations.nextcloud import nextcloud_integration

        with patch('httpx.AsyncClient') as mock_client:
            mock_ctx = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_ctx
            mock_ctx.get.return_value = make_mock_response(status_code=200)

            result = await nextcloud_integration.check_status()

            assert result.connected is True
            assert result.server_name == "Nextcloud"

    def test_parse_ocs_response_success(self, nc_env):
        """Test OCS XML parsing for success response."""
        from integrations.nextcloud import nextcloud_integration

        xml = """<?xml version="1.0"?>
        <ocs><meta><statuscode>100</statuscode></meta></ocs>"""

        success, message = nextcloud_integration._parse_ocs_response(xml)

        assert success is True
        assert message == "OK"

    def test_parse_ocs_response_failure(self, nc_env):
        """Test OCS XML parsing for failure response."""
        from integrations.nextcloud import nextcloud_integration

        xml = """<?xml version="1.0"?>
        <ocs><meta><statuscode>102</statuscode><message>User already exists</message></meta></ocs>"""

        success, message = nextcloud_integration._parse_ocs_response(xml)

        assert success is False
        assert message == "User already exists"

    def test_parse_ocs_response_invalid_xml(self, nc_env):
        """Test OCS XML parsing with invalid XML."""
        from integrations.nextcloud import nextcloud_integration

        success, message = nextcloud_integration._parse_ocs_response("not xml")

        assert success is False
        assert "Invalid XML" in message
