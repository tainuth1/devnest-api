import logging
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.collaborators.schemas import (
    CollaboratorInviteRequest,
    CollaboratorInviteResponseData,
    CollaboratorRoleUpdateRequest,
    CollaboratorRoleUpdateResponseData,
    InvitationAcceptResponseData,
    InvitationDetailResponseData,
    PendingInvitationResponse,
    ProjectMemberResponse,
)
from app.modules.collaborators.service import CollaboratorService
from app.modules.projects.dependencies import (
    ProjectContext,
    require_project_admin_or_owner,
    require_project_member,
)
from app.shared import responses as res

logger = logging.getLogger("app.collaborators.router")

# Router mounted under /projects (e.g. /api/projects)
project_collaborators_router = APIRouter()

# Router mounted under /invitations (e.g. /api/invitations)
invitations_router = APIRouter()


# ── 4.1 List Project Members & Roles ──────────────────────────────────────────

@project_collaborators_router.get(
    "/{project_id}/members",
    summary="List Project Members & Roles",
    description="Returns all active project members and their assigned RBAC roles. Accessible by any member (OWNER, ADMIN, EDITOR, VIEWER).",
    response_model=None,
)
def list_project_members(
    project_id: str,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    members = CollaboratorService.list_project_members(db=db, context=context)
    return res.ok(message="Project members retrieved.", data=members)


# ── 4.2 Invite Collaborator to Project ────────────────────────────────────────

@project_collaborators_router.post(
    "/{project_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    summary="Invite Collaborator to Project",
    description="Generates a secure invitation token in project_invitations and dispatches an invitation email with a 7-day expiration deadline. Requires OWNER or ADMIN (Admins can only invite EDITOR or VIEWER).",
)
async def invite_collaborator(
    project_id: str,
    data: CollaboratorInviteRequest,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    result = await CollaboratorService.invite_collaborator(
        db=db,
        context=context,
        data=data,
    )
    return res.created(message=f"Invitation dispatched to {data.email}.", data=result)


# ── 4.3 List Pending Project Invitations ──────────────────────────────────────

@project_collaborators_router.get(
    "/{project_id}/invitations",
    summary="List Pending Project Invitations",
    description="Returns array of pending, unaccepted invitation records. Requires OWNER or ADMIN.",
)
def list_pending_invitations(
    project_id: str,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    result = CollaboratorService.list_pending_invitations(db=db, context=context)
    return res.ok(message="Pending invitations retrieved.", data=result)


# ── 4.4 Revoke / Cancel Invitation ───────────────────────────────────────────

@project_collaborators_router.delete(
    "/{project_id}/invitations/{invitation_id}",
    summary="Revoke / Cancel Invitation",
    description="Revokes an active invitation. Requires OWNER or ADMIN.",
)
def revoke_invitation(
    project_id: str,
    invitation_id: str,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    CollaboratorService.revoke_invitation(
        db=db,
        context=context,
        invitation_id=invitation_id,
    )
    return res.ok(message="Invitation cancelled.", data=None)


# ── 4.6 Update Collaborator Role ─────────────────────────────────────────────

@project_collaborators_router.patch(
    "/{project_id}/members/{user_id}",
    summary="Update Collaborator Role",
    description="Updates role of an existing project member. Requires OWNER (can assign any role) or ADMIN (can toggle between EDITOR and VIEWER). Owner role cannot be modified.",
)
@project_collaborators_router.put(
    "/{project_id}/members/{user_id}",
    summary="Update Collaborator Role",
    description="Updates role of an existing project member. Requires OWNER (can assign any role) or ADMIN (can toggle between EDITOR and VIEWER). Owner role cannot be modified.",
)
def update_member_role(
    project_id: str,
    user_id: str,
    data: CollaboratorRoleUpdateRequest,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    result = CollaboratorService.update_member_role(
        db=db,
        context=context,
        target_user_id=user_id,
        data=data,
    )
    return res.ok(message="Member role updated.", data=result)


# ── 4.7 Remove Collaborator from Project ──────────────────────────────────────

@project_collaborators_router.delete(
    "/{project_id}/members/{user_id}",
    summary="Remove Collaborator from Project",
    description="Removes a collaborator from the project and revokes access immediately. Requires OWNER or ADMIN, or member removing themselves.",
)
def remove_member(
    project_id: str,
    user_id: str,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    CollaboratorService.remove_member(
        db=db,
        context=context,
        target_user_id=user_id,
    )
    return res.ok(message="Member removed from project.", data=None)


# ── 4.5 Accept / Decline Invitation & Details (Invited User) ──────────────────

@invitations_router.get(
    "/{invitation_token}",
    summary="Get Invitation Details",
    description="Inspect invitation details (project name, inviter, assigned role) using secure token.",
)
def get_invitation_details(
    invitation_token: str,
    db: Session = Depends(get_db),
):
    result = CollaboratorService.get_invitation_details(
        db=db,
        invitation_token=invitation_token,
    )
    return res.ok(message="Invitation details retrieved.", data=result)


@invitations_router.post(
    "/{invitation_token}/accept",
    summary="Accept Project Invitation",
    description="Inserts user into project_members and marks invitation ACCEPTED. Must be authenticated with email matching invitee.",
)
def accept_invitation(
    invitation_token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = CollaboratorService.accept_invitation(
        db=db,
        current_user=current_user,
        invitation_token=invitation_token,
    )
    return res.ok(message="Invitation accepted. You are now a project member.", data=result)


@invitations_router.post(
    "/{invitation_token}/decline",
    summary="Decline Project Invitation",
    description="Marks invitation DECLINED. Must be authenticated with email matching invitee.",
)
def decline_invitation(
    invitation_token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    CollaboratorService.decline_invitation(
        db=db,
        current_user=current_user,
        invitation_token=invitation_token,
    )
    return res.ok(message="Invitation declined.", data=None)
