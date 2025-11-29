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


class TestHomepageOverseerrIntegration:
    """
    End-to-end tests for Homepage's Overseerr user management.

    These tests verify the full flow through Homepage's API, including:
    - Creating friends with Overseerr access
    - Automatic account creation in Overseerr
    - Revoking access and automatic account deletion

    This is a regression test for the service revoke bug (KeyError: 0)
    when row_factory returned dicts instead of tuples.
    """

    @pytest.fixture
    def homepage_url(self):
        """Get the Homepage URL (assumes running on host)."""
        return os.environ.get('HOMEPAGE_TEST_URL', 'http://127.0.0.1:3000')

    @pytest.fixture
    def admin_password(self):
        """Get the Homepage admin password for testing."""
        return os.environ.get('HOMEPAGE_ADMIN_PASSWORD', 'test')

    @pytest.fixture
    def homepage_headers(self, admin_password):
        """Get headers for authenticated Homepage requests."""
        return {
            "Authorization": f"Bearer {admin_password}",
            "Content-Type": "application/json"
        }

    @pytest.mark.asyncio
    async def test_service_revoke_deletes_overseerr_user(
        self, wait_for_services, homepage_url, homepage_headers,
        overseerr_url, overseerr_api_key, unique_username
    ):
        """
        Test that removing Overseerr from a friend deletes their Overseerr account.

        This is the full flow that the X button triggers:
        1. Create friend with Overseerr access
        2. Verify Overseerr user was created
        3. Remove Overseerr from friend's services
        4. Verify Overseerr user was deleted
        """
        overseerr_headers = {
            "X-Api-Key": overseerr_api_key,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Get Overseerr service ID from Homepage
            services_resp = await client.get(
                f"{homepage_url}/api/services",
                headers=homepage_headers
            )
            assert services_resp.status_code == 200, f"Get services failed: {services_resp.text}"
            services = services_resp.json()
            overseerr_service = next((s for s in services if s['name'].lower() == 'overseerr'), None)
            assert overseerr_service, "Overseerr service not found in Homepage"
            overseerr_service_id = overseerr_service['id']

            # Step 2: Create a friend with Overseerr access
            create_resp = await client.post(
                f"{homepage_url}/api/friends",
                headers=homepage_headers,
                json={
                    "name": unique_username,
                    "service_ids": [overseerr_service_id]
                }
            )
            assert create_resp.status_code == 200, f"Create friend failed: {create_resp.text}"
            friend = create_resp.json()
            friend_id = friend['id']

            try:
                # Step 3: Verify Overseerr user was created
                # The friend should have overseerr_user_id set
                friend_resp = await client.get(
                    f"{homepage_url}/api/friends",
                    headers=homepage_headers
                )
                friends = friend_resp.json()
                our_friend = next((f for f in friends if f['id'] == friend_id), None)
                assert our_friend, "Friend not found after creation"
                overseerr_user_id = our_friend.get('overseerr_user_id')
                assert overseerr_user_id, f"Overseerr user not created: {our_friend}"

                # Verify user exists in Overseerr
                user_check_resp = await client.get(
                    f"{overseerr_url}/api/v1/user/{overseerr_user_id}",
                    headers=overseerr_headers
                )
                assert user_check_resp.status_code == 200, \
                    f"Overseerr user {overseerr_user_id} not found in Overseerr"

                # Step 4: Remove Overseerr from friend's services (the X button)
                # This is PUT /api/friends/{id} with updated service_ids
                current_service_ids = [s['id'] for s in our_friend.get('services', [])]
                new_service_ids = [sid for sid in current_service_ids if sid != overseerr_service_id]

                update_resp = await client.put(
                    f"{homepage_url}/api/friends/{friend_id}",
                    headers=homepage_headers,
                    json={"service_ids": new_service_ids}
                )
                assert update_resp.status_code == 200, \
                    f"Remove Overseerr service failed: {update_resp.text}"

                # Step 5: Verify Overseerr user was deleted
                deleted_check_resp = await client.get(
                    f"{overseerr_url}/api/v1/user/{overseerr_user_id}",
                    headers=overseerr_headers
                )
                assert deleted_check_resp.status_code == 404, \
                    f"Overseerr user should be deleted but still exists: {deleted_check_resp.status_code}"

            finally:
                # Cleanup: Delete the friend from Homepage
                await client.delete(
                    f"{homepage_url}/api/friends/{friend_id}?delete_accounts=false",
                    headers=homepage_headers
                )
