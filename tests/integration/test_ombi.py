"""
Integration tests for Ombi user operations.

These tests require a running Ombi test container and API key.
The API key can be found in Ombi settings after initial setup.

Run: pytest tests/integration/test_ombi.py -v
"""

import os
import pytest
import httpx

# Skip all tests if no API key configured
pytestmark = pytest.mark.skipif(
    not os.environ.get('OMBI_TEST_API_KEY'),
    reason="OMBI_TEST_API_KEY not set - Ombi needs initial setup"
)


class TestOmbiUserOperations:
    """Test Ombi user create/delete/authenticate operations."""

    @pytest.fixture
    def headers(self, ombi_api_key):
        """Get Ombi API headers."""
        return {
            "ApiKey": ombi_api_key,
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_check_status(self, wait_for_services, ombi_url, headers):
        """Test that Ombi reports as connected."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ombi_url}/api/v1/Status",
                headers=headers,
                timeout=10.0
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_user(self, wait_for_services, ombi_url, headers,
                                unique_username, cleanup_users):
        """Test creating an Ombi user with permissions."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ombi_url}/api/v1/Identity",
                headers=headers,
                json={
                    "userName": unique_username,
                    "password": "TestPassword123!",
                    "claims": [
                        {"value": "RequestMovie", "enabled": True},
                        {"value": "RequestTv", "enabled": True}
                    ]
                },
                timeout=10.0
            )

        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"

        # Ombi may not return ID directly, fetch user list
        async with httpx.AsyncClient() as client:
            users_resp = await client.get(
                f"{ombi_url}/api/v1/Identity/Users",
                headers=headers,
                timeout=10.0
            )

        assert users_resp.status_code == 200
        users = users_resp.json()
        user = next((u for u in users if u.get("userName") == unique_username), None)

        assert user is not None, f"User {unique_username} not found in user list"
        cleanup_users.append(('ombi', user["id"]))

    @pytest.mark.asyncio
    async def test_delete_user(self, wait_for_services, ombi_url, headers,
                                unique_username):
        """Test creating and deleting an Ombi user."""
        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{ombi_url}/api/v1/Identity",
                headers=headers,
                json={
                    "userName": unique_username,
                    "password": "TestPassword123!",
                    "claims": []
                },
                timeout=10.0
            )
            assert create_resp.status_code in (200, 201)

            # Get user ID
            users_resp = await client.get(
                f"{ombi_url}/api/v1/Identity/Users",
                headers=headers,
                timeout=10.0
            )
            users = users_resp.json()
            user = next((u for u in users if u.get("userName") == unique_username), None)
            assert user is not None
            user_id = user["id"]

            # Delete user
            delete_resp = await client.delete(
                f"{ombi_url}/api/v1/Identity/{user_id}",
                headers=headers,
                timeout=10.0
            )

        assert delete_resp.status_code in (200, 204)

        # Verify user is gone
        async with httpx.AsyncClient() as client:
            users_resp = await client.get(
                f"{ombi_url}/api/v1/Identity/Users",
                headers=headers,
                timeout=10.0
            )
        users = users_resp.json()
        user = next((u for u in users if u.get("userName") == unique_username), None)
        assert user is None, "User still exists after deletion"

    @pytest.mark.asyncio
    async def test_authenticate_user(self, wait_for_services, ombi_url, headers,
                                      unique_username, cleanup_users):
        """Test authenticating an Ombi user."""
        password = "TestPassword123!"

        async with httpx.AsyncClient() as client:
            # Create user
            await client.post(
                f"{ombi_url}/api/v1/Identity",
                headers=headers,
                json={
                    "userName": unique_username,
                    "password": password,
                    "claims": []
                },
                timeout=10.0
            )

            # Get user ID for cleanup
            users_resp = await client.get(
                f"{ombi_url}/api/v1/Identity/Users",
                headers=headers,
                timeout=10.0
            )
            users = users_resp.json()
            user = next((u for u in users if u.get("userName") == unique_username), None)
            if user:
                cleanup_users.append(('ombi', user["id"]))

            # Authenticate
            auth_resp = await client.post(
                f"{ombi_url}/api/v1/Token",
                headers={"Content-Type": "application/json"},
                json={"username": unique_username, "password": password},
                timeout=10.0
            )

        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
        data = auth_resp.json()
        assert "access_token" in data
