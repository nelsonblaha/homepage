"""
Integration tests for Jellyfin user operations.

These tests require a running Jellyfin test container and API key.
The API key must be created manually after initial Jellyfin setup.

Run: pytest tests/integration/test_jellyfin.py -v
"""

import os
import pytest
import httpx

# Skip all tests if no API key configured
pytestmark = pytest.mark.skipif(
    not os.environ.get('JELLYFIN_TEST_API_KEY'),
    reason="JELLYFIN_TEST_API_KEY not set - Jellyfin needs initial setup"
)


class TestJellyfinUserOperations:
    """Test Jellyfin user create/delete/authenticate operations."""

    @pytest.fixture
    def headers(self, jellyfin_api_key):
        """Get Jellyfin API headers."""
        return {
            "X-Emby-Token": jellyfin_api_key,
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_check_status(self, wait_for_services, jellyfin_url, headers):
        """Test that Jellyfin reports as connected."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{jellyfin_url}/System/Info",
                headers=headers,
                timeout=10.0
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "ServerName" in data or "Id" in data

    @pytest.mark.asyncio
    async def test_create_user(self, wait_for_services, jellyfin_url, headers,
                                unique_username, cleanup_users):
        """Test creating a Jellyfin user."""
        async with httpx.AsyncClient() as client:
            # Create user
            resp = await client.post(
                f"{jellyfin_url}/Users/New",
                headers=headers,
                json={"Name": unique_username},
                timeout=10.0
            )

        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        data = resp.json()

        assert "Id" in data
        assert data.get("Name") == unique_username

        # Track for cleanup
        cleanup_users.append(('jellyfin', data["Id"]))

    @pytest.mark.asyncio
    async def test_create_user_with_password(self, wait_for_services, jellyfin_url,
                                              headers, unique_username, cleanup_users):
        """Test creating a Jellyfin user and setting password."""
        async with httpx.AsyncClient() as client:
            # Create user
            resp = await client.post(
                f"{jellyfin_url}/Users/New",
                headers=headers,
                json={"Name": unique_username},
                timeout=10.0
            )

            assert resp.status_code in (200, 201)
            data = resp.json()
            user_id = data["Id"]
            cleanup_users.append(('jellyfin', user_id))

            # Set password
            pwd_resp = await client.post(
                f"{jellyfin_url}/Users/{user_id}/Password",
                headers=headers,
                json={"NewPw": "TestPassword123!"},
                timeout=10.0
            )

        assert pwd_resp.status_code in (200, 204), f"Set password failed: {pwd_resp.text}"

    @pytest.mark.asyncio
    async def test_delete_user(self, wait_for_services, jellyfin_url, headers,
                                unique_username):
        """Test creating and deleting a Jellyfin user."""
        async with httpx.AsyncClient() as client:
            # Create user first
            create_resp = await client.post(
                f"{jellyfin_url}/Users/New",
                headers=headers,
                json={"Name": unique_username},
                timeout=10.0
            )

            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["Id"]

            # Delete user
            delete_resp = await client.delete(
                f"{jellyfin_url}/Users/{user_id}",
                headers=headers,
                timeout=10.0
            )

        assert delete_resp.status_code in (200, 204)

        # Verify user is gone
        async with httpx.AsyncClient() as client:
            get_resp = await client.get(
                f"{jellyfin_url}/Users/{user_id}",
                headers=headers,
                timeout=10.0
            )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_authenticate_user(self, wait_for_services, jellyfin_url, headers,
                                      unique_username, cleanup_users):
        """Test authenticating a Jellyfin user."""
        password = "TestPassword123!"

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{jellyfin_url}/Users/New",
                headers=headers,
                json={"Name": unique_username},
                timeout=10.0
            )
            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["Id"]
            cleanup_users.append(('jellyfin', user_id))

            # Set password
            await client.post(
                f"{jellyfin_url}/Users/{user_id}/Password",
                headers=headers,
                json={"NewPw": password},
                timeout=10.0
            )

            # Authenticate
            auth_resp = await client.post(
                f"{jellyfin_url}/Users/AuthenticateByName",
                headers={
                    "Content-Type": "application/json",
                    "X-Emby-Authorization": 'MediaBrowser Client="Test", Device="Test", DeviceId="test-device", Version="1.0"'
                },
                json={"Username": unique_username, "Pw": password},
                timeout=10.0
            )

        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
        data = auth_resp.json()
        assert "AccessToken" in data
        assert "User" in data
        assert data["User"]["Id"] == user_id
