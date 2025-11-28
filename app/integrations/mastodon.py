"""Mastodon integration for blaha.io - user management via tootctl CLI"""
import asyncio
import os
from fastapi import APIRouter, Depends

from services.session import verify_admin

MASTODON_CONTAINER = os.environ.get("MASTODON_CONTAINER", "mastodon-web")
MASTODON_DOMAIN = os.environ.get("MASTODON_DOMAIN", "social.blaha.io")

router = APIRouter(prefix="/api/mastodon", tags=["mastodon"])


async def run_tootctl(command: str) -> tuple[bool, str]:
    """Run a tootctl command in the Mastodon container."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", MASTODON_CONTAINER, "tootctl", *command.split(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() + stderr.decode()
        return proc.returncode == 0, output.strip()
    except Exception as e:
        return False, str(e)


async def create_mastodon_user(username: str) -> dict | None:
    """Create a Mastodon user. Returns user info including password."""
    # Mastodon username: lowercase, alphanumeric + underscores only
    safe_username = username.lower().replace(' ', '_')
    email = f"{safe_username}@blaha.io"

    # Create the user with --confirmed and --approve flags
    success, output = await run_tootctl(f"accounts create {safe_username} --email={email} --confirmed --approve")

    if not success:
        # User might already exist
        if "already" in output.lower():
            # Reset password instead
            return await reset_mastodon_password(safe_username)
        print(f"Mastodon create user failed: {output}")
        return None

    # Extract password from output (tootctl outputs "New password: <password>")
    password = None
    for line in output.split('\n'):
        if 'password' in line.lower():
            parts = line.split(':')
            if len(parts) >= 2:
                password = parts[-1].strip()
                break

    if not password:
        # Generate a new password
        return await reset_mastodon_password(safe_username)

    # Return full Mastodon handle for display (username@domain)
    full_handle = f"{safe_username}@{MASTODON_DOMAIN}"
    return {
        "id": full_handle,
        "username": full_handle,
        "email": email,
        "password": password,
        "_internal_username": safe_username  # For deletion
    }


async def reset_mastodon_password(username: str) -> dict | None:
    """Reset a Mastodon user's password. Returns new password."""
    success, output = await run_tootctl(f"accounts modify {username} --reset-password")

    if not success:
        print(f"Mastodon reset password failed: {output}")
        return None

    # Extract password from output
    password = None
    for line in output.split('\n'):
        if 'password' in line.lower():
            parts = line.split(':')
            if len(parts) >= 2:
                password = parts[-1].strip()
                break

    if not password:
        print(f"Mastodon: could not parse password from: {output}")
        return None

    email = f"{username}@blaha.io"
    # Return full Mastodon handle for display (username@domain)
    full_handle = f"{username}@{MASTODON_DOMAIN}"
    return {
        "id": full_handle,
        "username": full_handle,
        "email": email,
        "password": password,
        "_internal_username": username  # For deletion
    }


async def delete_mastodon_user(username: str) -> bool:
    """Delete a Mastodon user. Accepts full handle (user@domain) or just username."""
    # Extract just the username if full handle was provided
    if '@' in username:
        username = username.split('@')[0]
    success, output = await run_tootctl(f"accounts delete {username}")
    if not success:
        print(f"Mastodon delete user failed: {output}")
    return success


@router.get("/status")
async def mastodon_status(_: bool = Depends(verify_admin)):
    """Check Mastodon connection status."""
    success, output = await run_tootctl("accounts --help")
    if success:
        return {"connected": True, "domain": MASTODON_DOMAIN}
    return {"connected": False, "error": "Cannot reach Mastodon container"}
