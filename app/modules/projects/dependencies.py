"""
Project-Level Role-Based Access Control (RBAC) Dependencies.

OWASP A01 — Broken Access Control
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enforces strict server-side tenant isolation and RBAC at the project level,
strictly independent of any frontend client state or UI conditional rendering.

Permissions Matrix (from Section 2 of Business Logics Specification):
  - OWNER: Full control (create, view, update, delete, transfer, manage members, reorder)
  - ADMIN: Full operational control (view, update, lifecycle status, manage members, backups, tokens; CANNOT delete or transfer)
  - EDITOR: Workspace authoring (view, edit flows, schemas, docs; CANNOT update project status or details)
  - VIEWER: Read-only access (view artifacts, export, reorder own personal view; CANNOT edit or mutate)
  - NON-MEMBER: Denied (returns 404 to eliminate enumeration risks)
"""

import logging
from dataclasses import dataclass
from typing import Any
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.core.enums import ProjectRole
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.service import ProjectService

logger = logging.getLogger("app.projects.rbac")


@dataclass
class ProjectContext:
    """
    Verified execution context for project-scoped operations.
    Contains the verified Project, the calling User, and their ProjectMember membership record.
    """
    project: Project
    member: ProjectMember
    user: User

    @property
    def role(self) -> str:
        return self.member.role

    @property
    def is_owner(self) -> bool:
        return self.member.role == ProjectRole.OWNER.value

    @property
    def is_admin(self) -> bool:
        return self.member.role == ProjectRole.ADMIN.value

    @property
    def is_editor(self) -> bool:
        return self.member.role == ProjectRole.EDITOR.value

    @property
    def is_viewer(self) -> bool:
        return self.member.role == ProjectRole.VIEWER.value


def get_project_context(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectContext:
    """
    FastAPI dependency that:
      1. Resolves the project by 20-character project_code or UUID from path parameters.
      2. Validates that the caller is an active member in project_members.
      3. Returns 404 if project does not exist OR caller is not a member (OWASP tenant isolation).
    """
    identifier = request.path_params.get("project_code") or request.path_params.get("project_id")
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project identifier is required.",
        )

    project = ProjectService.get_project_by_id_or_code(db, identifier)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == current_user.id,
        )
        .first()
    )

    if not member:
        # Strictly return 404 to avoid revealing project existence to non-members
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return ProjectContext(
        project=project,
        member=member,
        user=current_user,
    )


def require_project_role(*allowed_roles: ProjectRole | str):
    """
    Dependency factory enforcing project-level RBAC on API routes.

    Args:
        *allowed_roles: Allowed ProjectRole values (e.g. ProjectRole.OWNER, ProjectRole.ADMIN).

    Returns:
        FastAPI dependency callable resolving to verified ProjectContext.

    Raises:
        HTTPException 404: If project does not exist or caller is not a member.
        HTTPException 403: If caller is a member but has insufficient role permissions.
    """
    allowed_values = {
        r.value if isinstance(r, ProjectRole) else str(r)
        for r in allowed_roles
    }

    def _dependency(
        context: ProjectContext = Depends(get_project_context),
        db: Session = Depends(get_db),
    ) -> ProjectContext:
        if context.member.role not in allowed_values:
            audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED_UNAUTHORIZED,
                status=AuditStatus.BLOCKED,
                user_id=context.user.id,
                details={
                    "project_id": str(context.project.id),
                    "project_code": context.project.project_code,
                    "caller_role": context.member.role,
                    "required_roles": sorted(list(allowed_values)),
                    "reason": "Insufficient project-level RBAC role",
                },
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of the following project roles: {', '.join(sorted(allowed_values))}.",
            )
        return context

    return _dependency


# ── Semantic RBAC Role Dependencies (Strictly Aligned with 2_BUSINESS_LOGICS.md Section 2) ──

#: Any active project member (OWNER, ADMIN, EDITOR, VIEWER)
require_project_member = require_project_role(
    ProjectRole.OWNER,
    ProjectRole.ADMIN,
    ProjectRole.EDITOR,
    ProjectRole.VIEWER,
)

#: Workspace authoring roles (OWNER, ADMIN, EDITOR)
require_project_editor_or_above = require_project_role(
    ProjectRole.OWNER,
    ProjectRole.ADMIN,
    ProjectRole.EDITOR,
)

#: Project administration roles (OWNER, ADMIN)
require_project_admin_or_owner = require_project_role(
    ProjectRole.OWNER,
    ProjectRole.ADMIN,
)

#: Project owner exclusive role (OWNER only)
require_project_owner = require_project_role(
    ProjectRole.OWNER,
)
