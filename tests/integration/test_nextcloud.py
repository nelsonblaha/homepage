"""
Integration tests for Nextcloud user operations.

These tests require a running Nextcloud test container with admin credentials.
The test docker-compose sets up admin/adminpass123 by default.

Run: pytest tests/integration/test_nextcloud.py -v
"""

import pytest
import httpx
import xml.etree.ElementTree as ET


def parse_ocs_response(response_text: str) -> tuple[bool, str]:
    """Parse OCS API XML response. Returns (success, message)."""
    try:
        root = ET.fromstring(response_text)
        status_code = root.find(".//statuscode")
        if status_code is not None and status_code.text == "100":
            return True, "OK"
        message = root.find(".//message")
        return False, message.text if message is not None else "Unknown error"
    except ET.ParseError:
        return False, "Invalid XML response"


class TestNextcloudUserOperations:
    """Test Nextcloud user create/delete/authenticate operations."""

    @pytest.fixture
    def auth(self, nextcloud_admin_user, nextcloud_admin_pass):
        """Get Nextcloud admin auth tuple."""
        return (nextcloud_admin_user, nextcloud_admin_pass)

    @pytest.fixture
    def headers(self):
        """Get Nextcloud OCS API headers."""
        return {
            "OCS-APIRequest": "true",
            "Content-Type": "application/x-www-form-urlencoded"
        }

    @pytest.mark.asyncio
    async def test_check_status(self, wait_for_services, nextcloud_url, auth, headers):
        """Test that Nextcloud reports as connected."""
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{nextcloud_url}/ocs/v1.php/cloud/capabilities",
                auth=auth,
                headers=headers,
                timeout=10.0
            )

        assert resp.status_code == 200
        success, _ = parse_ocs_response(resp.text)
        assert success, f"OCS response indicates failure: {resp.text}"

    @pytest.mark.asyncio
    async def test_create_user(self, wait_for_services, nextcloud_url, auth, headers,
                                unique_username, cleanup_users):
        """Test creating a Nextcloud user."""
        password = "TestPassword123!"

        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{nextcloud_url}/ocs/v1.php/cloud/users",
                auth=auth,
                headers=headers,
                data={
                    "userid": unique_username,
                    "password": password
                },
                timeout=15.0
            )

        assert resp.status_code == 200, f"HTTP error: {resp.status_code}"
        success, message = parse_ocs_response(resp.text)
        assert success, f"Create failed: {message}"

        # Nextcloud uses username as user ID
        cleanup_users.append(('nextcloud', unique_username))

    @pytest.mark.asyncio
    async def test_delete_user(self, wait_for_services, nextcloud_url, auth, headers,
                                unique_username):
        """Test creating and deleting a Nextcloud user."""
        async with httpx.AsyncClient(verify=False) as client:
            # Create user
            create_resp = await client.post(
                f"{nextcloud_url}/ocs/v1.php/cloud/users",
                auth=auth,
                headers=headers,
                data={
                    "userid": unique_username,
                    "password": "TestPassword123!"
                },
                timeout=15.0
            )
            assert create_resp.status_code == 200
            success, message = parse_ocs_response(create_resp.text)
            assert success, f"Create failed: {message}"

            # Delete user
            delete_resp = await client.delete(
                f"{nextcloud_url}/ocs/v1.php/cloud/users/{unique_username}",
                auth=auth,
                headers={"OCS-APIRequest": "true"},
                timeout=10.0
            )

        assert delete_resp.status_code == 200
        success, _ = parse_ocs_response(delete_resp.text)
        assert success

        # Verify user is gone
        async with httpx.AsyncClient(verify=False) as client:
            get_resp = await client.get(
                f"{nextcloud_url}/ocs/v1.php/cloud/users/{unique_username}",
                auth=auth,
                headers={"OCS-APIRequest": "true"},
                timeout=10.0
            )
        # Nextcloud returns 200 with error status for non-existent user
        if get_resp.status_code == 200:
            success, _ = parse_ocs_response(get_resp.text)
            assert not success, "User still exists after deletion"

    @pytest.mark.asyncio
    async def test_authenticate_user(self, wait_for_services, nextcloud_url, auth,
                                      headers, unique_username, cleanup_users):
        """Test authenticating a Nextcloud user."""
        password = "TestPassword123!"

        async with httpx.AsyncClient(verify=False) as client:
            # Create user
            create_resp = await client.post(
                f"{nextcloud_url}/ocs/v1.php/cloud/users",
                auth=auth,
                headers=headers,
                data={
                    "userid": unique_username,
                    "password": password
                },
                timeout=15.0
            )
            assert create_resp.status_code == 200
            success, _ = parse_ocs_response(create_resp.text)
            assert success
            cleanup_users.append(('nextcloud', unique_username))

            # Authenticate by accessing OCS API with user credentials
            auth_resp = await client.get(
                f"{nextcloud_url}/ocs/v1.php/cloud/capabilities",
                auth=(unique_username, password),
                headers={"OCS-APIRequest": "true"},
                timeout=10.0
            )

        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.status_code}"
        success, _ = parse_ocs_response(auth_resp.text)
        assert success, "Authentication failed - couldn't access capabilities"

    @pytest.mark.asyncio
    async def test_user_exists_error(self, wait_for_services, nextcloud_url, auth,
                                      headers, unique_username, cleanup_users):
        """Test that creating duplicate user returns appropriate error."""
        password = "TestPassword123!"

        async with httpx.AsyncClient(verify=False) as client:
            # Create user first time
            resp1 = await client.post(
                f"{nextcloud_url}/ocs/v1.php/cloud/users",
                auth=auth,
                headers=headers,
                data={"userid": unique_username, "password": password},
                timeout=15.0
            )
            assert resp1.status_code == 200
            success, _ = parse_ocs_response(resp1.text)
            assert success
            cleanup_users.append(('nextcloud', unique_username))

            # Try to create same user again
            resp2 = await client.post(
                f"{nextcloud_url}/ocs/v1.php/cloud/users",
                auth=auth,
                headers=headers,
                data={"userid": unique_username, "password": password},
                timeout=15.0
            )

        assert resp2.status_code == 200  # OCS returns 200 with error in body
        success, message = parse_ocs_response(resp2.text)
        assert not success, "Should fail when creating duplicate user"
