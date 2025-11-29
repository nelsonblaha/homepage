"""
Integration tests for Mattermost user operations.

These tests require a running Mattermost test container with admin token.
The token must be created via System Console > Integrations > Bot Accounts
or by using the API with an admin session.

Run: pytest tests/integration/test_mattermost.py -v
"""

import os
import pytest
import httpx

# Skip all tests if no token configured
pytestmark = pytest.mark.skipif(
    not os.environ.get('MATTERMOST_TEST_TOKEN'),
    reason="MATTERMOST_TEST_TOKEN not set - Mattermost needs initial setup"
)


class TestMattermostUserOperations:
    """Test Mattermost user create/delete/authenticate operations."""

    @pytest.fixture
    def headers(self, mattermost_token):
        """Get Mattermost API headers."""
        return {
            "Authorization": f"Bearer {mattermost_token}",
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_check_status(self, wait_for_services, mattermost_url, headers):
        """Test that Mattermost reports as connected."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{mattermost_url}/api/v4/system/ping",
                headers=headers,
                timeout=10.0
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_create_user(self, wait_for_services, mattermost_url, headers,
                                unique_username, unique_email, cleanup_users):
        """Test creating a Mattermost user."""
        # Mattermost requires lowercase alphanumeric usernames
        mm_username = unique_username.lower().replace('-', '_')

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{mattermost_url}/api/v4/users",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": mm_username,
                    "password": "TestPassword123!",
                    "nickname": unique_username
                },
                timeout=10.0
            )

        assert resp.status_code in (200, 201), f"Create failed: {resp.text}"
        data = resp.json()

        assert "id" in data
        assert data.get("username") == mm_username
        cleanup_users.append(('mattermost', data["id"]))

    @pytest.mark.asyncio
    async def test_create_user_and_add_to_team(self, wait_for_services, mattermost_url,
                                                headers, mattermost_team_id,
                                                unique_username, unique_email,
                                                cleanup_users):
        """Test creating a Mattermost user and adding to team."""
        if not mattermost_team_id:
            pytest.skip("MATTERMOST_TEST_TEAM_ID not set")

        mm_username = unique_username.lower().replace('-', '_')

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{mattermost_url}/api/v4/users",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": mm_username,
                    "password": "TestPassword123!"
                },
                timeout=10.0
            )

            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]
            cleanup_users.append(('mattermost', user_id))

            # Add to team
            team_resp = await client.post(
                f"{mattermost_url}/api/v4/teams/{mattermost_team_id}/members",
                headers=headers,
                json={"team_id": mattermost_team_id, "user_id": user_id},
                timeout=10.0
            )

        assert team_resp.status_code in (200, 201), f"Add to team failed: {team_resp.text}"

    @pytest.mark.asyncio
    async def test_delete_user(self, wait_for_services, mattermost_url, headers,
                                unique_username, unique_email):
        """Test creating and deleting a Mattermost user."""
        mm_username = unique_username.lower().replace('-', '_')

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{mattermost_url}/api/v4/users",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": mm_username,
                    "password": "TestPassword123!"
                },
                timeout=10.0
            )

            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]

            # Delete user (Mattermost uses "deactivate" by default)
            delete_resp = await client.delete(
                f"{mattermost_url}/api/v4/users/{user_id}",
                headers=headers,
                timeout=10.0
            )

        assert delete_resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_authenticate_user(self, wait_for_services, mattermost_url, headers,
                                      unique_username, unique_email, cleanup_users):
        """Test authenticating a Mattermost user."""
        password = "TestPassword123!"
        mm_username = unique_username.lower().replace('-', '_')

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{mattermost_url}/api/v4/users",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": mm_username,
                    "password": password
                },
                timeout=10.0
            )
            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]
            cleanup_users.append(('mattermost', user_id))

            # Authenticate (can use email or username as login_id)
            auth_resp = await client.post(
                f"{mattermost_url}/api/v4/users/login",
                json={"login_id": unique_email, "password": password},
                timeout=10.0
            )

        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
        # Mattermost returns token in header
        assert "Token" in auth_resp.headers

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, wait_for_services, mattermost_url, headers,
                                         unique_username, unique_email, cleanup_users):
        """Test looking up a user by username."""
        mm_username = unique_username.lower().replace('-', '_')

        async with httpx.AsyncClient() as client:
            # Create user
            create_resp = await client.post(
                f"{mattermost_url}/api/v4/users",
                headers=headers,
                json={
                    "email": unique_email,
                    "username": mm_username,
                    "password": "TestPassword123!"
                },
                timeout=10.0
            )
            assert create_resp.status_code in (200, 201)
            user_id = create_resp.json()["id"]
            cleanup_users.append(('mattermost', user_id))

            # Look up by username
            get_resp = await client.get(
                f"{mattermost_url}/api/v4/users/username/{mm_username}",
                headers=headers,
                timeout=10.0
            )

        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == user_id
        assert data["username"] == mm_username
