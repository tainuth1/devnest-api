from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationActor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    actor_id: Optional[str] = None
    project_id: Optional[str] = None
    type: str
    category: str
    title: str
    message: str
    link_url: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    is_read: bool
    action_status: Optional[str] = None
    read_at: Optional[str] = None
    created_at: str
    actor: Optional[NotificationActor] = None


class PaginationInfo(BaseModel):
    page: int
    limit: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class NotificationListResponseData(BaseModel):
    items: List[NotificationResponse]
    pagination: PaginationInfo
    unread_count: int


class UnreadCountResponseData(BaseModel):
    unread_count: int


class NotificationActionRequest(BaseModel):
    action: str = Field(
        ...,
        description="Action result to record, e.g. ACCEPTED, DECLINED, DISMISSED",
        min_length=1,
        max_length=20,
    )
