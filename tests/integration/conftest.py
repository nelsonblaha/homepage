"""
Integration test fixtures for Homepage services.

These tests hit real containerized services to verify user operations work correctly.
Run with: pytest tests/integration/ -v

Requires test containers to be running:
  docker compose -f tests/integration/docker-compose.yml up -d
"""

import os
import sys
import uuid
import time
import pytest
import httpx

# Add app to path for importing integrations
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'app'))


# =============================================================================
# Test Container URLs
# =============================================================================
# When running inside the test network, use container hostnames
# When running from host, use localhost with mapped ports

def get_test_url(service: str) -> str:
    """Get the URL for a test service based on environment."""
    # Check if we're inside the docker network
    in_docker = os.environ.get('IN_DOCKER_NETWORK', '').lower() == 'true'

    if in_docker:
        # Inside docker network - use container hostnames
        urls = {
            'jellyfin': 'http://homepage-test-jellyfin:8096',
            'ombi': 'http://homepage-test-ombi:3579',
            'overseerr': 'http://homepage-test-overseerr:5055',
            'nextcloud': 'http://homepage-test-nextcloud:80',
            'mattermost': 'http://homepage-test-mattermost:8065',
        }
    else:
        # From host - use localhost with mapped ports
        urls = {
            'jellyfin': 'http://127.0.0.1:19096',
            'ombi': 'http://127.0.0.1:19579',
            'overseerr': 'http://127.0.0.1:19055',
            'nextcloud': 'http://127.0.0.1:19080',
            'mattermost': 'http://127.0.0.1:19065',
        }

    return urls.get(service, '')


# =============================================================================
# Service Health Check Endpoints
# =============================================================================

HEALTH_CHECKS = {
    'jellyfin': '/health',
    'ombi': '/api/v1/Status',
    'overseerr': '/api/v1/status',
    'nextcloud': '/status.php',
    'mattermost': '/api/v4/system/ping',
}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def wait_for_services():
    """
    Wait for all test containers to be healthy before running tests.

    This fixture runs once per session and blocks until all services respond.
    Times out after 5 minutes total.
    """
    services = ['jellyfin', 'ombi', 'overseerr', 'nextcloud', 'mattermost']
    max_wait = 300  # 5 minutes total
    start_time = time.time()

    healthy = {s: False for s in services}

    while not all(healthy.values()) and (time.time() - start_time) < max_wait:
        for service in services:
            if healthy[service]:
                continue

            url = get_test_url(service)
            health_path = HEALTH_CHECKS[service]

            try:
                resp = httpx.get(f"{url}{health_path}", timeout=5.0, follow_redirects=True)
                if resp.status_code < 500:
                    healthy[service] = True
                    print(f"✓ {service} is healthy")
            except Exception:
                pass

        if not all(healthy.values()):
            time.sleep(5)

    unhealthy = [s for s, h in healthy.items() if not h]
    if unhealthy:
        pytest.fail(f"Services not healthy after {max_wait}s: {unhealthy}")

    return healthy


@pytest.fixture
def unique_username():
    """Generate a unique username for test isolation."""
    return f"test-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def unique_email(unique_username):
    """Generate a unique email based on unique username."""
    return f"{unique_username}@test.local"


# =============================================================================
# Jellyfin Fixtures
# =============================================================================

@pytest.fixture
def jellyfin_url():
    """Get the Jellyfin test container URL."""
    return get_test_url('jellyfin')


@pytest.fixture
def jellyfin_api_key():
    """
    Get or create a Jellyfin API key for testing.

    Note: Fresh Jellyfin has no API key - tests that need one should
    skip or handle this case. For user creation tests, we'll use
    the wizard setup or basic auth.
    """
    # For a fresh Jellyfin, we need to complete initial setup first
    # This would need to be done manually or via setup script
    return os.environ.get('JELLYFIN_TEST_API_KEY', '')


# =============================================================================
# Ombi Fixtures
# =============================================================================

@pytest.fixture
def ombi_url():
    """Get the Ombi test container URL."""
    return get_test_url('ombi')


@pytest.fixture
def ombi_api_key():
    """Get the Ombi API key for testing."""
    return os.environ.get('OMBI_TEST_API_KEY', '')


# =============================================================================
# Overseerr Fixtures
# =============================================================================

@pytest.fixture
def overseerr_url():
    """Get the Overseerr test container URL."""
    return get_test_url('overseerr')


@pytest.fixture
def overseerr_api_key():
    """Get the Overseerr API key for testing."""
    return os.environ.get('OVERSEERR_TEST_API_KEY', '')


# =============================================================================
# Nextcloud Fixtures
# =============================================================================

@pytest.fixture
def nextcloud_url():
    """Get the Nextcloud test container URL."""
    return get_test_url('nextcloud')


@pytest.fixture
def nextcloud_admin_user():
    """Get the Nextcloud admin username."""
    return os.environ.get('NEXTCLOUD_TEST_ADMIN_USER', 'admin')


@pytest.fixture
def nextcloud_admin_pass():
    """Get the Nextcloud admin password."""
    return os.environ.get('NEXTCLOUD_TEST_ADMIN_PASS', 'adminpass123')


# =============================================================================
# Mattermost Fixtures
# =============================================================================

@pytest.fixture
def mattermost_url():
    """Get the Mattermost test container URL."""
    return get_test_url('mattermost')


@pytest.fixture
def mattermost_token():
    """Get the Mattermost admin token for testing."""
    return os.environ.get('MATTERMOST_TEST_TOKEN', '')


@pytest.fixture
def mattermost_team_id():
    """Get the Mattermost team ID for testing."""
    return os.environ.get('MATTERMOST_TEST_TEAM_ID', '')


# =============================================================================
# Cleanup Helpers
# =============================================================================

@pytest.fixture
def cleanup_users():
    """
    Fixture that provides a list to track users for cleanup.

    Usage:
        def test_something(cleanup_users):
            user = create_user(...)
            cleanup_users.append(('jellyfin', user['id']))
            # Test runs...
            # Cleanup happens automatically after test
    """
    users_to_cleanup = []
    yield users_to_cleanup

    # Cleanup after test
    for service, user_id in users_to_cleanup:
        try:
            url = get_test_url(service)
            if service == 'jellyfin':
                api_key = os.environ.get('JELLYFIN_TEST_API_KEY', '')
                if api_key:
                    httpx.delete(
                        f"{url}/Users/{user_id}",
                        headers={"X-Emby-Token": api_key},
                        timeout=10.0
                    )
            elif service == 'ombi':
                api_key = os.environ.get('OMBI_TEST_API_KEY', '')
                if api_key:
                    httpx.delete(
                        f"{url}/api/v1/Identity/{user_id}",
                        headers={"ApiKey": api_key},
                        timeout=10.0
                    )
            elif service == 'overseerr':
                api_key = os.environ.get('OVERSEERR_TEST_API_KEY', '')
                if api_key:
                    httpx.delete(
                        f"{url}/api/v1/user/{user_id}",
                        headers={"X-Api-Key": api_key},
                        timeout=10.0
                    )
            elif service == 'nextcloud':
                admin_user = os.environ.get('NEXTCLOUD_TEST_ADMIN_USER', 'admin')
                admin_pass = os.environ.get('NEXTCLOUD_TEST_ADMIN_PASS', 'adminpass123')
                httpx.delete(
                    f"{url}/ocs/v1.php/cloud/users/{user_id}",
                    auth=(admin_user, admin_pass),
                    headers={"OCS-APIRequest": "true"},
                    timeout=10.0
                )
            elif service == 'mattermost':
                token = os.environ.get('MATTERMOST_TEST_TOKEN', '')
                if token:
                    httpx.delete(
                        f"{url}/api/v4/users/{user_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10.0
                    )
        except Exception as e:
            print(f"Warning: Failed to cleanup {service} user {user_id}: {e}")
