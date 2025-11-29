"""Tests for account management service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
    monkeypatch.setenv("OMBI_URL", "http://localhost:3579")
    monkeypatch.setenv("OMBI_API_KEY", "testkey")
    monkeypatch.setenv("JELLYFIN_URL", "http://localhost:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "testkey")


# =============================================================================
# MANAGED_SERVICES EXPORT TESTS
# =============================================================================

def test_managed_services_exported(mock_env):
    """Test MANAGED_SERVICES dict is exported."""
    from services.accounts import MANAGED_SERVICES

    assert isinstance(MANAGED_SERVICES, dict)
    assert "ombi" in MANAGED_SERVICES
    assert "jellyfin" in MANAGED_SERVICES
    assert "overseerr" in MANAGED_SERVICES


def test_managed_services_maps_to_columns(mock_env):
    """Test MANAGED_SERVICES maps slugs to user_id columns."""
    from services.accounts import MANAGED_SERVICES

    assert MANAGED_SERVICES["ombi"] == "ombi_user_id"
    assert MANAGED_SERVICES["jellyfin"] == "jellyfin_user_id"
    assert MANAGED_SERVICES["plex"] == "plex_user_id"


# =============================================================================
# HANDLE_SERVICE_GRANT TESTS
# =============================================================================

class TestHandleServiceGrant:
    """Tests for handle_service_grant function."""

    @pytest.mark.asyncio
    async def test_grant_plex_special_handling(self, mock_env):
        """Test Plex uses special handling (not registry)."""
        from services.accounts import handle_service_grant

        mock_db = AsyncMock()

        with patch('services.accounts.create_plex_user') as mock_plex:
            mock_plex.return_value = {"id": "plex-123", "pin": "1234"}

            result = await handle_service_grant(1, "TestUser", "plex", mock_db)

            mock_plex.assert_called_once_with("TestUser")
            assert result["service"] == "plex"
            assert result["success"] is True
            assert result["action"] == "created"
            # Should update DB with plex_user_id
            mock_db.execute.assert_called()

    @pytest.mark.asyncio
    async def test_grant_plex_failure(self, mock_env):
        """Test Plex grant failure returns error."""
        from services.accounts import handle_service_grant

        mock_db = AsyncMock()

        with patch('services.accounts.create_plex_user') as mock_plex:
            mock_plex.return_value = None

            result = await handle_service_grant(1, "TestUser", "plex", mock_db)

            assert result["success"] is False
            assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_grant_ombi_uses_registry(self, mock_env):
        """Test Ombi uses registry-based handling."""
        from services.accounts import handle_service_grant

        mock_db = AsyncMock()

        with patch('services.accounts.handle_service_grant_v2') as mock_v2:
            mock_v2.return_value = {
                "service": "ombi",
                "action": "created",
                "success": True,
                "error": None
            }

            result = await handle_service_grant(1, "TestUser", "ombi", mock_db)

            mock_v2.assert_called_once_with(1, "TestUser", "ombi", mock_db)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_grant_case_insensitive(self, mock_env):
        """Test service name is case-insensitive."""
        from services.accounts import handle_service_grant

        mock_db = AsyncMock()

        with patch('services.accounts.handle_service_grant_v2') as mock_v2:
            mock_v2.return_value = {"service": "ombi", "action": "created", "success": True, "error": None}

            # Test uppercase
            await handle_service_grant(1, "Test", "OMBI", mock_db)
            mock_v2.assert_called_with(1, "Test", "ombi", mock_db)

            # Test mixed case
            await handle_service_grant(1, "Test", "Ombi", mock_db)


# =============================================================================
# HANDLE_SERVICE_REVOKE TESTS
# =============================================================================

class TestHandleServiceRevoke:
    """Tests for handle_service_revoke function."""

    @pytest.mark.asyncio
    async def test_revoke_plex_special_handling(self, mock_env):
        """Test Plex revoke uses special handling."""
        from services.accounts import handle_service_revoke

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = ("plex-user-id-123",)
        mock_db.execute.return_value = mock_cursor

        with patch('services.accounts.delete_plex_user') as mock_delete:
            mock_delete.return_value = True

            result = await handle_service_revoke(1, "plex", mock_db)

            mock_delete.assert_called_once_with("plex-user-id-123")
            assert result["success"] is True
            assert result["action"] == "deleted"

    @pytest.mark.asyncio
    async def test_revoke_plex_no_user_id(self, mock_env):
        """Test Plex revoke when no user ID stored."""
        from services.accounts import handle_service_revoke

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = (None,)
        mock_db.execute.return_value = mock_cursor

        result = await handle_service_revoke(1, "plex", mock_db)

        assert result["action"] is None
        # No deletion attempted

    @pytest.mark.asyncio
    async def test_revoke_ombi_uses_registry(self, mock_env):
        """Test Ombi revoke uses registry-based handling."""
        from services.accounts import handle_service_revoke

        mock_db = AsyncMock()

        with patch('services.accounts.handle_service_revoke_v2') as mock_v2:
            mock_v2.return_value = {
                "service": "ombi",
                "action": "deleted",
                "success": True,
                "error": None
            }

            result = await handle_service_revoke(1, "ombi", mock_db)

            mock_v2.assert_called_once_with(1, "ombi", mock_db)
            assert result["success"] is True


# =============================================================================
# REGISTRY HANDLER TESTS
# =============================================================================

class TestRegistryHandlers:
    """Tests for registry-based grant/revoke handlers."""

    @pytest.mark.asyncio
    async def test_grant_v2_creates_user_and_updates_db(self, mock_env):
        """Test handle_service_grant_v2 creates user and updates DB."""
        from integrations.registry import handle_service_grant_v2
        from integrations.base import UserResult

        mock_db = AsyncMock()

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_integration.create_user.return_value = UserResult(
                success=True,
                user_id="user-123",
                username="testuser",
                password="secret123"
            )
            mock_get.return_value = mock_integration

            result = await handle_service_grant_v2(1, "TestUser", "ombi", mock_db)

            mock_integration.create_user.assert_called_once_with("TestUser")
            mock_db.execute.assert_called()
            assert result["success"] is True
            assert result["action"] == "created"

    @pytest.mark.asyncio
    async def test_grant_v2_unknown_service(self, mock_env):
        """Test handle_service_grant_v2 with unknown service."""
        from integrations.registry import handle_service_grant_v2

        mock_db = AsyncMock()

        result = await handle_service_grant_v2(1, "Test", "unknown_service", mock_db)

        assert result["success"] is False
        assert result["action"] is None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_v2_deletes_user_and_clears_db(self, mock_env):
        """Test handle_service_revoke_v2 deletes user and clears DB."""
        from integrations.registry import handle_service_revoke_v2

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = ("user-123",)
        mock_db.execute.return_value = mock_cursor

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_integration.delete_user.return_value = True
            mock_get.return_value = mock_integration

            result = await handle_service_revoke_v2(1, "ombi", mock_db)

            mock_integration.delete_user.assert_called_once_with("user-123")
            assert result["success"] is True
            assert result["action"] == "deleted"

    @pytest.mark.asyncio
    async def test_revoke_v2_no_user_id_stored(self, mock_env):
        """Test handle_service_revoke_v2 when no user ID in DB."""
        from integrations.registry import handle_service_revoke_v2

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = (None,)
        mock_db.execute.return_value = mock_cursor

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_get.return_value = mock_integration

            result = await handle_service_revoke_v2(1, "ombi", mock_db)

            # Should not attempt to delete
            mock_integration.delete_user.assert_not_called()
            assert result["action"] is None

    @pytest.mark.asyncio
    async def test_revoke_v2_with_dict_row_factory(self, mock_env):
        """Test handle_service_revoke_v2 works when row_factory returns dicts.

        This is a regression test for a bug where using row[0] instead of
        row[column_name] caused KeyError when row_factory was set to return dicts.
        """
        from integrations.registry import handle_service_revoke_v2

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        # Simulate dict row (as returned when row_factory is set)
        mock_cursor.fetchone.return_value = {"ombi_user_id": "user-123"}
        mock_db.execute.return_value = mock_cursor

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_integration.delete_user.return_value = True
            mock_get.return_value = mock_integration

            result = await handle_service_revoke_v2(1, "ombi", mock_db)

            mock_integration.delete_user.assert_called_once_with("user-123")
            assert result["success"] is True
            assert result["action"] == "deleted"

    @pytest.mark.asyncio
    async def test_revoke_v2_with_dict_row_empty_user_id(self, mock_env):
        """Test handle_service_revoke_v2 with dict row containing empty user_id."""
        from integrations.registry import handle_service_revoke_v2

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        # Simulate dict row with empty user_id
        mock_cursor.fetchone.return_value = {"ombi_user_id": ""}
        mock_db.execute.return_value = mock_cursor

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_get.return_value = mock_integration

            result = await handle_service_revoke_v2(1, "ombi", mock_db)

            # Should not attempt to delete when user_id is empty
            mock_integration.delete_user.assert_not_called()
            assert result["action"] is None

    @pytest.mark.asyncio
    async def test_revoke_v2_overseerr_with_dict_row(self, mock_env):
        """Test overseerr revoke works with dict rows (real-world scenario)."""
        from integrations.registry import handle_service_revoke_v2

        mock_db = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.fetchone.return_value = {"overseerr_user_id": "16"}
        mock_db.execute.return_value = mock_cursor

        with patch('integrations.registry.get_integration') as mock_get:
            mock_integration = AsyncMock()
            mock_integration.delete_user.return_value = True
            mock_get.return_value = mock_integration

            result = await handle_service_revoke_v2(1, "overseerr", mock_db)

            mock_integration.delete_user.assert_called_once_with("16")
            assert result["success"] is True
