"""Tests for integration registry."""
import pytest


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", ".test.local")
    # Set minimal config so integrations initialize
    monkeypatch.setenv("OMBI_URL", "http://localhost:3579")
    monkeypatch.setenv("OMBI_API_KEY", "testkey")
    monkeypatch.setenv("JELLYFIN_URL", "http://localhost:8096")
    monkeypatch.setenv("JELLYFIN_API_KEY", "testkey")


# =============================================================================
# REGISTRY FUNCTION TESTS
# =============================================================================

def test_get_integration_returns_integration(mock_env):
    """Test get_integration returns an integration instance."""
    from integrations.registry import get_integration

    integration = get_integration("ombi")
    assert integration is not None
    assert integration.SERVICE_NAME == "ombi"


def test_get_integration_case_insensitive(mock_env):
    """Test get_integration is case insensitive."""
    from integrations.registry import get_integration

    assert get_integration("OMBI") is not None
    assert get_integration("Ombi") is not None
    assert get_integration("ombi") is not None


def test_get_integration_returns_none_for_unknown(mock_env):
    """Test get_integration returns None for unknown services."""
    from integrations.registry import get_integration

    assert get_integration("nonexistent") is None
    assert get_integration("foobar") is None


def test_get_all_integrations(mock_env):
    """Test get_all_integrations returns dict of integrations."""
    from integrations.registry import get_all_integrations

    integrations = get_all_integrations()
    assert isinstance(integrations, dict)
    assert len(integrations) > 0
    # Should have at least ombi and jellyfin
    assert "ombi" in integrations
    assert "jellyfin" in integrations


def test_is_managed_service(mock_env):
    """Test is_managed_service returns correct values."""
    from integrations.registry import is_managed_service

    assert is_managed_service("ombi") is True
    assert is_managed_service("jellyfin") is True
    assert is_managed_service("nonexistent") is False


# =============================================================================
# DATABASE COLUMN MAPPING TESTS
# =============================================================================

def test_service_db_columns_has_expected_services():
    """Test SERVICE_DB_COLUMNS has all expected services."""
    from integrations.registry import SERVICE_DB_COLUMNS

    expected = ["plex", "ombi", "jellyfin", "nextcloud", "overseerr", "mattermost", "chat"]
    for service in expected:
        assert service in SERVICE_DB_COLUMNS, f"{service} missing from SERVICE_DB_COLUMNS"


def test_service_db_columns_structure():
    """Test SERVICE_DB_COLUMNS entries are tuples of two strings."""
    from integrations.registry import SERVICE_DB_COLUMNS

    for slug, cols in SERVICE_DB_COLUMNS.items():
        assert isinstance(cols, tuple), f"{slug} columns should be tuple"
        assert len(cols) == 2, f"{slug} should have exactly 2 columns"
        assert isinstance(cols[0], str), f"{slug} user_id column should be string"
        assert isinstance(cols[1], str), f"{slug} password column should be string"


def test_get_db_columns_returns_tuple(mock_env):
    """Test get_db_columns returns correct tuple."""
    from integrations.registry import get_db_columns

    cols = get_db_columns("ombi")
    assert cols == ("ombi_user_id", "ombi_password")

    cols = get_db_columns("jellyfin")
    assert cols == ("jellyfin_user_id", "jellyfin_password")


def test_get_db_columns_case_insensitive(mock_env):
    """Test get_db_columns is case insensitive."""
    from integrations.registry import get_db_columns

    assert get_db_columns("OMBI") == ("ombi_user_id", "ombi_password")
    assert get_db_columns("Ombi") == ("ombi_user_id", "ombi_password")


def test_get_db_columns_returns_empty_for_unknown(mock_env):
    """Test get_db_columns returns empty strings for unknown services."""
    from integrations.registry import get_db_columns

    assert get_db_columns("nonexistent") == ("", "")


def test_chat_alias(mock_env):
    """Test chat is an alias for mattermost."""
    from integrations.registry import get_db_columns, SERVICE_DB_COLUMNS

    assert SERVICE_DB_COLUMNS["chat"] == SERVICE_DB_COLUMNS["mattermost"]
    assert get_db_columns("chat") == get_db_columns("mattermost")


# =============================================================================
# INTEGRATION INSTANCE TESTS
# =============================================================================

def test_integrations_have_required_attributes(mock_env):
    """Test all registered integrations have required attributes."""
    from integrations.registry import get_all_integrations

    for slug, integration in get_all_integrations().items():
        if slug == "chat":  # Skip alias
            continue
        assert hasattr(integration, "SERVICE_NAME"), f"{slug} missing SERVICE_NAME"
        assert hasattr(integration, "ENV_PREFIX"), f"{slug} missing ENV_PREFIX"
        assert hasattr(integration, "create_user"), f"{slug} missing create_user"
        assert hasattr(integration, "delete_user"), f"{slug} missing delete_user"
        assert hasattr(integration, "check_status"), f"{slug} missing check_status"
        assert hasattr(integration, "is_configured"), f"{slug} missing is_configured"


def test_integrations_service_name_matches_slug(mock_env):
    """Test integration SERVICE_NAME matches registry slug."""
    from integrations.registry import get_all_integrations

    for slug, integration in get_all_integrations().items():
        if slug == "chat":  # Skip alias
            continue
        # SERVICE_NAME should match slug (lowercase)
        assert integration.SERVICE_NAME.lower() == slug.lower(), \
            f"{slug} SERVICE_NAME '{integration.SERVICE_NAME}' doesn't match"
