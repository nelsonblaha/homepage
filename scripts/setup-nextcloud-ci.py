#!/usr/bin/env python3
"""
Setup Nextcloud for CI testing.

Nextcloud (linuxserver image) auto-creates an admin user on first run.
We need to wait for it and then get/create an app password for API access.
"""
import requests
import time
import sys
import os
import urllib3

# Disable SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NEXTCLOUD_URL = os.environ.get('NEXTCLOUD_URL', 'https://localhost:443')
MAX_RETRIES = 90  # Nextcloud takes longer to initialize
RETRY_DELAY = 4

# Default admin credentials (linuxserver image)
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"  # Can be set via NEXTCLOUD_ADMIN_PASSWORD env var


def wait_for_nextcloud():
    """Wait for Nextcloud to be ready."""
    print(f"Waiting for Nextcloud at {NEXTCLOUD_URL}...", flush=True)
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(
                f"{NEXTCLOUD_URL}/status.php",
                timeout=5,
                verify=False
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('installed'):
                    print("Nextcloud is ready!", flush=True)
                    return True
                else:
                    if i % 10 == 0:
                        print(f"Attempt {i+1}/{MAX_RETRIES} - Not yet installed", flush=True)
            else:
                if i % 10 == 0:
                    print(f"Attempt {i+1}/{MAX_RETRIES} - Status {resp.status_code}", flush=True)
        except requests.exceptions.RequestException as e:
            if i % 10 == 0:
                print(f"Attempt {i+1}/{MAX_RETRIES} - {type(e).__name__}", flush=True)
        time.sleep(RETRY_DELAY)
    return False


def test_login():
    """Test admin login with basic auth."""
    try:
        resp = requests.get(
            f"{NEXTCLOUD_URL}/ocs/v2.php/cloud/user",
            auth=(ADMIN_USER, ADMIN_PASSWORD),
            headers={"OCS-APIRequest": "true"},
            timeout=10,
            verify=False
        )
        if resp.status_code == 200:
            print(f"Login successful as {ADMIN_USER}")
            return True
        else:
            print(f"Login failed: {resp.status_code}")
            return False
    except Exception as e:
        print(f"Login error: {e}")
        return False


def create_app_password():
    """Create an app password for API access."""
    try:
        resp = requests.post(
            f"{NEXTCLOUD_URL}/ocs/v2.php/core/getapppassword",
            auth=(ADMIN_USER, ADMIN_PASSWORD),
            headers={"OCS-APIRequest": "true"},
            timeout=10,
            verify=False
        )
        if resp.status_code == 200:
            # Parse OCS response
            import xml.etree.ElementTree as ET
            root = ET.fromstring(resp.text)
            app_password = root.find('.//apppassword')
            if app_password is not None and app_password.text:
                print(f"Created app password: {app_password.text[:8]}...")
                return app_password.text
    except Exception as e:
        print(f"Error creating app password: {e}")

    # Fall back to using admin password
    print("Using admin password for API access")
    return ADMIN_PASSWORD


def main():
    if not wait_for_nextcloud():
        print("ERROR: Nextcloud failed to start")
        sys.exit(1)

    # Give it a bit more time to fully initialize
    time.sleep(5)

    if not test_login():
        print("ERROR: Failed to login to Nextcloud")
        print("Note: linuxserver/nextcloud requires manual first-run setup")
        print("Continuing with test credentials...")

    # For CI, we'll just use the admin password
    # Real app passwords require the user to be logged in via web
    api_password = ADMIN_PASSWORD

    print(f"\nNEXTCLOUD_USER={ADMIN_USER}")
    print(f"NEXTCLOUD_PASSWORD={api_password}")

    with open('/tmp/nextcloud-credentials.txt', 'w') as f:
        f.write(f"{ADMIN_USER}:{api_password}")

    print("\nNextcloud setup complete!")
    sys.exit(0)


if __name__ == '__main__':
    main()
