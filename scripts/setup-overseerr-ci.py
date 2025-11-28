#!/usr/bin/env python3
"""
Setup Overseerr for CI testing.

Overseerr requires initial setup to create an admin user. Unlike Ombi,
Overseerr doesn't need Plex connection for basic testing.
"""
import requests
import time
import sys
import os

OVERSEERR_URL = os.environ.get('OVERSEERR_URL', 'http://localhost:5055')
MAX_RETRIES = 60
RETRY_DELAY = 3


def wait_for_overseerr():
    """Wait for Overseerr to be ready."""
    print(f"Waiting for Overseerr at {OVERSEERR_URL}...", flush=True)
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{OVERSEERR_URL}/api/v1/status", timeout=5)
            if resp.status_code == 200:
                print("Overseerr is ready!", flush=True)
                return True
        except requests.exceptions.RequestException as e:
            if i % 10 == 0:
                print(f"Attempt {i+1}/{MAX_RETRIES} - {type(e).__name__}", flush=True)
        time.sleep(RETRY_DELAY)
    return False


def check_if_initialized():
    """Check if Overseerr has been initialized."""
    try:
        resp = requests.get(f"{OVERSEERR_URL}/api/v1/settings/public", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('initialized', False)
    except Exception:
        pass
    return False


def complete_setup():
    """Complete Overseerr initial setup."""
    print("Completing Overseerr setup...")

    # Step 1: Create local admin user (skip Plex login)
    try:
        resp = requests.post(
            f"{OVERSEERR_URL}/api/v1/auth/local",
            json={
                "email": "admin@test.local",
                "password": "CITestAdmin123!"
            },
            timeout=10
        )
        if resp.status_code == 200:
            print("Local admin user created")
            return resp.json()
        elif resp.status_code == 403:
            print("Local auth may be disabled, trying login...")
        else:
            print(f"Local auth returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Error creating local user: {e}")

    return None


def login_and_get_api_key():
    """Login and get API key."""
    session = requests.Session()

    # Login
    try:
        resp = session.post(
            f"{OVERSEERR_URL}/api/v1/auth/local",
            json={
                "email": "admin@test.local",
                "password": "CITestAdmin123!"
            },
            timeout=10
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code}")
            return None

        print("Login successful")

        # Get settings which contain API key
        resp = session.get(f"{OVERSEERR_URL}/api/v1/settings/main", timeout=10)
        if resp.status_code == 200:
            settings = resp.json()
            api_key = settings.get('apiKey')
            if api_key:
                print(f"Found API key: {api_key[:8]}...")
                return api_key

        # Try to get API key from auth/me
        resp = session.get(f"{OVERSEERR_URL}/api/v1/auth/me", timeout=10)
        if resp.status_code == 200:
            user = resp.json()
            print(f"Logged in as: {user.get('email')}")

        print("Could not retrieve API key from settings")
        return None

    except Exception as e:
        print(f"Error during login: {e}")
        return None


def main():
    if not wait_for_overseerr():
        print("ERROR: Overseerr failed to start")
        sys.exit(1)

    if check_if_initialized():
        print("Overseerr already initialized, getting API key...")
        api_key = login_and_get_api_key()
    else:
        result = complete_setup()
        if result:
            api_key = login_and_get_api_key()
        else:
            api_key = None

    if api_key:
        print(f"\nOVERSEERR_API_KEY={api_key}")
        with open('/tmp/overseerr-api-key.txt', 'w') as f:
            f.write(api_key)
        print("\nOverseerr setup complete!")
        sys.exit(0)
    else:
        # Overseerr without Plex might not work fully, but we can still test
        print("\nWARNING: Could not get API key (Plex login may be required)")
        print("Continuing with limited testing...")
        sys.exit(0)  # Don't fail CI


if __name__ == '__main__':
    main()
