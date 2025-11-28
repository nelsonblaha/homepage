"""Tests for Pydantic models."""
import pytest
from pydantic import ValidationError


def test_service_model_validates_required_fields():
    """Test that Service model requires name and url."""
    from models import ServiceCreate

    # Valid service
    service = ServiceCreate(name="Test", url="https://test.local")
    assert service.name == "Test"
    assert service.url == "https://test.local"

    # Missing name
    with pytest.raises(ValidationError):
        ServiceCreate(url="https://test.local")

    # Missing url
    with pytest.raises(ValidationError):
        ServiceCreate(name="Test")


def test_service_model_defaults():
    """Test Service model default values."""
    from models import ServiceCreate

    service = ServiceCreate(name="Test", url="https://test.local")
    assert service.icon == ""
    assert service.description == ""
    assert service.display_order == 0
    assert service.subdomain == ""
    assert service.is_default is False


def test_friend_create_model():
    """Test FriendCreate model."""
    from models import FriendCreate

    friend = FriendCreate(name="Alice", service_ids=[1, 2, 3])
    assert friend.name == "Alice"
    assert friend.service_ids == [1, 2, 3]


def test_friend_create_default_services():
    """Test FriendCreate defaults to empty services list."""
    from models import FriendCreate

    friend = FriendCreate(name="Bob")
    assert friend.name == "Bob"
    assert friend.service_ids == []
