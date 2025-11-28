"""
Friend authentication service - password, TOTP, and usage limits.

This module handles:
- Password hashing and verification
- TOTP generation and verification
- Usage counting and limits
- Time-limited access (expiration)
"""

import os
import secrets
import hashlib
import hmac
import time
import struct
import base64
from datetime import datetime
from typing import Optional, Tuple
from dataclasses import dataclass


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default thresholds (can be overridden per-friend)
DEFAULT_WARNING_THRESHOLD = 5  # Warn user at this usage count
DEFAULT_PASSWORD_THRESHOLD = 10  # Require password after this many uses

# Password modes
PASSWORD_NOT_REQUIRED = 0
PASSWORD_ALWAYS_REQUIRED = 1
PASSWORD_AFTER_THRESHOLD = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AuthRequirement:
    """What authentication is required for a friend."""
    needs_password: bool = False
    needs_totp: bool = False
    is_expired: bool = False
    usage_warning: bool = False  # True if approaching threshold
    error_message: Optional[str] = None


@dataclass
class AuthResult:
    """Result of authentication attempt."""
    success: bool
    error: Optional[str] = None
    session_token: Optional[str] = None


# =============================================================================
# PASSWORD HASHING (bcrypt-style using hashlib)
# =============================================================================

def _generate_salt(length: int = 16) -> bytes:
    """Generate a random salt."""
    return secrets.token_bytes(length)


def hash_password(password: str) -> str:
    """
    Hash a password using PBKDF2-SHA256.

    Returns a string in format: $pbkdf2$iterations$salt$hash
    """
    iterations = 100000
    salt = _generate_salt()
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations
    )

    salt_b64 = base64.b64encode(salt).decode('ascii')
    hash_b64 = base64.b64encode(password_hash).decode('ascii')

    return f"$pbkdf2${iterations}${salt_b64}${hash_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash.

    Returns True if password matches.
    """
    if not password_hash or not password_hash.startswith("$pbkdf2$"):
        return False

    try:
        parts = password_hash.split("$")
        if len(parts) != 5:
            return False

        _, _, iterations_str, salt_b64, expected_hash_b64 = parts
        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64)
        expected_hash = base64.b64decode(expected_hash_b64)

        actual_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations
        )

        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False


def generate_temporary_password(length: int = 16) -> str:
    """Generate a random temporary password."""
    return secrets.token_urlsafe(length)


# =============================================================================
# TOTP (Time-based One-Time Password)
# =============================================================================

def generate_totp_secret() -> str:
    """Generate a new TOTP secret (Base32 encoded)."""
    # 20 bytes = 160 bits, standard for TOTP
    secret_bytes = secrets.token_bytes(20)
    return base64.b32encode(secret_bytes).decode('ascii').rstrip('=')


def _hotp(secret: bytes, counter: int) -> str:
    """Generate HOTP value."""
    counter_bytes = struct.pack('>Q', counter)
    hmac_result = hmac.new(secret, counter_bytes, hashlib.sha1).digest()

    # Dynamic truncation
    offset = hmac_result[-1] & 0x0F
    code = struct.unpack('>I', hmac_result[offset:offset + 4])[0]
    code = (code & 0x7FFFFFFF) % 1000000

    return str(code).zfill(6)


def generate_totp(secret: str, time_step: int = 30) -> str:
    """
    Generate current TOTP code.

    Args:
        secret: Base32 encoded secret
        time_step: Time step in seconds (default 30)

    Returns:
        6-digit TOTP code
    """
    # Pad secret if needed
    padding = 8 - (len(secret) % 8)
    if padding != 8:
        secret += '=' * padding

    secret_bytes = base64.b32decode(secret.upper())
    counter = int(time.time()) // time_step

    return _hotp(secret_bytes, counter)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    """
    Verify a TOTP code.

    Args:
        secret: Base32 encoded secret
        code: 6-digit code to verify
        window: Number of time steps to check before/after current

    Returns:
        True if code is valid
    """
    if not secret or not code:
        return False

    # Normalize code
    code = code.strip().replace(' ', '')
    if len(code) != 6:
        return False

    try:
        # Pad secret if needed
        padding = 8 - (len(secret) % 8)
        if padding != 8:
            secret += '=' * padding

        secret_bytes = base64.b32decode(secret.upper())
        current_counter = int(time.time()) // 30

        # Check current time and window before/after
        for offset in range(-window, window + 1):
            expected = _hotp(secret_bytes, current_counter + offset)
            if hmac.compare_digest(expected, code):
                return True

        return False
    except Exception:
        return False


def get_totp_uri(secret: str, username: str, issuer: str = None) -> str:
    """
    Generate otpauth:// URI for QR code generation.

    Args:
        secret: Base32 encoded secret
        username: User's display name
        issuer: Service name

    Returns:
        otpauth:// URI for QR code
    """
    from urllib.parse import quote
    if issuer is None:
        issuer = os.environ.get("BASE_DOMAIN", "Homepage")
    return f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}"


# =============================================================================
# AUTH REQUIREMENT CHECKING
# =============================================================================

def check_auth_requirements(friend: dict) -> AuthRequirement:
    """
    Check what authentication is required for a friend.

    Args:
        friend: Friend database record (dict)

    Returns:
        AuthRequirement indicating what's needed
    """
    result = AuthRequirement()

    # Check expiration
    expires_at = friend.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if datetime.now() > expires_at:
            result.is_expired = True
            result.error_message = "Your access has expired"
            return result

    # Check usage limits
    usage_count = friend.get("usage_count", 0)
    password_required = friend.get("password_required", PASSWORD_NOT_REQUIRED)
    password_threshold = friend.get("password_required_after", DEFAULT_PASSWORD_THRESHOLD)

    # Usage warning
    if password_required == PASSWORD_AFTER_THRESHOLD:
        if usage_count >= DEFAULT_WARNING_THRESHOLD and usage_count < password_threshold:
            result.usage_warning = True

    # Password requirement
    if password_required == PASSWORD_ALWAYS_REQUIRED:
        if friend.get("password_hash"):
            result.needs_password = True
    elif password_required == PASSWORD_AFTER_THRESHOLD:
        if usage_count >= password_threshold and friend.get("password_hash"):
            result.needs_password = True

    # TOTP requirement (if configured)
    if friend.get("totp_secret"):
        result.needs_totp = True

    return result


async def increment_usage(db, friend_id: int) -> int:
    """
    Increment usage count for a friend.

    Returns the new usage count.
    """
    await db.execute(
        "UPDATE friends SET usage_count = usage_count + 1 WHERE id = ?",
        (friend_id,)
    )
    await db.commit()

    cursor = await db.execute(
        "SELECT usage_count FROM friends WHERE id = ?",
        (friend_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return 0
    # Handle both dict (when row_factory is set) and tuple (default) results
    if isinstance(row, dict):
        return row.get("usage_count", 0)
    return row[0]


async def set_friend_password(db, friend_id: int, password: str) -> bool:
    """
    Set or update a friend's password.

    Returns True on success.
    """
    password_hash = hash_password(password)
    await db.execute(
        "UPDATE friends SET password_hash = ? WHERE id = ?",
        (password_hash, friend_id)
    )
    await db.commit()
    return True


async def enable_totp(db, friend_id: int) -> str:
    """
    Enable TOTP for a friend.

    Returns the TOTP secret (for QR code generation).
    """
    secret = generate_totp_secret()
    await db.execute(
        "UPDATE friends SET totp_secret = ? WHERE id = ?",
        (secret, friend_id)
    )
    await db.commit()
    return secret


async def disable_totp(db, friend_id: int) -> bool:
    """Disable TOTP for a friend."""
    await db.execute(
        "UPDATE friends SET totp_secret = '' WHERE id = ?",
        (friend_id,)
    )
    await db.commit()
    return True
