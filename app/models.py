from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ServiceBase(BaseModel):
    name: str
    url: str
    icon: str = ""
    description: str = ""
    display_order: int = 0
    subdomain: str = ""  # For SSO: e.g., "ombi" for ombi.blaha.io
    stack: str = ""  # Docker stack: media, infra, jitsi, priorities, etc.
    is_default: bool = False  # Auto-grant to new friends

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

class TokenResponse(BaseModel):
    token: str
