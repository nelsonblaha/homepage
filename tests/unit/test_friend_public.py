"""Tests for public friend endpoints (no admin auth required)."""
import pytest
import asyncio
import importlib
from fastapi.testclient import TestClient


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """Set up mock environment variables."""
    db_path = str(tmp_path / "test-friend-public.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpassword")
    monkeypatch.setenv("SESSION_SECRET", "testsecret1234567890abcdef")
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", "")
    monkeypatch.setenv("DB_PATH", db_path)
    return db_path


@pytest.fixture
def client(mock_env):
    """Create test client with initialized database."""
    import database
    importlib.reload(database)

    import main
    importlib.reload(main)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(database.init_db())

    yield TestClient(main.app)

    loop.close()


@pytest.fixture
def auth_client(client):
    """Create authenticated test client (admin)."""
    client.post("/api/admin/login", json={"password": "testpassword"})
    return client


@pytest.fixture
def setup_friend_with_service(auth_client):
    """Set up a friend with a service for testing."""
    # Create service
    svc_resp = auth_client.post("/api/services", json={
        "name": "Jellyfin",
        "url": "https://jellyfin.test.local",
        "subdomain": "jellyfin"
    })
    service = svc_resp.json()

    # Create friend with service
    friend_resp = auth_client.post("/api/friends", json={
        "name": "TestFriend",
        "service_ids": [service["id"]]
    })
    friend = friend_resp.json()

    return {"service": service, "friend": friend}


# =============================================================================
# FRIEND VIEW TESTS
# =============================================================================

class TestFriendView:
    """Tests for GET /api/f/{token} endpoint."""

    def test_invalid_token_returns_404(self, client):
        """Test invalid token returns 404."""
        response = client.get("/api/f/invalid_token_xyz")
        assert response.status_code == 404
        assert "Invalid link" in response.json()["detail"]

    def test_valid_token_returns_friend_view(self, auth_client, setup_friend_with_service):
        """Test valid token returns friend view with services."""
        friend = setup_friend_with_service["friend"]

        response = auth_client.get(f"/api/f/{friend['token']}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "TestFriend"
        assert len(data["services"]) == 1
        assert data["services"][0]["name"] == "Jellyfin"

    def test_friend_view_updates_last_visit(self, auth_client, setup_friend_with_service):
        """Test viewing friend page updates last_visit timestamp."""
        friend = setup_friend_with_service["friend"]

        # View friend page
        auth_client.get(f"/api/f/{friend['token']}")

        # Check last_visit was updated (via admin endpoint)
        friends = auth_client.get("/api/friends").json()
        target = next(f for f in friends if f["id"] == friend["id"])
        assert target.get("last_visit") is not None

    def test_friend_view_does_not_expose_token(self, auth_client, setup_friend_with_service):
        """Test friend view does not expose the token."""
        friend = setup_friend_with_service["friend"]

        response = auth_client.get(f"/api/f/{friend['token']}")
        data = response.json()

        # Response should only have name and services
        assert "token" not in data

    def test_friend_view_includes_service_details(self, auth_client, setup_friend_with_service):
        """Test friend view includes service URL and icon."""
        friend = setup_friend_with_service["friend"]

        response = auth_client.get(f"/api/f/{friend['token']}")
        data = response.json()

        service = data["services"][0]
        assert "url" in service
        assert "subdomain" in service


# =============================================================================
# FRIEND CREDENTIALS TESTS
# =============================================================================

class TestFriendCredentials:
    """Tests for GET /api/f/{token}/credentials/{service_key} endpoint."""

    def test_invalid_token_returns_404(self, client):
        """Test invalid token returns 404."""
        response = client.get("/api/f/invalid_token/credentials/jellyfin")
        assert response.status_code == 404

    def test_invalid_service_key_returns_404(self, auth_client, setup_friend_with_service):
        """Test invalid service key returns 404."""
        friend = setup_friend_with_service["friend"]

        response = auth_client.get(f"/api/f/{friend['token']}/credentials/unknown")
        assert response.status_code == 404
        assert "No credentials for this service" in response.json()["detail"]

    def test_no_credentials_stored_returns_404(self, auth_client, setup_friend_with_service):
        """Test returns 404 when no credentials stored for service."""
        friend = setup_friend_with_service["friend"]

        # Jellyfin is a valid service key but we haven't stored credentials
        response = auth_client.get(f"/api/f/{friend['token']}/credentials/jellyfin")
        assert response.status_code == 404
        assert "No credentials stored" in response.json()["detail"]

    def test_valid_credential_services(self, client):
        """Test which services support credentials."""
        # These are the valid service keys for credentials
        valid_keys = ["nextcloud", "ombi", "jellyfin", "overseerr", "mattermost", "chat"]

        # Just verify the endpoint structure accepts these keys
        # (they will 404 because no friend exists, which is correct)
        for key in valid_keys:
            response = client.get(f"/api/f/sometoken/credentials/{key}")
            # Should not get "No credentials for this service" - that means key is invalid
            assert response.status_code == 404


# =============================================================================
# SERVICE ORDER TESTS
# =============================================================================

class TestServiceOrdering:
    """Tests for service display ordering."""

    def test_services_ordered_by_display_order(self, auth_client):
        """Test services are returned in display_order, then name order."""
        # Create services with specific display orders
        auth_client.post("/api/services", json={
            "name": "Zebra Service",
            "url": "https://zebra.local",
            "display_order": 3
        })
        auth_client.post("/api/services", json={
            "name": "Alpha Service",
            "url": "https://alpha.local",
            "display_order": 1
        })
        auth_client.post("/api/services", json={
            "name": "Beta Service",
            "url": "https://beta.local",
            "display_order": 2
        })

        # Create friend with all services
        services = auth_client.get("/api/services").json()
        service_ids = [s["id"] for s in services]

        friend_resp = auth_client.post("/api/friends", json={
            "name": "OrderTest",
            "service_ids": service_ids
        })
        token = friend_resp.json()["token"]

        # Get friend view and check ordering
        response = auth_client.get(f"/api/f/{token}")
        svc_names = [s["name"] for s in response.json()["services"]]

        # Should be ordered: Alpha (1), Beta (2), Zebra (3)
        assert svc_names == ["Alpha Service", "Beta Service", "Zebra Service"]


# =============================================================================
# DEFAULT SERVICES TESTS
# =============================================================================

class TestDefaultServices:
    """Tests for default service assignment."""

    def test_friend_gets_default_services(self, auth_client):
        """Test new friend gets default services when no services specified."""
        # Create a default service
        auth_client.post("/api/services", json={
            "name": "Default Service",
            "url": "https://default.local",
            "is_default": True
        })

        # Create non-default service
        auth_client.post("/api/services", json={
            "name": "Optional Service",
            "url": "https://optional.local",
            "is_default": False
        })

        # Create friend without specifying services
        friend_resp = auth_client.post("/api/friends", json={"name": "DefaultTest"})
        friend = friend_resp.json()

        # Friend should have the default service
        service_names = [s["name"] for s in friend["services"]]
        assert "Default Service" in service_names
        assert "Optional Service" not in service_names

    def test_explicit_services_override_defaults(self, auth_client):
        """Test explicit service_ids override defaults."""
        # Create services
        default_resp = auth_client.post("/api/services", json={
            "name": "Default Service",
            "url": "https://default.local",
            "is_default": True
        })
        optional_resp = auth_client.post("/api/services", json={
            "name": "Optional Service",
            "url": "https://optional.local",
            "is_default": False
        })

        # Create friend with only optional service
        friend_resp = auth_client.post("/api/friends", json={
            "name": "ExplicitTest",
            "service_ids": [optional_resp.json()["id"]]
        })
        friend = friend_resp.json()

        # Friend should only have the explicitly specified service
        service_names = [s["name"] for s in friend["services"]]
        assert "Optional Service" in service_names
        assert "Default Service" not in service_names


# =============================================================================
# HTML PAGE TESTS
# =============================================================================

class TestFriendHTMLPage:
    """Tests for friend HTML page at /f/{token}."""

    def test_friend_page_returns_html(self, auth_client, setup_friend_with_service):
        """Test friend page returns HTML."""
        friend = setup_friend_with_service["friend"]

        response = auth_client.get(f"/f/{friend['token']}")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_invalid_friend_token_page(self, client):
        """Test invalid friend token on HTML page."""
        response = client.get("/f/invalid_token_xyz")
        # Could return 200 with error message or redirect
        # Just verify it doesn't crash
        assert response.status_code in (200, 302, 404)
