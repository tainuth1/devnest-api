"""
Authentication dependencies for FastAPI endpoints.

Authenticates requests by reading the `session_id` HttpOnly cookie,
validating the session record in the database, and returning the active User.
"""

import logging
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.enums import UserStatus
from app.core.cookie import SESSION_COOKIE_NAME
from app.core.security import hash_session_token
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.database import get_db
from app.modules.auth.models import User, UserSession

logger = logging.getLogger("app.auth.dependencies")


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    """
    FastAPI dependency to extract and validate the session cookie,
    look up the session record in the database, and return the active User.

    Raises:
        HTTPException 401: Missing, invalid, revoked, or expired session cookie,
                           or user not found.
        HTTPException 403: Suspended, banned, or inactive user account.
    """
    if not session_id:
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": "Session cookie is missing"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )

    token_hash = hash_session_token(session_id)
    session: UserSession | None = (
        db.query(UserSession)
        .filter(UserSession.token_hash == token_hash)
        .first()
    )

    if not session:
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": "Session not found in database"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    if not session.is_valid:
        reason = "Session has been revoked" if session.revoked else "Session has expired"
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": reason, "session_id": str(session.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )

    user: User | None = db.query(User).filter(User.id == session.user_id).first()

    if not user:
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": f"User for session does not exist: {session.user_id}"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this session no longer exists.",
        )

    if user.status == UserStatus.SUSPENDED:
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_STATUS_DENIED,
            status=AuditStatus.BLOCKED,
            user_id=user.id,
            details={"status": user.status.value},
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended.",
        )
    elif user.status == UserStatus.BANNED:
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_STATUS_DENIED,
            status=AuditStatus.BLOCKED,
            user_id=user.id,
            details={"status": user.status.value},
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been permanently banned.",
        )
    elif user.status == UserStatus.INACTIVE:
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_STATUS_DENIED,
            status=AuditStatus.BLOCKED,
            user_id=user.id,
            details={"status": user.status.value},
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is deactivated.",
        )

    if user.is_locked_out:
        audit_logger.log_event(
            event_type=AuditEventType.AUTH_BLOCKED_LOCKED,
            status=AuditStatus.BLOCKED,
            user_id=user.id,
            details={"locked_until": user.locked_until.isoformat() if user.locked_until else None},
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to multiple failed login attempts.",
        )

    return user
