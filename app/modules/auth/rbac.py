"""
Role-Based Access Control (RBAC) dependencies.

OWASP A01 — Broken Access Control
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These FastAPI dependencies enforce *authorization* (what an authenticated
user is *allowed* to do) on top of authentication (who they are).

Usage
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    from app.modules.auth.rbac import require_role
    from app.core.enums import UserRole

    # Single role
    @router.get("/admin/stats", dependencies=[Depends(require_role(UserRole.ADMIN))])
    async def admin_stats(): ...

    # Multiple allowed roles (any match grants access)
    @router.get(
        "/dashboard",
        dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DEVELOPER))],
    )
    async def dashboard(): ...

    # Inject the verified user object AND enforce role
    @router.delete("/admin/users/{user_id}")
    async def delete_user(
        user_id: uuid.UUID,
        current_user: User = Depends(require_role(UserRole.ADMIN)),
    ): ...

    # Any authenticated, active user (convenience alias for get_current_user)
    @router.get("/protected")
    async def protected(user: User = Depends(require_active_user)): ...

Security contract
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - All role checks are performed SERVER-SIDE. Never trust client claims.
  - Deny by default: if the user's role is not in the allowed set → 403.
  - Every denied attempt is logged as a security warning for audit purposes.
  - `require_role()` chains on top of `get_current_user`, which already
    validates the session cookie, checks account status, and checks lockout state.
"""

import logging
import uuid
from functools import lru_cache
from fastapi import Depends, HTTPException, status

from app.core.enums import UserRole
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User

logger = logging.getLogger("app.auth.rbac")


def require_role(*roles: UserRole):
    """
    Dependency factory that enforces Role-Based Access Control.

    Returns a FastAPI dependency that:
      1. Authenticates the request via ``get_current_user``.
      2. Checks that the user's role is in the allowed ``roles`` set.
      3. Logs and raises HTTP 403 if the role is insufficient.

    Args:
        *roles: One or more ``UserRole`` values that are permitted.

    Returns:
        A FastAPI dependency callable that resolves to the authenticated ``User``.

    Raises:
        HTTPException 403: If the authenticated user's role is not in ``roles``.

    Example::

        @router.get("/admin/data", dependencies=[Depends(require_role(UserRole.ADMIN))])
        async def admin_data(): ...
    """
    allowed = frozenset(roles)

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            from app.core.audit import audit_logger, AuditEventType, AuditStatus
            audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED_UNAUTHORIZED,
                status=AuditStatus.BLOCKED,
                user_id=current_user.id,
                details={
                    "user_role": current_user.role.value,
                    "required_roles": [r.value for r in allowed],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        logger.debug(
            "==> Role check passed | user_id=%s role=%s",
            current_user.id,
            current_user.role.value,
        )
        return current_user


    return _check


# ---------------------------------------------------------------------------
# Convenience alias — use instead of get_current_user for clarity in routes
# ---------------------------------------------------------------------------

async def require_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency that resolves to the currently authenticated, active user.

    This is a semantic alias for ``get_current_user`` with an explicit name
    that signals "this endpoint requires a fully active authenticated user."
    Use it on any protected route to make the intent self-documenting.

    Raises:
        HTTPException 401: Missing / invalid token.
        HTTPException 403: Suspended, banned, or inactive account.
    """
    return current_user


# Admin-only shortcut

#: Convenience dependency — equivalent to ``require_role(UserRole.ADMIN)``.
#: Import and use as ``Depends(require_admin)`` for brevity.
require_admin = require_role(UserRole.ADMIN)

# Import and use as ``Depends(require_developer)``
require_developer = require_role(UserRole.DEVELOPER)

#: Allows both ADMIN and DEVELOPER roles (e.g. internal tooling endpoints).
require_admin_or_developer = require_role(UserRole.ADMIN, UserRole.DEVELOPER)
