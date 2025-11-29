from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str
    url: str
    icon: str = ""
    description: str = ""
    display_order: int = 0
    subdomain: str = ""  # For SSO: e.g., "ombi" for ombi.yourdomain.com
    stack: str = ""  # Docker stack: media, infra, jitsi, priorities, etc.
    is_default: bool = False  # Auto-grant to new friends
    auth_type: str = "none"  # none, basic, forward-auth, jellyfin, ombi, overseerr, plex, nextcloud, mattermost, open
    github_repo: str = ""  # GitHub repo for CI status (e.g., "nelsonblaha/homepage")
    quick_join_params: str = ""  # JSON params for quick-join URLs, e.g. {"session": "blaha.io"}
    visible_to_friends: bool = True  # Whether this service appears in friend assignment UI

class ServiceCreate(ServiceBase):
    pass

class Service(ServiceBase):
    id: int

class AccessRequest(BaseModel):
    id: int
    friend_id: int
    service_id: int
    requested_at: Optional[datetime] = None
    status: str = "pending"
    friend_name: Optional[str] = None
    service_name: Optional[str] = None

class FriendBase(BaseModel):
    name: str

class FriendCreate(FriendBase):
    service_ids: list[int] = []

class FriendUpdate(BaseModel):
    name: Optional[str] = None
    service_ids: Optional[list[int]] = None

class Friend(FriendBase):
    id: int
    token: str
    created_at: Optional[datetime] = None
    last_visit: Optional[datetime] = None
    services: list[Service] = []

class FriendView(BaseModel):
    name: str
    services: list[Service]

class AdminLogin(BaseModel):
    password: str
    remember: bool = False  # "Remember me" for 30 days instead of 24 hours

class TokenResponse(BaseModel):
    token: str
