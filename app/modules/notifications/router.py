import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.notifications.schemas import NotificationActionRequest
from app.modules.notifications.service import NotificationService
from app.shared import responses as res

logger = logging.getLogger("app.notifications.router")

router = APIRouter()


@router.get(
    "",
    summary="List User Notifications",
    description="Retrieve paginated notifications for the current authenticated user with optional read, category, or type filters.",
    response_model=None,
)
def list_notifications(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    is_read: Optional[bool] = Query(default=None, description="Filter by read status"),
    category: Optional[str] = Query(default=None, description="Filter by category (e.g. COLLABORATION, OWNERSHIP)"),
    type: Optional[str] = Query(default=None, description="Filter by notification type"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = NotificationService.get_user_notifications(
        db=db,
        user_id=current_user.id,
        page=page,
        limit=limit,
        is_read=is_read,
        category=category,
        type=type,
    )
    return res.ok(message="Notifications retrieved.", data=result)


@router.get(
    "/unread-count",
    summary="Get Unread Notification Count",
    description="Fast count query for the header notification bell indicator badge.",
    response_model=None,
)
def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = NotificationService.get_unread_count(db=db, user_id=current_user.id)
    return res.ok(
        message="Unread notifications count retrieved.",
        data={"unread_count": count},
    )


@router.patch(
    "/mark-all-read",
    summary="Mark All Notifications as Read",
    description="Marks all unread notifications belonging to the authenticated user as read.",
    response_model=None,
)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = NotificationService.mark_all_as_read(db=db, user_id=current_user.id)
    return res.ok(
        message="All notifications marked as read.",
        data={"updated_count": count},
    )


@router.patch(
    "/{notification_id}/read",
    summary="Mark Notification as Read",
    description="Marks a specific notification as read when clicked or previewed by the user.",
    response_model=None,
)
def mark_as_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = NotificationService.mark_as_read(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    return res.ok(message="Notification marked as read.", data=updated)


@router.patch(
    "/{notification_id}/action",
    summary="Update Notification Action Status",
    description="Records user action on an interactive notification (e.g. ACCEPTED, DECLINED, DISMISSED).",
    response_model=None,
)
def update_action_status(
    notification_id: str,
    body: NotificationActionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    updated = NotificationService.update_action_status(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
        action=body.action,
    )
    return res.ok(message="Notification action updated.", data=updated)


@router.delete(
    "/{notification_id}",
    summary="Delete / Dismiss Notification",
    description="Removes a notification from the user's notification list.",
    response_model=None,
)
def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    NotificationService.delete_notification(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    return res.ok(message="Notification deleted successfully.")
