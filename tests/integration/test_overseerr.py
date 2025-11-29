"""
Integration tests for Overseerr user operations.

These tests require a running Overseerr test container and API key.
The API key can be found in Overseerr settings after initial setup.

Run: pytest tests/integration/test_overseerr.py -v
"""

import os
import pytest
import httpx

# Skip all tests if no API key configured
pytestmark = pytest.mark.skipif(
    not os.environ.get('OVERSEERR_TEST_API_KEY'),
    reason="OVERSEERR_TEST_API_KEY not set - Overseerr needs initial setup"
)


class TestOverseerrUserOperations:
    """Test Overseerr user create/delete/authenticate operations."""

    @pytest.fixture
    def headers(self, overseerr_api_key):
        """Get Overseerr API headers."""
        return {
            "X-Api-Key": overseerr_api_key,
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_check_status(self, wait_for_services, overseerr_url, headers):
        """Test that Overseerr reports as connected."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{overseerr_url}/api/v1/status",
                headers=headers,
                timeout=10.0
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_user(self, wait_for_services, overseerr_url, headers,
                                unique_username, unique_email, cleanup_users):
        """Test creating an Overseerr local user."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{overseerr_url}/api/v1/user",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": unique_username,
                    "permissions": 34  # REQUEST + AUTO_APPROVE
                },
                timeout=10.0
            )

        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        data = resp.json()

        assert "id" in data
        cleanup_users.append(('overseerr', str(data["id"])))

    @pytest.mark.asyncio
    async def test_create_user_with_password(self, wait_for_services, overseerr_url,
                                              headers, unique_username, unique_email,
                                              cleanup_users):
        """Test creating an Overseerr user and setting password."""
        password = "TestPassword123!"

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{overseerr_url}/api/v1/user",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": unique_username,
                    "permissions": 34
                },
                timeout=10.0
            )

            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]
            cleanup_users.append(('overseerr', str(user_id)))

            # Set password
            pwd_resp = await client.post(
                f"{overseerr_url}/api/v1/user/{user_id}/settings/password",
                headers=headers,
                json={"newPassword": password},
                timeout=10.0
            )

        assert pwd_resp.status_code in (200, 204), f"Set password failed: {pwd_resp.text}"

    @pytest.mark.asyncio
    async def test_delete_user(self, wait_for_services, overseerr_url, headers,
                                unique_username, unique_email):
        """Test creating and deleting an Overseerr user."""
        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{overseerr_url}/api/v1/user",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": unique_username,
                    "permissions": 2
                },
                timeout=10.0
            )

            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]

            # Delete user
            delete_resp = await client.delete(
                f"{overseerr_url}/api/v1/user/{user_id}",
                headers=headers,
                timeout=10.0
            )

        assert delete_resp.status_code in (200, 204)

        # Verify user is gone
        async with httpx.AsyncClient() as client:
            get_resp = await client.get(
                f"{overseerr_url}/api/v1/user/{user_id}",
                headers=headers,
                timeout=10.0
            )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_authenticate_user(self, wait_for_services, overseerr_url, headers,
                                      unique_username, unique_email, cleanup_users):
        """Test authenticating an Overseerr user."""
        password = "TestPassword123!"

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{overseerr_url}/api/v1/user",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": unique_username,
                    "permissions": 2
                },
                timeout=10.0
            )
            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]
            cleanup_users.append(('overseerr', str(user_id)))

            # Set password
            await client.post(
                f"{overseerr_url}/api/v1/user/{user_id}/settings/password",
                headers=headers,
                json={"newPassword": password},
                timeout=10.0
            )

            # Authenticate (Overseerr uses email for login)
            auth_resp = await client.post(
                f"{overseerr_url}/api/v1/auth/local",
                json={"email": unique_email, "password": password},
                timeout=10.0
            )

        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
        # Overseerr returns session cookie
        assert "connect.sid" in auth_resp.cookies
