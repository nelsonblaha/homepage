"""Unit tests for credential generation module."""
import pytest
from services.credentials import generate_username, generate_password


def test_generate_username_simple():
    """Test basic username generation."""
    assert generate_username("Annette", "transmission") == "annette_transmission"
    assert generate_username("Test", "sonarr") == "test_sonarr"


def test_generate_username_with_spaces():
    """Test username generation with spaces in friend name."""
    assert generate_username("Test User", "transmission") == "testuser_transmission"
    assert generate_username("John Doe", "radarr") == "johndoe_radarr"


def test_generate_username_with_special_chars():
    """Test username generation with special characters."""
    assert generate_username("Test User!", "transmission") == "testuser_transmission"
    assert generate_username("A@B#C", "sonarr") == "abc_sonarr"
    assert generate_username("Name-With-Dashes", "lidarr") == "namewithdashes_lidarr"


def test_generate_username_lowercase():
    """Test that usernames are always lowercase."""
    assert generate_username("ANNETTE", "TRANSMISSION") == "annette_transmission"
    assert generate_username("MixedCase", "MixedService") == "mixedcase_mixedservice"


def test_generate_password_length():
    """Test that generated passwords have correct length."""
    pw = generate_password(24)
    assert len(pw) == 24

    pw = generate_password(32)
    assert len(pw) == 32

    pw = generate_password(16)
    assert len(pw) == 16


def test_generate_password_complexity():
    """Test that passwords have required complexity."""
    pw = generate_password(24)

    # Should have uppercase
    assert any(c.isupper() for c in pw), f"Password missing uppercase: {pw}"

    # Should have lowercase
    assert any(c.islower() for c in pw), f"Password missing lowercase: {pw}"

    # Should have digits
    assert any(c.isdigit() for c in pw), f"Password missing digits: {pw}"

    # Should have special characters
    assert any(c in "!@#$%^&*-_=+" for c in pw), f"Password missing special chars: {pw}"


def test_generate_password_no_ambiguous_chars():
    """Test that passwords don't contain ambiguous characters."""
    # Generate many passwords to test randomness
    for _ in range(100):
        pw = generate_password(24)

        # Should not contain ambiguous characters
        assert '0' not in pw, f"Password contains '0': {pw}"
        assert 'O' not in pw, f"Password contains 'O': {pw}"
        assert '1' not in pw, f"Password contains '1': {pw}"
        assert 'l' not in pw, f"Password contains 'l': {pw}"
        assert 'I' not in pw, f"Password contains 'I': {pw}"
        assert 'o' not in pw, f"Password contains 'o': {pw}"


def test_generate_password_unique():
    """Test that passwords are unique (not deterministic)."""
    passwords = [generate_password(24) for _ in range(10)]

    # All passwords should be unique
    assert len(set(passwords)) == len(passwords), "Generated passwords are not unique"


def test_generate_password_randomness():
    """Test that password generation has good randomness."""
    # Generate multiple passwords and check they're different
    pw1 = generate_password(24)
    pw2 = generate_password(24)
    pw3 = generate_password(24)

    # All should be different
    assert pw1 != pw2
    assert pw2 != pw3
    assert pw1 != pw3

    # Should have different character distributions
    # (This is a weak test but helps catch deterministic generators)
    assert pw1[0] != pw2[0] or pw1[1] != pw2[1] or pw1[2] != pw2[2]
