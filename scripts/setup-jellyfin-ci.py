#!/usr/bin/env python3
"""
Setup Jellyfin for CI testing.

Jellyfin requires completing a setup wizard on first run to create an admin user
and configure basic settings. This script automates that process.
"""
import requests
import time
import sys
import os

JELLYFIN_URL = os.environ.get('JELLYFIN_URL', 'http://localhost:8096')
MAX_RETRIES = 60
RETRY_DELAY = 3


def wait_for_jellyfin():
    """Wait for Jellyfin to be ready."""
    print(f"Waiting for Jellyfin at {JELLYFIN_URL}...", flush=True)
    for i in range(MAX_RETRIES):
        try:
            resp = requests.get(f"{JELLYFIN_URL}/health", timeout=5)
            if resp.status_code == 200:
                print("Jellyfin is ready!", flush=True)
                return True
        except requests.exceptions.RequestException as e:
            if i % 10 == 0:
                print(f"Attempt {i+1}/{MAX_RETRIES} - {type(e).__name__}", flush=True)
        time.sleep(RETRY_DELAY)
    return False


def get_startup_config():
    """Get the startup configuration wizard status."""
    try:
        resp = requests.get(f"{JELLYFIN_URL}/Startup/Configuration", timeout=5)
        return resp.status_code == 200, resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        print(f"Error getting startup config: {e}")
        return False, {}


def complete_wizard():
    """Complete the Jellyfin setup wizard."""
    print("Completing Jellyfin setup wizard...")

    # Step 1: Set startup configuration (language, etc)
    try:
        resp = requests.post(
            f"{JELLYFIN_URL}/Startup/Configuration",
            json={
                "UICulture": "en-US",
                "MetadataCountryCode": "US",
                "PreferredMetadataLanguage": "en"
            },
            timeout=10
        )
        if resp.status_code not in (200, 204):
            print(f"Warning: Startup config returned {resp.status_code}")
    except Exception as e:
        print(f"Warning: Error setting startup config: {e}")

    # Step 2: Get first user (might already exist)
    try:
        resp = requests.get(f"{JELLYFIN_URL}/Startup/User", timeout=5)
        if resp.status_code == 200:
            user_data = resp.json()
            if user_data.get('Name'):
                print(f"Found existing user: {user_data['Name']}")
    except Exception:
        pass

    # Step 3: Create admin user
    try:
        resp = requests.post(
            f"{JELLYFIN_URL}/Startup/User",
            json={
                "Name": "admin",
                "Password": "CITestAdmin123!"
            },
            timeout=10
        )
        if resp.status_code in (200, 204):
            print("Admin user created successfully")
        else:
            print(f"User creation returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Error creating admin user: {e}")

    # Step 4: Complete the wizard
    try:
        resp = requests.post(
            f"{JELLYFIN_URL}/Startup/Complete",
            timeout=10
        )
        if resp.status_code in (200, 204):
            print("Wizard completed!")
        else:
            print(f"Wizard completion returned {resp.status_code}")
    except Exception as e:
        print(f"Error completing wizard: {e}")

    return get_api_key()


def get_api_key():
    """Login and get/create API key."""
    # Authenticate
    try:
        resp = requests.post(
            f"{JELLYFIN_URL}/Users/AuthenticateByName",
            headers={
                "X-Emby-Authorization": 'MediaBrowser Client="CI Test", Device="CI", DeviceId="ci-test", Version="1.0"'
            },
            json={
                "Username": "admin",
                "Pw": "CITestAdmin123!"
            },
            timeout=10
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            return None

        data = resp.json()
        access_token = data.get('AccessToken')
        user_id = data.get('User', {}).get('Id')

        if not access_token:
            print("No access token in response")
            return None

        print(f"Login successful, user ID: {user_id}")

        # Create an API key
        headers = {
            "X-Emby-Authorization": f'MediaBrowser Client="CI Test", Device="CI", DeviceId="ci-test", Version="1.0", Token="{access_token}"'
        }

        # Get existing API keys
        resp = requests.get(
            f"{JELLYFIN_URL}/Auth/Keys",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            keys = resp.json().get('Items', [])
            for key in keys:
                if key.get('AppName') == 'blaha-homepage-ci':
                    print(f"Found existing API key: {key['AccessToken'][:8]}...")
                    return key['AccessToken']

        # Create new API key
        resp = requests.post(
            f"{JELLYFIN_URL}/Auth/Keys",
            headers=headers,
            params={"app": "blaha-homepage-ci"},
            timeout=10
        )
        if resp.status_code in (200, 204):
            # Fetch the keys again to get the new one
            resp = requests.get(
                f"{JELLYFIN_URL}/Auth/Keys",
                headers=headers,
                timeout=10
            )
            if resp.status_code == 200:
                keys = resp.json().get('Items', [])
                for key in keys:
                    if key.get('AppName') == 'blaha-homepage-ci':
                        print(f"Created API key: {key['AccessToken'][:8]}...")
                        return key['AccessToken']

        print(f"Failed to create API key: {resp.status_code}")
        return None

    except Exception as e:
        print(f"Error during authentication: {e}")
        return None


def check_if_configured():
    """Check if Jellyfin is already configured."""
    try:
        resp = requests.get(f"{JELLYFIN_URL}/System/Info/Public", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('StartupWizardCompleted', False)
    except Exception:
        pass
    return False


def main():
    if not wait_for_jellyfin():
        print("ERROR: Jellyfin failed to start")
        sys.exit(1)

    if check_if_configured():
        print("Jellyfin already configured, getting API key...")
        api_key = get_api_key()
    else:
        api_key = complete_wizard()

    if api_key:
        print(f"\nJELLYFIN_API_KEY={api_key}")
        with open('/tmp/jellyfin-api-key.txt', 'w') as f:
            f.write(api_key)
        print("\nJellyfin setup complete!")
        sys.exit(0)
    else:
        print("\nERROR: Failed to get API key")
        sys.exit(1)


if __name__ == '__main__':
    main()
