"""
Pydantic request / response schemas for the user admin module.

Validation rules are enforced here so the service layer stays clean.
"""

import uuid
from datetime import datetime
from pydantic import BaseModel
from app.core.enums import UserStatus


class UserDetailResponse(BaseModel):
    """Full user profile, returned by admin read endpoints."""

    id: str
    email: str
    username: str | None = None
    role: str
    status: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserListResponse(BaseModel):
    """Paginated list of users returned by GET /admin/users."""

    users: list[UserDetailResponse]
    skip: int
    limit: int
    total: int


class UpdateUserStatusRequest(BaseModel):
    """
    Body for PATCH /admin/users/{user_id}/status.

    Uses the UserStatus enum so only valid status strings are accepted —
    no free-text injection possible.
    """

    status: UserStatus


class UpdateUserStatusResponse(BaseModel):
    """Confirmation payload after a status change."""

    user_id: str
    status: str


class SystemInfoResponse(BaseModel):
    """Runtime system statistics returned by GET /admin/system/info."""

    app_name: str
    app_version: str
    current_time: str
    total_users: int
    active_users: int
