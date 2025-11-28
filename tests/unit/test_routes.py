"""Tests for FastAPI routes using TestClient."""
import pytest
import os
import sys
import asyncio
import importlib
from fastapi.testclient import TestClient


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """Set up mock environment variables."""
    db_path = str(tmp_path / "test-routes.db")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpassword")
    monkeypatch.setenv("SESSION_SECRET", "testsecret1234567890abcdef")
    monkeypatch.setenv("BASE_DOMAIN", "test.local")
    monkeypatch.setenv("COOKIE_DOMAIN", "")
    monkeypatch.setenv("DB_PATH", db_path)
    return db_path


@pytest.fixture
def client(mock_env):
    """Create test client with initialized database."""
    # Force reload of database module to pick up new DB_PATH
    import database
    importlib.reload(database)

    # Also reload main to get fresh app with new database
    import main
    importlib.reload(main)

    # Initialize database synchronously
    loop = asyncio.new_event_loop()
    loop.run_until_complete(database.init_db())

    yield TestClient(main.app)

    loop.close()


# =============================================================================
# ADMIN AUTH TESTS
# =============================================================================

class TestAdminAuth:
    """Tests for admin authentication endpoints."""

    def test_login_success(self, client):
        """Test successful admin login."""
        response = client.post(
            "/api/admin/login",
            json={"password": "testpassword", "remember": False}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "admin_token" in response.cookies

    def test_login_wrong_password(self, client):
        """Test login with wrong password."""
        response = client.post(
            "/api/admin/login",
            json={"password": "wrongpassword"}
        )
        assert response.status_code == 401
        assert "admin_token" not in response.cookies

    def test_login_remember_me(self, client):
        """Test login with remember me option."""
        response = client.post(
            "/api/admin/login",
            json={"password": "testpassword", "remember": True}
        )
        assert response.status_code == 200
        # Cookie should be set with longer expiry
        assert "admin_token" in response.cookies

    def test_verify_not_authenticated(self, client):
        """Test verify returns not authenticated without cookie."""
        response = client.get("/api/admin/verify")
        assert response.status_code == 200
        assert response.json()["authenticated"] is False

    def test_verify_authenticated(self, client):
        """Test verify returns authenticated with valid session."""
        # Login first
        login_resp = client.post(
            "/api/admin/login",
            json={"password": "testpassword"}
        )
        assert login_resp.status_code == 200

        # Verify using the cookie from login
        response = client.get("/api/admin/verify")
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert response.json()["type"] == "admin"

    def test_logout(self, client):
        """Test logout clears session."""
        # Login
        client.post("/api/admin/login", json={"password": "testpassword"})

        # Logout
        response = client.post("/api/admin/logout")
        assert response.status_code == 200

        # Verify no longer authenticated
        verify_resp = client.get("/api/admin/verify")
        assert verify_resp.json()["authenticated"] is False


# =============================================================================
# PROTECTED ENDPOINT TESTS
# =============================================================================

class TestProtectedEndpoints:
    """Tests for endpoints requiring authentication."""

    def test_services_requires_auth(self, client):
        """Test GET /api/services requires authentication."""
        response = client.get("/api/services")
        assert response.status_code == 401

    def test_services_with_auth(self, client):
        """Test GET /api/services with authentication."""
        # Login
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.get("/api/services")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_friends_requires_auth(self, client):
        """Test GET /api/friends requires authentication."""
        response = client.get("/api/friends")
        assert response.status_code == 401

    def test_friends_with_auth(self, client):
        """Test GET /api/friends with authentication."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.get("/api/friends")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


# =============================================================================
# SERVICE CRUD TESTS
# =============================================================================

class TestServiceCRUD:
    """Tests for service CRUD operations."""

    def test_create_service(self, client):
        """Test creating a new service."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.post(
            "/api/services",
            json={
                "name": "Test Service",
                "url": "https://test.local",
                "icon": "server",
                "description": "A test service"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Service"
        assert "id" in data

    def test_create_service_minimal(self, client):
        """Test creating service with minimal fields."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.post(
            "/api/services",
            json={"name": "Minimal", "url": "https://min.local"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Minimal"
        assert data["icon"] == ""  # Default

    def test_delete_service(self, client):
        """Test deleting a service."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        # Create
        create_resp = client.post(
            "/api/services",
            json={"name": "ToDelete", "url": "https://del.local"}
        )
        service_id = create_resp.json()["id"]

        # Delete
        response = client.delete(f"/api/services/{service_id}")
        assert response.status_code == 200

        # Verify gone
        services = client.get("/api/services").json()
        assert not any(s["id"] == service_id for s in services)


# =============================================================================
# FRIEND CRUD TESTS
# =============================================================================

class TestFriendCRUD:
    """Tests for friend CRUD operations."""

    def test_create_friend(self, client):
        """Test creating a new friend."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.post(
            "/api/friends",
            json={"name": "Alice", "service_ids": []}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Alice"
        assert "token" in data
        assert len(data["token"]) > 0

    def test_friend_token_is_unique(self, client):
        """Test each friend gets unique token."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        resp1 = client.post("/api/friends", json={"name": "Friend1"})
        resp2 = client.post("/api/friends", json={"name": "Friend2"})

        assert resp1.json()["token"] != resp2.json()["token"]

    def test_update_friend_name(self, client):
        """Test updating friend name."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        # Create
        create_resp = client.post("/api/friends", json={"name": "OldName"})
        friend_id = create_resp.json()["id"]

        # Update
        response = client.put(
            f"/api/friends/{friend_id}",
            json={"name": "NewName"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "NewName"

    def test_delete_friend(self, client):
        """Test deleting a friend."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        # Create
        create_resp = client.post("/api/friends", json={"name": "ToDelete"})
        friend_id = create_resp.json()["id"]

        # Delete
        response = client.delete(f"/api/friends/{friend_id}")
        assert response.status_code == 200

        # Verify gone
        friends = client.get("/api/friends").json()
        assert not any(f["id"] == friend_id for f in friends)


# =============================================================================
# PUBLIC ENDPOINT TESTS
# =============================================================================

class TestPublicEndpoints:
    """Tests for public endpoints."""

    def test_root_returns_html(self, client):
        """Test root endpoint returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_friend_page_invalid_token(self, client):
        """Test friend page with invalid token."""
        response = client.get("/f/invalid_token_123")
        # Should redirect or show error
        assert response.status_code in (200, 302, 404)


# =============================================================================
# FORWARD AUTH TESTS
# =============================================================================

class TestForwardAuth:
    """Tests for forward auth endpoint."""

    def test_forward_auth_unauthenticated(self, client):
        """Test forward auth returns 401 when not authenticated."""
        response = client.get("/api/auth/verify")
        assert response.status_code == 401

    def test_forward_auth_admin(self, client):
        """Test forward auth returns 200 for admin."""
        client.post("/api/admin/login", json={"password": "testpassword"})

        response = client.get("/api/auth/verify")
        assert response.status_code == 200
        assert "X-Remote-User" in response.headers
        assert response.headers["X-Remote-User"] == "admin"
