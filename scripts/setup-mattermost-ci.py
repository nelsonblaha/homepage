#!/usr/bin/env python3
"""
Setup Mattermost for CI testing.

The mattermost-preview image comes pre-configured with an admin user.
We just need to get the login token and create an API access token.
"""
import requests
import time
import sys
import os

MATTERMOST_URL = os.environ.get('MATTERMOST_URL', 'http://localhost:8065')
MAX_RETRIES = 60
RETRY_DELAY = 3

# Default credentials for mattermost-preview image
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin"


def wait_for_mattermost():
    """Wait for Mattermost to be ready."""
    print(f"Waiting for Mattermost at {MATTERMOST_URL}...", flush=True)
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{MATTERMOST_URL}/api/v4/system/ping", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'OK':
                    print("Mattermost is ready!", flush=True)
                    return True
        except requests.exceptions.RequestException as e:
            if i % 10 == 0:
                print(f"Attempt {i+1}/{MAX_RETRIES} - {type(e).__name__}", flush=True)
        time.sleep(RETRY_DELAY)
    return False


def login():
    """Login to Mattermost and get session token."""
    try:
        resp = requests.post(
            f"{MATTERMOST_URL}/api/v4/users/login",
            json={
                "login_id": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        if resp.status_code == 200:
            token = resp.headers.get('Token')
            user = resp.json()
            print(f"Logged in as: {user.get('username')}")
            return token, user.get('id')
        else:
            print(f"Login failed: {resp.status_code} {resp.text}")
            return None, None
    except Exception as e:
        print(f"Error during login: {e}")
        return None, None


def create_personal_access_token(session_token, user_id):
    """Create a personal access token for API access."""
    headers = {"Authorization": f"Bearer {session_token}"}

    try:
        # Check existing tokens
        resp = requests.get(
            f"{MATTERMOST_URL}/api/v4/users/{user_id}/tokens",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            tokens = resp.json()
            for token in tokens:
                if token.get('description') == 'blaha-homepage-ci':
                    # Can't retrieve token value, need to create new
                    print("Found existing token but can't retrieve value")

        # Create new token
        resp = requests.post(
            f"{MATTERMOST_URL}/api/v4/users/{user_id}/tokens",
            headers=headers,
            json={"description": "blaha-homepage-ci"},
            timeout=10
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            token = data.get('token')
            print(f"Created personal access token: {token[:8]}...")
            return token
        else:
            print(f"Failed to create token: {resp.status_code} {resp.text}")

            # Personal access tokens might be disabled, use session token
            print("Using session token instead")
            return session_token

    except Exception as e:
        print(f"Error creating access token: {e}")
        return session_token  # Fall back to session token


def main():
    if not wait_for_mattermost():
        print("ERROR: Mattermost failed to start")
        sys.exit(1)

    session_token, user_id = login()
    if not session_token:
        print("ERROR: Failed to login to Mattermost")
        sys.exit(1)

    api_token = create_personal_access_token(session_token, user_id)

    if api_token:
        print(f"\nMATTERMOST_TOKEN={api_token}")
        with open('/tmp/mattermost-token.txt', 'w') as f:
            f.write(api_token)
        print("\nMattermost setup complete!")
        sys.exit(0)
    else:
        print("\nERROR: Failed to get API token")
        sys.exit(1)


if __name__ == '__main__':
    main()
