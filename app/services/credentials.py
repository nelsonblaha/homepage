"""Credential management for basic auth services.

This module handles:
- Generating unique credentials per friend per service
- Updating nginx htpasswd files
- Credential lifecycle (create, delete, regenerate)
"""
import secrets
import string
import subprocess
from pathlib import Path
from typing import Optional


# Admin credentials stay in env vars for now
ADMIN_USERNAME = "admin"

# Nginx htpasswd directory (in nginx-proxy container)
HTPASSWD_DIR = "/etc/nginx/htpasswd"


def generate_username(friend_name: str, service_subdomain: str) -> str:
    """Generate unique username for friend+service combination.

    Format: friendname_service (lowercase, alphanumeric only)
    Example: annette_transmission
    """
    # Clean friend name and subdomain
    clean_friend = "".join(c for c in friend_name.lower() if c.isalnum())
    clean_service = "".join(c for c in service_subdomain.lower() if c.isalnum())

    return f"{clean_friend}_{clean_service}"


def generate_password(length: int = 24) -> str:
    """Generate a secure random password.

    Uses mix of uppercase, lowercase, digits, and safe special characters.
    Avoids ambiguous characters (0/O, 1/l/I).
    """
    # Exclude ambiguous characters
    alphabet = string.ascii_uppercase.replace('O', '').replace('I', '')
    alphabet += string.ascii_lowercase.replace('l', '').replace('o', '')
    alphabet += string.digits.replace('0', '').replace('1', '')
    alphabet += "!@#$%^&*-_=+"

    return ''.join(secrets.choice(alphabet) for _ in range(length))


def update_htpasswd(subdomain: str, username: str, password: str) -> None:
    """Add or update a user in the htpasswd file for a service.

    Uses docker exec to run htpasswd inside nginx-proxy container.
    """
    htpasswd_file = f"{HTPASSWD_DIR}/{subdomain}.blaha.io"

    # Use htpasswd command in nginx-proxy container
    # -b: batch mode (password on command line)
    # NOTE: If user exists, this updates their password. If not, appends.
    subprocess.run([
        "docker", "exec", "nginx-proxy",
        "htpasswd", "-b", htpasswd_file, username, password
    ], check=True, capture_output=True)


def remove_from_htpasswd(subdomain: str, username: str) -> None:
    """Remove a user from the htpasswd file for a service.

    Uses docker exec to run htpasswd inside nginx-proxy container.
    """
    htpasswd_file = f"{HTPASSWD_DIR}/{subdomain}.blaha.io"

    # Use htpasswd -D to delete user
    subprocess.run([
        "docker", "exec", "nginx-proxy",
        "htpasswd", "-D", htpasswd_file, username
    ], check=True, capture_output=True)


def reload_nginx() -> None:
    """Reload nginx to pick up htpasswd changes."""
    subprocess.run([
        "docker", "exec", "nginx-proxy",
        "nginx", "-s", "reload"
    ], check=True, capture_output=True)


async def provision_credentials(friend_name: str, service_subdomain: str) -> tuple[str, str]:
    """Provision new credentials for a friend+service.

    Returns:
        tuple of (username, password)
    """
    username = generate_username(friend_name, service_subdomain)
    password = generate_password()

    # Add to htpasswd file
    update_htpasswd(service_subdomain, username, password)

    # Reload nginx
    reload_nginx()

    return username, password


async def revoke_credentials(service_subdomain: str, username: str) -> None:
    """Revoke credentials for a friend+service.

    Removes the user from the htpasswd file.
    """
    remove_from_htpasswd(service_subdomain, username)
    reload_nginx()
