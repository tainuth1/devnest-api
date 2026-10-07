import logging
import math
import uuid
from typing import Any, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.core.enums import (
    NotificationActionStatus,
    NotificationCategory,
    NotificationType,
)
from app.modules.auth.models import User
from app.modules.notifications.models import Notification
from app.modules.projects.models import ProjectMember

logger = logging.getLogger("app.notifications.service")


class NotificationService:
    @staticmethod
    def _parse_uuid(val: Any, field_name: str = "ID") -> uuid.UUID:
        if isinstance(val, uuid.UUID):
            return val
        try:
            return uuid.UUID(str(val))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name} format.",
            )

    @classmethod
    def _serialize_notification(cls, notif: Notification) -> dict[str, Any]:
        actor_data = None
        if notif.actor:
            actor_data = {
                "id": str(notif.actor.id),
                "email": notif.actor.email,
                "username": notif.actor.username,
                "first_name": notif.actor.first_name,
                "last_name": notif.actor.last_name,
                "avatar_url": notif.actor.avatar_url,
            }

        return {
            "id": str(notif.id),
            "user_id": str(notif.user_id),
            "actor_id": str(notif.actor_id) if notif.actor_id else None,
            "project_id": str(notif.project_id) if notif.project_id else None,
            "type": notif.type,
            "category": notif.category,
            "title": notif.title,
            "message": notif.message,
            "link_url": notif.link_url,
            "data": notif.data or {},
            "is_read": notif.is_read,
            "action_status": notif.action_status,
            "read_at": notif.read_at.isoformat() if notif.read_at else None,
            "created_at": notif.created_at.isoformat(),
            "actor": actor_data,
        }

    # ── Dispatching Helpers ───────────────────────────────────────────────────

    @classmethod
    def send_to_user(
        cls,
        db: Session,
        user_id: Any,
        type: str,
        category: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        actor_id: Optional[Any] = None,
        project_id: Optional[Any] = None,
        data: Optional[dict[str, Any]] = None,
        action_status: Optional[str] = NotificationActionStatus.PENDING.value,
    ) -> Notification:
        """
        Dispatches an in-app notification to a single user.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        parsed_actor_id = cls._parse_uuid(actor_id, "Actor ID") if actor_id else None
        parsed_project_id = cls._parse_uuid(project_id, "Project ID") if project_id else None

        notification = Notification(
            user_id=parsed_user_id,
            actor_id=parsed_actor_id,
            project_id=parsed_project_id,
            type=type,
            category=category,
            title=title,
            message=message,
            link_url=link_url,
            data=data or {},
            action_status=action_status,
            created_at=tz.now(),
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        logger.info(
            "Notification dispatched: user_id=%s type=%s title='%s'",
            parsed_user_id,
            type,
            title,
        )
        return notification

    @classmethod
    def send_to_users(
        cls,
        db: Session,
        user_ids: List[Any],
        type: str,
        category: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        actor_id: Optional[Any] = None,
        project_id: Optional[Any] = None,
        data: Optional[dict[str, Any]] = None,
        action_status: Optional[str] = NotificationActionStatus.PENDING.value,
    ) -> List[Notification]:
        """
        Dispatches identical notifications in bulk to multiple users.
        """
        parsed_actor_id = cls._parse_uuid(actor_id, "Actor ID") if actor_id else None
        parsed_project_id = cls._parse_uuid(project_id, "Project ID") if project_id else None
        now = tz.now()

        notifications = []
        for uid in user_ids:
            parsed_uid = cls._parse_uuid(uid, "User ID")
            notifications.append(
                Notification(
                    user_id=parsed_uid,
                    actor_id=parsed_actor_id,
                    project_id=parsed_project_id,
                    type=type,
                    category=category,
                    title=title,
                    message=message,
                    link_url=link_url,
                    data=data or {},
                    action_status=action_status,
                    created_at=now,
                )
            )

        if notifications:
            db.add_all(notifications)
            db.commit()
            for n in notifications:
                db.refresh(n)

        return notifications

    @classmethod
    def send_to_project_members(
        cls,
        db: Session,
        project_id: Any,
        type: str,
        category: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        actor_id: Optional[Any] = None,
        exclude_user_ids: Optional[List[Any]] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Broadcasts an in-app notification to all active collaborators of a project.
        """
        parsed_project_id = cls._parse_uuid(project_id, "Project ID")
        excluded_set = {
            cls._parse_uuid(u, "Exclude User ID") for u in (exclude_user_ids or [])
        }

        members = (
            db.query(ProjectMember.user_id)
            .filter(ProjectMember.project_id == parsed_project_id)
            .all()
        )

        target_user_ids = [m.user_id for m in members if m.user_id not in excluded_set]
        if not target_user_ids:
            return 0

        created = cls.send_to_users(
            db=db,
            user_ids=target_user_ids,
            type=type,
            category=category,
            title=title,
            message=message,
            link_url=link_url,
            actor_id=actor_id,
            project_id=parsed_project_id,
            data=data,
        )
        return len(created)

    @classmethod
    def broadcast_to_all_users(
        cls,
        db: Session,
        type: str,
        category: str,
        title: str,
        message: str,
        link_url: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> int:
        """
        Broadcasts a system-wide announcement to all active users.
        """
        active_users = db.query(User.id).filter(User.status == "active").all()
        target_user_ids = [u.id for u in active_users]
        if not target_user_ids:
            return 0

        created = cls.send_to_users(
            db=db,
            user_ids=target_user_ids,
            type=type,
            category=category,
            title=title,
            message=message,
            link_url=link_url,
            data=data,
        )
        return len(created)

    # ── Retrieval & Mutation Queries ──────────────────────────────────────────

    @classmethod
    def get_user_notifications(
        cls,
        db: Session,
        user_id: Any,
        page: int = 1,
        limit: int = 20,
        is_read: Optional[bool] = None,
        category: Optional[str] = None,
        type: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Retrieves paginated notifications for the specified user with optional filters.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        page = max(1, page)
        limit = min(max(1, limit), 100)
        offset = (page - 1) * limit

        query = db.query(Notification).filter(Notification.user_id == parsed_user_id)

        if is_read is not None:
            query = query.filter(Notification.is_read == is_read)
        if category:
            query = query.filter(Notification.category == category)
        if type:
            query = query.filter(Notification.type == type)

        total_items = query.count()
        total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

        notifications = (
            query.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        unread_count = cls.get_unread_count(db, parsed_user_id)

        return {
            "items": [cls._serialize_notification(n) for n in notifications],
            "pagination": {
                "page": page,
                "limit": limit,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "unread_count": unread_count,
        }

    @classmethod
    def get_unread_count(cls, db: Session, user_id: Any) -> int:
        """
        Fast unread count query for the header notification bell indicator.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        return (
            db.query(func.count(Notification.id))
            .filter(
                Notification.user_id == parsed_user_id,
                Notification.is_read == False,  # noqa: E712
            )
            .scalar()
            or 0
        )

    @classmethod
    def mark_as_read(
        cls,
        db: Session,
        user_id: Any,
        notification_id: Any,
    ) -> dict[str, Any]:
        """
        Marks a specific notification as read.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        parsed_notif_id = cls._parse_uuid(notification_id, "Notification ID")

        notification = (
            db.query(Notification)
            .filter(
                Notification.id == parsed_notif_id,
                Notification.user_id == parsed_user_id,
            )
            .first()
        )
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = tz.now()
            db.commit()
            db.refresh(notification)

        return cls._serialize_notification(notification)

    @classmethod
    def mark_all_as_read(cls, db: Session, user_id: Any) -> int:
        """
        Marks all unread notifications for a user as read.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        now = tz.now()

        updated_count = (
            db.query(Notification)
            .filter(
                Notification.user_id == parsed_user_id,
                Notification.is_read == False,  # noqa: E712
            )
            .update(
                {"is_read": True, "read_at": now},
                synchronize_session=False,
            )
        )
        db.commit()
        return updated_count

    @classmethod
    def delete_notification(
        cls,
        db: Session,
        user_id: Any,
        notification_id: Any,
    ) -> bool:
        """
        Dismisses / deletes a notification for a user.
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        parsed_notif_id = cls._parse_uuid(notification_id, "Notification ID")

        notification = (
            db.query(Notification)
            .filter(
                Notification.id == parsed_notif_id,
                Notification.user_id == parsed_user_id,
            )
            .first()
        )
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        db.delete(notification)
        db.commit()
        return True

    @classmethod
    def update_action_status(
        cls,
        db: Session,
        user_id: Any,
        notification_id: Any,
        action: str,
    ) -> dict[str, Any]:
        """
        Updates the action_status of an interactive notification (e.g. ACCEPTED, DECLINED, DISMISSED).
        """
        parsed_user_id = cls._parse_uuid(user_id, "User ID")
        parsed_notif_id = cls._parse_uuid(notification_id, "Notification ID")

        notification = (
            db.query(Notification)
            .filter(
                Notification.id == parsed_notif_id,
                Notification.user_id == parsed_user_id,
            )
            .first()
        )
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found.",
            )

        notification.action_status = action.upper()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = tz.now()

        db.commit()
        db.refresh(notification)
        return cls._serialize_notification(notification)
