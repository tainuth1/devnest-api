"""
Authentication dependencies for FastAPI endpoints.
"""

import logging
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.enums import UserStatus
from app.core.security import decode_access_token
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.database import get_db
from app.modules.auth.models import User

logger = logging.getLogger("app.auth.dependencies")

http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency to extract and validate the JWT Bearer access token,
    query the DB for the user, and verify account status.

    Raises:
        HTTPException 401: Missing, malformed, expired, or invalid token, or user not found.
        HTTPException 403: Suspended, banned, or inactive user account.
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": "Missing or invalid authorization bearer credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
                status=AuditStatus.BLOCKED,
                details={"reason": "Subject claim missing in access token"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = uuid.UUID(user_id_str)
    except (InvalidTokenError, ValueError):
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": "Invalid or expired access token"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user: User | None = db.query(User).filter(User.id == user_id).first()

    if not user:
        audit_logger.log_event(
            event_type=AuditEventType.ACCESS_DENIED_UNAUTHENTICATED,
            status=AuditStatus.BLOCKED,
            details={"reason": f"User specified in token does not exist: {user_id_str}"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User specified in token does not exist.",
            headers={"WWW-Authenticate": "Bearer"},
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

