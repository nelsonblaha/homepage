"""Tests for access request routes and business logic."""
import pytest
import asyncio
import importlib
from fastapi.testclient import TestClient


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """Set up mock environment variables."""
    db_path = str(tmp_path / "test-requests.db")
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
def setup_friend_and_service(auth_client):
    """Set up a friend and a service for testing."""
    # Create service
    svc_resp = auth_client.post("/api/services", json={
        "name": "Test Service",
        "url": "https://test.local",
        "subdomain": "test"
    })
    service = svc_resp.json()

    # Create friend
    friend_resp = auth_client.post("/api/friends", json={"name": "TestFriend"})
    friend = friend_resp.json()

    return {"service": service, "friend": friend}


# =============================================================================
# CREATE ACCESS REQUEST TESTS
# =============================================================================

class TestCreateAccessRequest:
    """Tests for POST /api/access-requests."""

    def test_requires_friend_auth(self, client):
        """Test request creation requires friend authentication."""
        response = client.post("/api/access-requests?service=test")
        assert response.status_code == 401

    def test_invalid_friend_token(self, client):
        """Test request creation with invalid token."""
        client.cookies.set("friend_token", "invalid_token_123")
        response = client.post("/api/access-requests?service=test")
        assert response.status_code == 401

    def test_service_not_found(self, auth_client, setup_friend_and_service):
        """Test request for non-existent service."""
        friend = setup_friend_and_service["friend"]
        auth_client.cookies.set("friend_token", friend["token"])

        response = auth_client.post("/api/access-requests?service=nonexistent")
        assert response.status_code == 404
        assert "Service not found" in response.json()["detail"]

    def test_successful_request_creation(self, auth_client, setup_friend_and_service):
        """Test successful access request creation."""
        friend = setup_friend_and_service["friend"]
        auth_client.cookies.set("friend_token", friend["token"])

        response = auth_client.post("/api/access-requests?service=test")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_duplicate_request_rejected(self, auth_client, setup_friend_and_service):
        """Test duplicate pending request is rejected."""
        friend = setup_friend_and_service["friend"]
        auth_client.cookies.set("friend_token", friend["token"])

        # First request
        auth_client.post("/api/access-requests?service=test")

        # Duplicate request
        response = auth_client.post("/api/access-requests?service=test")
        assert response.status_code == 400
        assert "already pending" in response.json()["detail"]

    def test_already_has_access(self, auth_client, setup_friend_and_service):
        """Test request rejected when already has access."""
        friend = setup_friend_and_service["friend"]
        service = setup_friend_and_service["service"]

        # Grant access first
        auth_client.put(
            f"/api/friends/{friend['id']}",
            json={"service_ids": [service["id"]]}
        )

        # Try to request access
        auth_client.cookies.set("friend_token", friend["token"])
        response = auth_client.post("/api/access-requests?service=test")
        assert response.status_code == 400
        assert "Already have access" in response.json()["detail"]


# =============================================================================
# LIST ACCESS REQUESTS TESTS
# =============================================================================

class TestListAccessRequests:
    """Tests for GET /api/access-requests."""

    def test_requires_admin_auth(self, client):
        """Test listing requests requires admin authentication."""
        response = client.get("/api/access-requests")
        assert response.status_code == 401

    def test_returns_empty_list(self, auth_client):
        """Test returns empty list when no requests."""
        response = auth_client.get("/api/access-requests")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_pending_requests(self, auth_client, setup_friend_and_service):
        """Test returns pending requests with friend and service info."""
        friend = setup_friend_and_service["friend"]

        # Create a request
        auth_client.cookies.set("friend_token", friend["token"])
        auth_client.post("/api/access-requests?service=test")

        # List requests
        response = auth_client.get("/api/access-requests")
        assert response.status_code == 200
        requests = response.json()
        assert len(requests) == 1
        assert requests[0]["friend_name"] == "TestFriend"
        assert requests[0]["service_name"] == "Test Service"
        assert requests[0]["status"] == "pending"


# =============================================================================
# APPROVE ACCESS REQUEST TESTS
# =============================================================================

class TestApproveAccessRequest:
    """Tests for POST /api/access-requests/{id}/approve."""

    def test_requires_admin_auth(self, client):
        """Test approving requires admin authentication."""
        response = client.post("/api/access-requests/1/approve")
        assert response.status_code == 401

    def test_request_not_found(self, auth_client):
        """Test approving non-existent request."""
        response = auth_client.post("/api/access-requests/9999/approve")
        assert response.status_code == 404

    def test_successful_approval(self, auth_client, setup_friend_and_service):
        """Test successful request approval grants access."""
        friend = setup_friend_and_service["friend"]
        service = setup_friend_and_service["service"]

        # Create request
        auth_client.cookies.set("friend_token", friend["token"])
        auth_client.post("/api/access-requests?service=test")

        # Get request ID
        requests = auth_client.get("/api/access-requests").json()
        request_id = requests[0]["id"]

        # Approve
        response = auth_client.post(f"/api/access-requests/{request_id}/approve")
        assert response.status_code == 200

        # Verify friend now has access by listing all friends
        friends = auth_client.get("/api/friends").json()
        target_friend = next(f for f in friends if f["id"] == friend["id"])
        service_ids = [s["id"] for s in target_friend.get("services", [])]
        assert service["id"] in service_ids


# =============================================================================
# DENY ACCESS REQUEST TESTS
# =============================================================================

class TestDenyAccessRequest:
    """Tests for POST /api/access-requests/{id}/deny."""

    def test_requires_admin_auth(self, client):
        """Test denying requires admin authentication."""
        response = client.post("/api/access-requests/1/deny")
        assert response.status_code == 401

    def test_successful_denial(self, auth_client, setup_friend_and_service):
        """Test successful request denial."""
        friend = setup_friend_and_service["friend"]

        # Create request
        auth_client.cookies.set("friend_token", friend["token"])
        auth_client.post("/api/access-requests?service=test")

        # Get request ID
        requests = auth_client.get("/api/access-requests").json()
        request_id = requests[0]["id"]

        # Deny
        response = auth_client.post(f"/api/access-requests/{request_id}/deny")
        assert response.status_code == 200

        # Verify request no longer in pending list
        pending = auth_client.get("/api/access-requests").json()
        assert len(pending) == 0


# =============================================================================
# REQUEST ACCESS INFO TESTS
# =============================================================================

class TestRequestAccessInfo:
    """Tests for GET /api/request-access-info."""

    def test_returns_service_info(self, auth_client, setup_friend_and_service):
        """Test returns service info."""
        response = auth_client.get("/api/request-access-info?service=test")
        assert response.status_code == 200
        data = response.json()
        assert data["service"]["name"] == "Test Service"

    def test_returns_friend_name_when_authenticated(
        self, auth_client, setup_friend_and_service
    ):
        """Test returns friend name when authenticated."""
        friend = setup_friend_and_service["friend"]
        auth_client.cookies.set("friend_token", friend["token"])

        response = auth_client.get("/api/request-access-info?service=test")
        assert response.status_code == 200
        data = response.json()
        assert data["friend_name"] == "TestFriend"

    def test_shows_pending_request_status(self, auth_client, setup_friend_and_service):
        """Test shows pending request status."""
        friend = setup_friend_and_service["friend"]
        auth_client.cookies.set("friend_token", friend["token"])

        # Create request
        auth_client.post("/api/access-requests?service=test")

        # Check info
        response = auth_client.get("/api/request-access-info?service=test")
        assert response.status_code == 200
        data = response.json()
        assert data["has_pending_request"] is True

    def test_service_not_found_returns_null(self, auth_client):
        """Test returns null service when not found."""
        response = auth_client.get("/api/request-access-info?service=nonexistent")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] is None
