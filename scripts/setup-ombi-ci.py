#!/usr/bin/env python3
"""
Setup Ombi for CI testing.

Ombi requires completing a setup wizard on first run to create an admin user
and generate an API key. This script automates that process.
"""
import requests
import time
import sys
import os

OMBI_URL = os.environ.get('OMBI_URL', 'http://localhost:3579')
MAX_RETRIES = 60  # Ombi takes a long time on first run
RETRY_DELAY = 5   # 60 * 5 = 5 minutes max wait


def wait_for_ombi():
    """Wait for Ombi to be ready."""
    print(f"Waiting for Ombi at {OMBI_URL}...")
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{OMBI_URL}/api/v1/Settings/About", timeout=5)
            if resp.status_code == 200:
                print("Ombi is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        print(f"Attempt {i+1}/{MAX_RETRIES} - Ombi not ready yet...")
        time.sleep(RETRY_DELAY)
    return False


def check_wizard_status():
    """Check if wizard has been completed."""
    try:
        resp = requests.get(f"{OMBI_URL}/api/v1/Settings/Wizard", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('result', False)
    except Exception as e:
        print(f"Error checking wizard status: {e}")
    return False


def complete_wizard():
    """Complete the Ombi setup wizard."""
    print("Completing Ombi setup wizard...")

    # Step 1: Create admin user
    admin_data = {
        "username": "admin",
        "password": "CITestAdmin123!",
        "usePlexAdminAccount": False
    }

    try:
        resp = requests.post(
            f"{OMBI_URL}/api/v1/Identity/Wizard",
            json=admin_data,
            timeout=30
        )
        if resp.status_code not in (200, 201):
            print(f"Failed to create admin user: {resp.status_code} {resp.text}")
            # Try to login in case user already exists
            return try_login_and_get_key()
        print("Admin user created successfully")
    except Exception as e:
        print(f"Error creating admin user: {e}")
        return None

    # Step 2: Login and get token
    return try_login_and_get_key()


def try_login_and_get_key():
    """Login as admin and get/create API key."""
    login_data = {
        "username": "admin",
        "password": "CITestAdmin123!"
    }

    try:
        resp = requests.post(
            f"{OMBI_URL}/api/v1/Token",
            json=login_data,
            timeout=10
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            return None

        token = resp.json().get('access_token')
        if not token:
            print("No access token in response")
            return None
        print("Login successful")

        # Get API key from settings
        headers = {"Authorization": f"Bearer {token}"}

        # First check if there's an existing API key
        resp = requests.get(
            f"{OMBI_URL}/api/v1/Settings/Ombi",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            settings = resp.json()
            api_key = settings.get('apiKey')
            if api_key:
                print(f"Found existing API key: {api_key[:8]}...")
                return api_key

        # Generate new API key
        resp = requests.post(
            f"{OMBI_URL}/api/v1/Settings/GenerateApiKey",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            api_key = resp.text.strip('"')
            print(f"Generated new API key: {api_key[:8]}...")
            return api_key
        else:
            print(f"Failed to generate API key: {resp.status_code} {resp.text}")

    except Exception as e:
        print(f"Error during login/API key retrieval: {e}")

    return None


def main():
    if not wait_for_ombi():
        print("ERROR: Ombi failed to start")
        sys.exit(1)

    # Check if already set up
    if check_wizard_status():
        print("Wizard already completed, getting API key...")
        api_key = try_login_and_get_key()
    else:
        api_key = complete_wizard()

    if api_key:
        # Output for CI to capture
        print(f"\nOMBI_API_KEY={api_key}")

        # Also write to file for CI
        with open('/tmp/ombi-api-key.txt', 'w') as f:
            f.write(api_key)

        print("\nOmbi setup complete!")
        sys.exit(0)
    else:
        print("\nERROR: Failed to get API key")
        sys.exit(1)


if __name__ == '__main__':
    main()
