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


# =============================================================================
# SERVICE MODEL EXTENDED TESTS
# =============================================================================

def test_service_all_fields():
    """Test Service with all fields populated."""
    from models import Service

    service = Service(
        id=1,
        name="Jellyfin",
        url="https://jellyfin.example.com",
        icon="film",
        description="Media server",
        display_order=1,
        subdomain="jellyfin",
        stack="media",
        is_default=True,
        auth_type="jellyfin"
    )
    assert service.id == 1
    assert service.name == "Jellyfin"
    assert service.subdomain == "jellyfin"
    assert service.is_default is True
    assert service.auth_type == "jellyfin"
    assert service.stack == "media"


def test_service_auth_type_values():
    """Test Service auth_type can be various values."""
    from models import ServiceCreate

    # Various auth types that should be valid
    for auth_type in ["none", "basic", "jellyfin", "ombi", "overseerr"]:
        service = ServiceCreate(
            name="Test",
            url="http://test.com",
            auth_type=auth_type
        )
        assert service.auth_type == auth_type


def test_service_stack_grouping():
    """Test Service stack field for grouping."""
    from models import ServiceCreate

    media_service = ServiceCreate(name="S1", url="http://s1", stack="media")
    infra_service = ServiceCreate(name="S2", url="http://s2", stack="infrastructure")

    assert media_service.stack == "media"
    assert infra_service.stack == "infrastructure"


# =============================================================================
# FRIEND MODEL EXTENDED TESTS
# =============================================================================

def test_friend_update_partial():
    """Test FriendUpdate allows partial updates."""
    from models import FriendUpdate

    # Name only
    update = FriendUpdate(name="NewName")
    assert update.name == "NewName"
    assert update.service_ids is None

    # Services only
    update = FriendUpdate(service_ids=[1, 2])
    assert update.name is None
    assert update.service_ids == [1, 2]

    # Both
    update = FriendUpdate(name="Alice", service_ids=[3, 4])
    assert update.name == "Alice"
    assert update.service_ids == [3, 4]


def test_friend_model_complete():
    """Test Friend model with all fields."""
    from models import Friend, Service
    from datetime import datetime

    services = [
        Service(id=1, name="S1", url="http://s1.com"),
        Service(id=2, name="S2", url="http://s2.com")
    ]

    friend = Friend(
        id=1,
        name="Alice",
        token="abc123xyz",
        created_at=datetime(2024, 1, 1),
        last_visit=datetime(2024, 6, 15),
        services=services
    )

    assert friend.id == 1
    assert friend.name == "Alice"
    assert friend.token == "abc123xyz"
    assert len(friend.services) == 2
    assert friend.services[0].name == "S1"


def test_friend_view_for_public_display():
    """Test FriendView model for public pages."""
    from models import FriendView, Service

    view = FriendView(
        name="Alice",
        services=[Service(id=1, name="Plex", url="http://plex.local")]
    )
    assert view.name == "Alice"
    assert len(view.services) == 1
    # FriendView shouldn't expose token, id, etc.
    assert not hasattr(view, 'token')
    assert not hasattr(view, 'id')


# =============================================================================
# ACCESS REQUEST TESTS
# =============================================================================

def test_access_request_defaults():
    """Test AccessRequest default values."""
    from models import AccessRequest

    request = AccessRequest(id=1, friend_id=10, service_id=5)
    assert request.status == "pending"
    assert request.requested_at is None
    assert request.friend_name is None
    assert request.service_name is None


def test_access_request_with_enriched_data():
    """Test AccessRequest with joined data."""
    from models import AccessRequest
    from datetime import datetime

    request = AccessRequest(
        id=1,
        friend_id=10,
        service_id=5,
        requested_at=datetime(2024, 1, 1, 12, 0),
        status="approved",
        friend_name="Bob",
        service_name="Jellyfin"
    )
    assert request.status == "approved"
    assert request.friend_name == "Bob"
    assert request.service_name == "Jellyfin"


# =============================================================================
# ADMIN AUTH TESTS
# =============================================================================

def test_admin_login_remember_me():
    """Test AdminLogin remember me option."""
    from models import AdminLogin

    # Default is False
    login = AdminLogin(password="secret")
    assert login.remember is False

    # Can be True
    login = AdminLogin(password="secret", remember=True)
    assert login.remember is True


def test_admin_login_requires_password():
    """Test AdminLogin requires password field."""
    from models import AdminLogin

    with pytest.raises(ValidationError):
        AdminLogin()


def test_token_response():
    """Test TokenResponse model."""
    from models import TokenResponse

    response = TokenResponse(token="friend-unique-token-123")
    assert response.token == "friend-unique-token-123"


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_service_serialization():
    """Test Service model serializes correctly."""
    from models import Service

    service = Service(
        id=1,
        name="Test",
        url="http://test.com",
        stack="media",
        is_default=True
    )

    data = service.model_dump()
    assert data["id"] == 1
    assert data["name"] == "Test"
    assert data["stack"] == "media"
    assert data["is_default"] is True


def test_friend_serialization_with_nested_services():
    """Test Friend serializes with nested services."""
    from models import Friend, Service

    friend = Friend(
        id=1,
        name="Alice",
        token="abc",
        services=[
            Service(id=1, name="S1", url="http://s1.com"),
            Service(id=2, name="S2", url="http://s2.com")
        ]
    )

    data = friend.model_dump()
    assert data["id"] == 1
    assert data["name"] == "Alice"
    assert len(data["services"]) == 2
    assert data["services"][0]["name"] == "S1"
    assert data["services"][1]["id"] == 2
