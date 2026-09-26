"""
User admin service — business logic for admin user-management operations.

Keeps all domain logic out of the router layer. Raises HTTPException directly
since this is a small project with a single HTTP transport layer.

OWASP A01 notes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Role enforcement is handled upstream by the RBAC dependency in the router.
  The service trusts that the caller is already verified as ADMIN / DEVELOPER.
- UUID primary keys are used throughout — no sequential ID enumeration.
- Every mutating action is logged with admin_id + target_user_id for audit.
- Self-modification is explicitly blocked where relevant (e.g. status changes).
"""

import logging
import uuid
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.core.config import settings
from app.core.enums import UserStatus
from app.core.sanitize import sanitize_for_log
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.modules.auth.models import User, UserSession
from app.modules.user.schemas import (
    UserDetailResponse,
    UserListResponse,
    UpdateUserStatusResponse,
    SystemInfoResponse,
)

logger = logging.getLogger("app.user.service")


class UserAdminService:
    """Stateless user admin service. Each method receives a DB session explicitly."""

    @staticmethod
    def _to_detail(user: User) -> UserDetailResponse:
        """Map a User ORM object to the UserDetailResponse schema."""
        return UserDetailResponse(
            id=str(user.id),
            email=user.email,
            username=user.username,
            role=user.role.value,
            status=user.status.value,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    def list_users(
        db: Session,
        admin: User,
        skip: int = 0,
        limit: int = 50,
    ) -> UserListResponse:
        """
        Return a paginated list of all users.
        """
        # Cap limit to prevent accidental full-table dumps
        limit = min(limit, 100)

        users = db.query(User).offset(skip).limit(limit).all()

        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_USER_LISTED,
            status=AuditStatus.SUCCESS,
            user_id=admin.id,
            details={"count": len(users), "skip": skip, "limit": limit},
            db=db,
        )


        return UserListResponse(
            users=[UserAdminService._to_detail(u) for u in users],
            skip=skip,
            limit=limit,
            total=len(users),
        )

    @staticmethod
    def get_user(db: Session, admin: User, user_id: uuid.UUID) -> UserDetailResponse:
        """
        Retrieve a single user's full profile by UUID.
        """
        user: User | None = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_USER_VIEWED,
            status=AuditStatus.SUCCESS,
            user_id=admin.id,
            details={"target_user_id": str(user.id)},
            db=db,
        )


        return UserAdminService._to_detail(user)

    @staticmethod
    def update_user_status(
        db: Session,
        admin: User,
        user_id: uuid.UUID,
        new_status: UserStatus,
    ) -> UpdateUserStatusResponse:
        """
        Update the account status of any user.
        """
        if user_id == admin.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot modify their own account status.",
            )

        user: User | None = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        old_status = user.status
        user.status = new_status

        # Immediately revoke all active sessions when a user is suspended or banned
        # so they are forced out of all devices without waiting for session expiry.
        if new_status in (UserStatus.SUSPENDED, UserStatus.BANNED, UserStatus.INACTIVE):
            active_sessions = (
                db.query(UserSession)
                .filter(UserSession.user_id == user.id, UserSession.revoked == False)
                .all()
            )
            for sess in active_sessions:
                sess.revoked = True

        db.commit()

        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_USER_STATUS_CHANGED,
            status=AuditStatus.SUCCESS,
            user_id=admin.id,
            details={
                "target_user_id": str(user.id),
                "old_status": old_status.value,
                "new_status": new_status.value,
            },
            db=db,
        )


        return UpdateUserStatusResponse(
            user_id=str(user.id),
            status=new_status.value,
        )

    @staticmethod
    def get_system_info(db: Session, requesting_user: User) -> SystemInfoResponse:
        """
        Return basic runtime statistics about the system.
        """
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.status == UserStatus.ACTIVE).count()

        audit_logger.log_event(
            event_type=AuditEventType.ADMIN_SYSTEM_INFO_ACCESSED,
            status=AuditStatus.SUCCESS,
            user_id=requesting_user.id,
            details={"role": requesting_user.role.value},
            db=db,
        )


        return SystemInfoResponse(
            app_name=settings.APP_NAME,
            app_version=settings.APP_VERSION,
            current_time=tz.now().isoformat(),
            total_users=total_users,
            active_users=active_users,
        )

