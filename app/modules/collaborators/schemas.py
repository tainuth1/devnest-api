import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import ProjectRole

VALID_INVITATION_ROLES = [
    ProjectRole.ADMIN.value,
    ProjectRole.EDITOR.value,
    ProjectRole.VIEWER.value,
]
VALID_MEMBER_ROLES = [
    ProjectRole.OWNER.value,
    ProjectRole.ADMIN.value,
    ProjectRole.EDITOR.value,
    ProjectRole.VIEWER.value,
]


# ── Response Schemas ────────────────────────────────────────────────────────

class ProjectMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime
    is_you: bool = False


class CollaboratorInviteResponseData(BaseModel):
    invitation_id: uuid.UUID
    invitee_email: str
    role: str
    expires_at: datetime
    status: str


class InviterSummary(BaseModel):
    id: uuid.UUID
    email: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class PendingInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    inviter_user_id: uuid.UUID
    invitee_email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    inviter: Optional[InviterSummary] = None


class CollaboratorRoleUpdateResponseData(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    role: str
    updated_at: datetime


class InvitationAcceptResponseData(BaseModel):
    project_id: uuid.UUID
    project_code: str
    project_name: str
    role: str


class InvitationDetailResponseData(BaseModel):
    invitation_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    project_code: str
    inviter_name: str
    invitee_email: str
    role: str
    expires_at: datetime
    status: str


# ── Request Payloads ────────────────────────────────────────────────────────

class CollaboratorInviteRequest(BaseModel):
    email: EmailStr = Field(..., description="Target email of the collaborator to invite")
    role: str = Field(default=ProjectRole.EDITOR.value, description="Role to assign: ADMIN, EDITOR, or VIEWER")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper == ProjectRole.OWNER.value:
            raise ValueError("Project ownership cannot be assigned via invitation. Use ownership transfer instead.")
        if v_upper not in VALID_INVITATION_ROLES:
            raise ValueError(f"Invalid invitation role '{v}'. Must be one of: {', '.join(VALID_INVITATION_ROLES)}")
        return v_upper


class CollaboratorRoleUpdateRequest(BaseModel):
    role: str = Field(..., description="Updated role: ADMIN, EDITOR, or VIEWER")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper not in VALID_MEMBER_ROLES:
            raise ValueError(f"Invalid role '{v}'. Must be one of: {', '.join(VALID_MEMBER_ROLES)}")
        return v_upper
