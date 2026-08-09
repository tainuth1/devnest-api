"""
User admin router.

OWASP A01 — Broken Access Control: Role-Based Access Control
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All endpoints in this file are admin-protected at the router level.
The router declaration below locks down every route automatically:

    router = APIRouter(dependencies=[Depends(require_admin)])

RBAC patterns used in this file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Pattern A — Router-level guard (all routes inherit, no per-route boilerplate):
      router = APIRouter(dependencies=[Depends(require_admin)])

  Pattern B — Per-route injection (resolve the admin User object for use in handler):
      async def endpoint(admin: User = Depends(require_admin)): ...

  Pattern C — Multi-role override (explicitly widen access for specific routes):
      @router.get("/route", dependencies=[Depends(require_admin_or_developer)])
      async def endpoint(user: User = Depends(require_admin_or_developer)): ...

Rule: NEVER add an endpoint to this router without a ``require_role`` dependency.
"""

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.enums import UserStatus
from app.database import get_db
from app.modules.auth.models import User
from app.modules.auth.rbac import require_admin, require_admin_or_developer
from app.modules.user.schemas import (
    UserDetailResponse,
    UserListResponse,
    UpdateUserStatusRequest,
    UpdateUserStatusResponse,
    SystemInfoResponse,
)
from app.modules.user.service import UserAdminService
from app.shared import responses as res

# ─────────────────────────────────────────────────────────────────────────────
# Pattern A: router-level RBAC — every route inherits require_admin by default.
# ─────────────────────────────────────────────────────────────────────────────
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get(
    "/users",
    summary="List all users",
    description=(
        "Returns a paginated list of all registered users. "
        "**Requires ADMIN role.** Regular users receive HTTP 403."
    ),
    response_description="Paginated user list returned successfully.",
)
async def list_users(
    # Pattern B: inject the verified admin User object
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0, description="Number of records to skip."),
    limit: int = Query(default=50, ge=1, le=100, description="Max records to return (1–100)."),
):
    result: UserListResponse = UserAdminService.list_users(
        db=db, admin=admin, skip=skip, limit=limit,
    )
    return res.ok(
        message=f"Returned {result.total} users.",
        data=result.model_dump(mode="json"),
    )


@router.get(
    "/users/{user_id}",
    summary="Get user by ID",
    description=(
        "Retrieves full profile details for any user by their UUID. "
        "**Requires ADMIN role.**"
    ),
    response_description="User details returned successfully.",
)
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result: UserDetailResponse = UserAdminService.get_user(
        db=db, admin=admin, user_id=user_id,
    )
    return res.ok(
        message="User details retrieved successfully.",
        data=result.model_dump(mode="json"),
    )


@router.patch(
    "/users/{user_id}/status",
    summary="Update user account status",
    description=(
        "Updates the account status of any user (active / inactive / suspended / banned). "
        "**Requires ADMIN role.** Admins cannot change their own status."
    ),
    response_description="User status updated successfully.",
)
async def update_user_status(
    user_id: uuid.UUID,
    body: UpdateUserStatusRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result: UpdateUserStatusResponse = UserAdminService.update_user_status(
        db=db, admin=admin, user_id=user_id, new_status=body.status,
    )
    return res.ok(
        message=f"User status updated to '{result.status}'.",
        data=result.model_dump(),
    )



@router.get(
    "/system/info",
    summary="System info",
    description=(
        "Returns basic runtime system information and user statistics. "
        "**Requires ADMIN or DEVELOPER role.**"
    ),
    response_description="System info returned successfully.",
    # Pattern C: explicitly override the router-level require_admin for this route
    dependencies=[Depends(require_admin_or_developer)],
)
async def system_info(
    requesting_user: User = Depends(require_admin_or_developer),
    db: Session = Depends(get_db),
):
    result: SystemInfoResponse = UserAdminService.get_system_info(
        db=db, requesting_user=requesting_user,
    )
    return res.ok(
        message="System info retrieved.",
        data=result.model_dump(),
    )
