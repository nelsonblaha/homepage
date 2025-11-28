"""
Unit tests for friend authentication service.
"""

import pytest
from datetime import datetime, timedelta


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_pbkdf2_format(self):
        """Test that hash_password returns correct format."""
        from services.friend_auth import hash_password

        result = hash_password("testpassword")

        assert result.startswith("$pbkdf2$")
        parts = result.split("$")
        assert len(parts) == 5
        assert parts[2] == "100000"  # iterations

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        from services.friend_auth import hash_password, verify_password

        password = "mySecureP@ssw0rd"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_wrong(self):
        """Test password verification with wrong password."""
        from services.friend_auth import hash_password, verify_password

        hashed = hash_password("correctpassword")

        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty_hash(self):
        """Test verify_password with empty hash."""
        from services.friend_auth import verify_password

        assert verify_password("password", "") is False
        assert verify_password("password", None) is False

    def test_verify_password_invalid_format(self):
        """Test verify_password with invalid hash format."""
        from services.friend_auth import verify_password

        assert verify_password("password", "invalid") is False
        assert verify_password("password", "$pbkdf2$wrong") is False

    def test_generate_temporary_password(self):
        """Test temporary password generation."""
        from services.friend_auth import generate_temporary_password

        password = generate_temporary_password()

        assert len(password) >= 16
        assert isinstance(password, str)

    def test_generate_temporary_password_unique(self):
        """Test that temporary passwords are unique."""
        from services.friend_auth import generate_temporary_password

        passwords = [generate_temporary_password() for _ in range(10)]

        assert len(set(passwords)) == 10


class TestTOTP:
    """Tests for TOTP (Time-based One-Time Password)."""

    def test_generate_totp_secret(self):
        """Test TOTP secret generation."""
        from services.friend_auth import generate_totp_secret

        secret = generate_totp_secret()

        # Base32 chars
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)
        assert len(secret) >= 16

    def test_generate_totp(self):
        """Test TOTP code generation."""
        from services.friend_auth import generate_totp_secret, generate_totp

        secret = generate_totp_secret()
        code = generate_totp(secret)

        assert len(code) == 6
        assert code.isdigit()

    def test_verify_totp_correct(self):
        """Test TOTP verification with correct code."""
        from services.friend_auth import generate_totp_secret, generate_totp, verify_totp

        secret = generate_totp_secret()
        code = generate_totp(secret)

        assert verify_totp(secret, code) is True

    def test_verify_totp_wrong(self):
        """Test TOTP verification with wrong code."""
        from services.friend_auth import generate_totp_secret, verify_totp

        secret = generate_totp_secret()

        assert verify_totp(secret, "000000") is False
        assert verify_totp(secret, "123456") is False

    def test_verify_totp_empty(self):
        """Test TOTP verification with empty values."""
        from services.friend_auth import verify_totp

        assert verify_totp("", "123456") is False
        assert verify_totp("SECRET", "") is False
        assert verify_totp("", "") is False

    def test_verify_totp_invalid_code_length(self):
        """Test TOTP verification with wrong code length."""
        from services.friend_auth import generate_totp_secret, verify_totp

        secret = generate_totp_secret()

        assert verify_totp(secret, "12345") is False
        assert verify_totp(secret, "1234567") is False

    def test_get_totp_uri(self):
        """Test TOTP URI generation for QR codes."""
        from services.friend_auth import get_totp_uri

        uri = get_totp_uri("TESTSECRET", "John Doe", "mysite.com")

        assert "otpauth://totp/" in uri
        assert "TESTSECRET" in uri
        assert "John%20Doe" in uri
        assert "mysite.com" in uri


class TestAuthRequirements:
    """Tests for authentication requirement checking."""

    def test_no_auth_required_default(self):
        """Test that no auth is required by default."""
        from services.friend_auth import check_auth_requirements, PASSWORD_NOT_REQUIRED

        friend = {
            "usage_count": 5,
            "password_required": PASSWORD_NOT_REQUIRED,
        }

        req = check_auth_requirements(friend)

        assert req.needs_password is False
        assert req.needs_totp is False
        assert req.is_expired is False

    def test_password_always_required(self):
        """Test password required mode."""
        from services.friend_auth import (
            check_auth_requirements, hash_password, PASSWORD_ALWAYS_REQUIRED
        )

        friend = {
            "usage_count": 1,
            "password_required": PASSWORD_ALWAYS_REQUIRED,
            "password_hash": hash_password("test"),
        }

        req = check_auth_requirements(friend)

        assert req.needs_password is True

    def test_password_after_threshold_warning(self):
        """Test usage warning before threshold."""
        from services.friend_auth import check_auth_requirements, PASSWORD_AFTER_THRESHOLD

        friend = {
            "usage_count": 7,
            "password_required": PASSWORD_AFTER_THRESHOLD,
            "password_required_after": 10,
        }

        req = check_auth_requirements(friend)

        assert req.needs_password is False
        assert req.usage_warning is True

    def test_password_after_threshold_required(self):
        """Test password required after threshold."""
        from services.friend_auth import (
            check_auth_requirements, hash_password, PASSWORD_AFTER_THRESHOLD
        )

        friend = {
            "usage_count": 15,
            "password_required": PASSWORD_AFTER_THRESHOLD,
            "password_required_after": 10,
            "password_hash": hash_password("test"),
        }

        req = check_auth_requirements(friend)

        assert req.needs_password is True
        assert req.usage_warning is False  # Past threshold, no warning

    def test_totp_required_when_configured(self):
        """Test that TOTP is required when secret is set."""
        from services.friend_auth import check_auth_requirements, generate_totp_secret

        friend = {
            "usage_count": 1,
            "password_required": 0,
            "totp_secret": generate_totp_secret(),
        }

        req = check_auth_requirements(friend)

        assert req.needs_totp is True

    def test_expired_access(self):
        """Test expired access detection."""
        from services.friend_auth import check_auth_requirements

        friend = {
            "usage_count": 1,
            "password_required": 0,
            "expires_at": (datetime.now() - timedelta(days=1)).isoformat(),
        }

        req = check_auth_requirements(friend)

        assert req.is_expired is True
        assert "expired" in req.error_message.lower()

    def test_not_expired(self):
        """Test access that hasn't expired."""
        from services.friend_auth import check_auth_requirements

        friend = {
            "usage_count": 1,
            "password_required": 0,
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
        }

        req = check_auth_requirements(friend)

        assert req.is_expired is False

    def test_no_expiration_set(self):
        """Test access with no expiration."""
        from services.friend_auth import check_auth_requirements

        friend = {
            "usage_count": 1,
            "password_required": 0,
            "expires_at": None,
        }

        req = check_auth_requirements(friend)

        assert req.is_expired is False
