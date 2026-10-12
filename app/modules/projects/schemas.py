import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ProjectRole, ProjectStatus

VALID_STATUSES = [s.value for s in ProjectStatus]
VALID_ROLES = [r.value for r in ProjectRole]


# ── Response Data Schemas ───────────────────────────────────────────────────

class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_code: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    order_index: int = 0
    is_pinned: bool = False
    color: str = "#6366F1"
    icon: str = "folder"
    my_role: str
    members_count: int = 1
    created_at: datetime
    updated_at: datetime


class PaginationInfo(BaseModel):
    page: int
    limit: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class ProjectListResponseData(BaseModel):
    items: list[ProjectListItem]
    pagination: PaginationInfo


class ProjectMemberItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    role: str
    initials: str
    avatar_url: Optional[str] = None


class ProjectDetailData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_code: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    color: str = "#6366F1"
    icon: str = "folder"
    settings: dict[str, Any] = Field(default_factory=dict)
    dialect: str = "POSTGRESQL 16"
    flows_count: int = 0
    tables_count: int = 0
    relations_count: int = 0
    documents_count: int = 0
    backup_status: str = "Healthy"
    backup_size: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    pending_invites_count: int = 0
    members: list[ProjectMemberItem] = Field(default_factory=list)
    ownership_transfer: Optional[dict[str, Any]] = None


class ProjectOrderResponseData(BaseModel):
    project_id: uuid.UUID
    project_code: str
    user_id: uuid.UUID
    order_index: int
    updated_at: datetime


class ProjectStatusResponseData(BaseModel):
    id: uuid.UUID
    project_code: str
    status: str
    updated_at: datetime


# ── Request Payloads ────────────────────────────────────────────────────────

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Project display name")
    description: Optional[str] = Field(None, description="Architecture & planning summary")
    settings: Optional[dict[str, Any]] = Field(default_factory=dict, description="Project settings and preferences")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Project name cannot be blank.")
        return cleaned


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7)
    icon: Optional[str] = Field(None, max_length=50)
    settings: Optional[dict[str, Any]] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {', '.join(VALID_STATUSES)}")
        return v

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Project name cannot be blank.")
            return cleaned
        return v


class ProjectStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Operational lifecycle status")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Must be one of: {', '.join(VALID_STATUSES)}")
        return v


class ProjectOrderUpdateRequest(BaseModel):
    order_index: int = Field(..., ge=0, description="Personalized display order index")
    is_pinned: Optional[bool] = Field(None, description="Optional pin to top state")


class ProjectBatchOrderItem(BaseModel):
    project_id: str = Field(..., description="Project UUID or project_code")
    order_index: int = Field(..., ge=0, description="Personalized display order index")
    is_pinned: Optional[bool] = None


class ProjectBatchReorderRequest(BaseModel):
    items: list[ProjectBatchOrderItem] = Field(..., min_length=1, description="List of projects to reorder")


class ProjectDeleteRequest(BaseModel):
    confirm_slug: str = Field(..., description="Confirmation project slug to prevent accidental deletion")
