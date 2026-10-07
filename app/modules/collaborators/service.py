import hashlib
import logging
import secrets
import uuid
from datetime import timedelta
from typing import Any, List
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.core.email import send_project_invitation_email
from app.core.enums import (
    InvitationStatus,
    NotificationActionStatus,
    NotificationCategory,
    NotificationType,
    ProjectRole,
)
from app.modules.auth.models import User
from app.modules.collaborators.models import ProjectInvitation
from app.modules.collaborators.schemas import (
    CollaboratorInviteRequest,
    CollaboratorRoleUpdateRequest,
)
from app.modules.notifications.service import NotificationService
from app.modules.projects.dependencies import ProjectContext
from app.modules.projects.models import Project, ProjectMember

logger = logging.getLogger("app.collaborators.service")



class CollaboratorService:
    @staticmethod
    def _parse_uuid(val: str, field_name: str = "ID") -> uuid.UUID:
        try:
            return uuid.UUID(str(val))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name} format.",
            )

    @classmethod
    def list_project_members(cls, db: Session, context: ProjectContext) -> List[dict[str, Any]]:
        """
        List all active members and their roles for the project (Rule 4.1).
        Accessible by any verified project member (OWNER, ADMIN, EDITOR, VIEWER).
        """
        members = (
            db.query(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .filter(ProjectMember.project_id == context.project.id)
            .order_by(ProjectMember.joined_at.asc())
            .all()
        )

        return [
            {
                "id": str(pm.id),
                "user_id": str(pm.user_id),
                "email": u.email,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "avatar_url": u.avatar_url,
                "role": pm.role,
                "joined_at": pm.joined_at.isoformat() if pm.joined_at else None,
                "is_you": (pm.user_id == context.user.id),
            }
            for pm, u in members
        ]

    @classmethod
    async def invite_collaborator(
        cls,
        db: Session,
        context: ProjectContext,
        data: CollaboratorInviteRequest,
    ) -> dict[str, Any]:
        """
        Generates a secure invitation token in project_invitations and dispatches
        an invitation email with a 7-day expiration deadline (Rule 4.2).
        Requires OWNER or ADMIN role (Admin can only invite EDITOR or VIEWER).
        """
        target_role = data.role.upper()
        target_email = data.email.strip().lower()

        # RBAC Check: Admins can only invite EDITOR or VIEWER
        if context.member.role == ProjectRole.ADMIN.value:
            if target_role not in (ProjectRole.EDITOR.value, ProjectRole.VIEWER.value):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admins can only invite collaborators with EDITOR or VIEWER role.",
                )

        # Check if the invitee is already an active member of this project
        existing_user = db.query(User).filter(func.lower(User.email) == target_email).first()
        if existing_user:
            existing_member = (
                db.query(ProjectMember)
                .filter(
                    ProjectMember.project_id == context.project.id,
                    ProjectMember.user_id == existing_user.id,
                )
                .first()
            )
            if existing_member:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User is already a member of this project.",
                )

        # Check if an active unexpired pending invitation already exists for this email
        now = tz.now()
        existing_invite = (
            db.query(ProjectInvitation)
            .filter(
                ProjectInvitation.project_id == context.project.id,
                func.lower(ProjectInvitation.invitee_email) == target_email,
                ProjectInvitation.status == InvitationStatus.PENDING.value,
                ProjectInvitation.expires_at > now,
            )
            .first()
        )
        if existing_invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An active invitation has already been dispatched to {target_email}.",
            )

        # Generate secure random token and SHA-256 hash
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = now + timedelta(days=7)

        # Persist invitation record
        invitation = ProjectInvitation(
            project_id=context.project.id,
            inviter_user_id=context.user.id,
            invitee_email=target_email,
            role=target_role,
            invitation_token_hash=token_hash,
            status=InvitationStatus.PENDING.value,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        # Dispatch invitation email
        inviter_name = (
            f"{context.user.first_name or ''} {context.user.last_name or ''}".strip()
            if (context.user.first_name or context.user.last_name)
            else (context.user.username or context.user.email)
        )

        try:
            await send_project_invitation_email(
                to_email=target_email,
                project_name=context.project.name,
                inviter_name=inviter_name,
                role=target_role,
                invitation_token=raw_token,
            )
        except Exception as exc:
            logger.error("Failed to dispatch invitation email to %s: %s", target_email, exc)
            db.delete(invitation)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send invitation email. Please verify email configuration.",
            )

        # Audit log commit
        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_INVITED,
            status=AuditStatus.SUCCESS,
            user_id=context.user.id,
            details={
                "project_id": str(context.project.id),
                "project_code": context.project.project_code,
                "invitee_email": target_email,
                "role": target_role,
                "invitation_id": str(invitation.id),
            },
            db=db,
        )

        # In-App Notification (Rule 3.4.1: If the invited user exists, they receive an in-app notification)
        invited_user = db.query(User).filter(func.lower(User.email) == target_email.lower()).first()
        if invited_user:
            try:
                NotificationService.send_to_user(
                    db=db,
                    user_id=invited_user.id,
                    actor_id=context.user.id,
                    project_id=context.project.id,
                    type=NotificationType.PROJECT_INVITATION.value,
                    category=NotificationCategory.COLLABORATION.value,
                    title=f"Invitation to join {context.project.name}",
                    message=f"{inviter_name} invited you to collaborate as {target_role}.",
                    link_url=f"/workspace/projects/{context.project.project_code}/team",
                    data={
                        "invitation_id": str(invitation.id),
                        "invitation_token": raw_token,
                        "role": target_role,
                        "project_code": context.project.project_code,
                        "project_name": context.project.name,
                    },
                )
            except Exception as e:
                logger.warning("Failed to dispatch in-app notification for invite: %s", e)

        return {
            "invitation_id": str(invitation.id),
            "invitee_email": invitation.invitee_email,
            "role": invitation.role,
            "expires_at": invitation.expires_at.isoformat(),
            "status": invitation.status,
        }

    @classmethod
    def list_pending_invitations(cls, db: Session, context: ProjectContext) -> List[dict[str, Any]]:
        """
        List all pending, unaccepted invitation records for a project (Rule 4.3).
        Requires OWNER or ADMIN role. Automatically excludes expired invitations.
        """
        now = tz.now()
        invitations = (
            db.query(ProjectInvitation)
            .filter(
                ProjectInvitation.project_id == context.project.id,
                ProjectInvitation.status == InvitationStatus.PENDING.value,
                ProjectInvitation.expires_at > now,
            )
            .order_by(ProjectInvitation.created_at.desc())
            .all()
        )

        result = []
        for inv in invitations:
            inviter = inv.inviter
            inviter_dict = None
            if inviter:
                inviter_dict = {
                    "id": str(inviter.id),
                    "email": inviter.email,
                    "username": inviter.username,
                    "first_name": inviter.first_name,
                    "last_name": inviter.last_name,
                }
            result.append({
                "id": str(inv.id),
                "project_id": str(inv.project_id),
                "inviter_user_id": str(inv.inviter_user_id),
                "invitee_email": inv.invitee_email,
                "email": inv.invitee_email,
                "role": inv.role,
                "status": inv.status,
                "expires_at": inv.expires_at.isoformat(),
                "created_at": inv.created_at.isoformat(),
                "inviter": inviter_dict,
            })
        return result

    @classmethod
    def revoke_invitation(cls, db: Session, context: ProjectContext, invitation_id: str) -> None:
        """
        Revoke / Cancel an invitation (Rule 4.4).
        Requires OWNER or ADMIN role.
        """
        inv_uuid = cls._parse_uuid(invitation_id, "invitation ID")
        invitation = (
            db.query(ProjectInvitation)
            .filter(
                ProjectInvitation.id == inv_uuid,
                ProjectInvitation.project_id == context.project.id,
            )
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found.",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel invitation with status '{invitation.status}'.",
            )

        if context.member.role == ProjectRole.ADMIN.value and invitation.role not in (
            ProjectRole.EDITOR.value,
            ProjectRole.VIEWER.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrators can only cancel invitations with EDITOR or VIEWER role.",
            )

        invitation.status = InvitationStatus.REVOKED.value
        db.commit()

        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_INVITATION_REVOKED,
            status=AuditStatus.SUCCESS,
            user_id=context.user.id,
            details={
                "project_id": str(context.project.id),
                "invitation_id": str(invitation.id),
                "invitee_email": invitation.invitee_email,
            },
            db=db,
        )

    @classmethod
    def get_invitation_details(cls, db: Session, invitation_token: str) -> dict[str, Any]:
        """
        Inspect invitation metadata before accepting or declining.
        """
        token_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
        invitation = (
            db.query(ProjectInvitation)
            .filter(ProjectInvitation.invitation_token_hash == token_hash)
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found or invalid token.",
            )

        now = tz.now()
        if tz.ensure_tz_aware(invitation.expires_at) < now and invitation.status == InvitationStatus.PENDING.value:
            invitation.status = InvitationStatus.EXPIRED.value
            db.commit()

        project = invitation.project
        inviter = invitation.inviter
        inviter_name = (
            f"{inviter.first_name or ''} {inviter.last_name or ''}".strip()
            if inviter and (inviter.first_name or inviter.last_name)
            else (inviter.username or inviter.email if inviter else "DevNest User")
        )

        return {
            "invitation_id": str(invitation.id),
            "project_id": str(invitation.project_id),
            "project_name": project.name if project else "Unknown Project",
            "project_code": project.project_code if project else "",
            "inviter_name": inviter_name,
            "invitee_email": invitation.invitee_email,
            "role": invitation.role,
            "expires_at": invitation.expires_at.isoformat(),
            "status": invitation.status,
        }

    @classmethod
    def accept_invitation(
        cls,
        db: Session,
        current_user: User,
        invitation_token: str,
    ) -> dict[str, Any]:
        """
        Accept an invitation (Rule 4.5).
        Access: Authenticated user whose email strictly matches invitee_email.
        Inserts user into project_members and marks invitation ACCEPTED.
        """
        token_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
        invitation = (
            db.query(ProjectInvitation)
            .filter(ProjectInvitation.invitation_token_hash == token_hash)
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found or invalid token.",
            )

        now = tz.now()
        if tz.ensure_tz_aware(invitation.expires_at) < now:
            if invitation.status == InvitationStatus.PENDING.value:
                invitation.status = InvitationStatus.EXPIRED.value
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has expired.",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation has already been {invitation.status.lower()}.",
            )

        # Enforce email identity match
        if current_user.email.strip().lower() != invitation.invitee_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation was dispatched to another email address. Please log in with the invited account.",
            )

        project = db.query(Project).filter(Project.id == invitation.project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or has been deleted.",
            )

        # Check existing membership
        existing_member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == current_user.id,
            )
            .first()
        )
        if existing_member:
            invitation.status = InvitationStatus.ACCEPTED.value
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of this project.",
            )

        # Calculate next personalized order index
        max_order = (
            db.query(func.max(ProjectMember.order_index))
            .filter(ProjectMember.user_id == current_user.id)
            .scalar()
        )
        new_order = (max_order + 1) if max_order is not None else 0

        new_member = ProjectMember(
            project_id=project.id,
            user_id=current_user.id,
            role=invitation.role,
            order_index=new_order,
            is_pinned=False,
            invited_by=invitation.inviter_user_id,
            joined_at=now,
            updated_at=now,
        )
        db.add(new_member)
        invitation.status = InvitationStatus.ACCEPTED.value
        db.commit()
        db.refresh(new_member)

        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_INVITATION_ACCEPTED,
            status=AuditStatus.SUCCESS,
            user_id=current_user.id,
            details={
                "project_id": str(project.id),
                "project_code": project.project_code,
                "role": invitation.role,
                "invitation_id": str(invitation.id),
            },
            db=db,
        )

        # Notify the inviter that their invitation was accepted
        if invitation.inviter_user_id:
            try:
                user_display = (
                    f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()
                    if (current_user.first_name or current_user.last_name)
                    else (current_user.username or current_user.email)
                )
                NotificationService.send_to_user(
                    db=db,
                    user_id=invitation.inviter_user_id,
                    actor_id=current_user.id,
                    project_id=project.id,
                    type=NotificationType.PROJECT_INVITATION_ACCEPTED.value,
                    category=NotificationCategory.COLLABORATION.value,
                    title=f"Invitation accepted for {project.name}",
                    message=f"{user_display} accepted your invitation to join as {invitation.role}.",
                    link_url=f"/workspace/projects/{project.project_code}/team",
                    data={
                        "project_code": project.project_code,
                        "project_name": project.name,
                        "role": invitation.role,
                        "member_user_id": str(current_user.id),
                    },
                )
            except Exception as e:
                logger.warning("Failed to notify inviter of acceptance: %s", e)

        return {
            "project_id": str(project.id),
            "project_code": project.project_code,
            "project_name": project.name,
            "role": invitation.role,
        }

    @classmethod
    def decline_invitation(
        cls,
        db: Session,
        current_user: User,
        invitation_token: str,
    ) -> None:
        """
        Decline an invitation (Rule 4.5).
        Access: Authenticated user matching invitee email.
        Marks invitation DECLINED.
        """
        token_hash = hashlib.sha256(invitation_token.encode("utf-8")).hexdigest()
        invitation = (
            db.query(ProjectInvitation)
            .filter(ProjectInvitation.invitation_token_hash == token_hash)
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found or invalid token.",
            )

        now = tz.now()
        if tz.ensure_tz_aware(invitation.expires_at) < now:
            if invitation.status == InvitationStatus.PENDING.value:
                invitation.status = InvitationStatus.EXPIRED.value
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This invitation has expired.",
            )

        if invitation.status != InvitationStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invitation has already been {invitation.status.lower()}.",
            )

        if current_user.email.strip().lower() != invitation.invitee_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This invitation was dispatched to another email address.",
            )

        invitation.status = InvitationStatus.DECLINED.value
        db.commit()

        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_INVITATION_DECLINED,
            status=AuditStatus.SUCCESS,
            user_id=current_user.id,
            details={
                "project_id": str(invitation.project_id),
                "invitation_id": str(invitation.id),
            },
            db=db,
        )

        if invitation.inviter_user_id:
            try:
                user_display = (
                    f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()
                    if (current_user.first_name or current_user.last_name)
                    else (current_user.username or current_user.email)
                )
                project = invitation.project
                project_name = project.name if project else "the project"
                project_code = project.project_code if project else ""
                NotificationService.send_to_user(
                    db=db,
                    user_id=invitation.inviter_user_id,
                    actor_id=current_user.id,
                    project_id=invitation.project_id,
                    type=NotificationType.PROJECT_INVITATION_DECLINED.value,
                    category=NotificationCategory.COLLABORATION.value,
                    title=f"Invitation declined for {project_name}",
                    message=f"{user_display} declined the invitation to join {project_name}.",
                    link_url=f"/workspace/projects/{project_code}/team" if project_code else None,
                    data={
                        "project_code": project_code,
                        "project_name": project_name,
                    },
                )
            except Exception as e:
                logger.warning("Failed to notify inviter of decline: %s", e)


    @classmethod
    def update_member_role(
        cls,
        db: Session,
        context: ProjectContext,
        target_user_id: str,
        data: CollaboratorRoleUpdateRequest,
    ) -> dict[str, Any]:
        """
        Update collaborator role (Rule 4.6).
        Access: OWNER (can change any role) or ADMIN (can only toggle between EDITOR and VIEWER).
        Owner role cannot be modified via this endpoint (returns 403).
        """
        target_uuid = cls._parse_uuid(target_user_id, "user ID")
        target_role = data.role.upper()

        if target_role == ProjectRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify Owner role via this endpoint. Project ownership must be transferred via the ownership transfer protocol.",
            )

        target_member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == context.project.id,
                ProjectMember.user_id == target_uuid,
            )
            .first()
        )
        if not target_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this project.",
            )

        if target_member.role == ProjectRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify Owner role via this endpoint.",
            )

        # RBAC Check: ADMIN role constraints
        if context.member.role == ProjectRole.ADMIN.value:
            if target_member.role == ProjectRole.ADMIN.value:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrators cannot modify roles of other administrators.",
                )
            if target_role not in (ProjectRole.EDITOR.value, ProjectRole.VIEWER.value):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Administrators can only toggle roles between EDITOR and VIEWER.",
                )

        # Prevent owner from demoting themselves through this endpoint
        if context.user.id == target_uuid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify your own role via this endpoint.",
            )

        old_role = target_member.role
        target_member.role = target_role
        target_member.updated_at = tz.now()
        db.commit()
        db.refresh(target_member)

        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_ROLE_UPDATED,
            status=AuditStatus.SUCCESS,
            user_id=context.user.id,
            details={
                "project_id": str(context.project.id),
                "target_user_id": str(target_uuid),
                "old_role": old_role,
                "new_role": target_role,
            },
            db=db,
        )

        # Notify the affected member of the role update
        try:
            NotificationService.send_to_user(
                db=db,
                user_id=target_member.user_id,
                actor_id=context.user.id,
                project_id=context.project.id,
                type=NotificationType.MEMBER_ROLE_CHANGED.value,
                category=NotificationCategory.COLLABORATION.value,
                title=f"Role updated in {context.project.name}",
                message=f"Your role in {context.project.name} has been updated to {target_role}.",
                link_url=f"/workspace/projects/{context.project.project_code}/team",
                data={
                    "project_code": context.project.project_code,
                    "old_role": old_role,
                    "new_role": target_role,
                },
            )
        except Exception as e:
            logger.warning("Failed to notify member of role change: %s", e)

        user = db.query(User).filter(User.id == target_uuid).first()
        return {
            "id": str(target_member.id),
            "user_id": str(target_member.user_id),
            "project_id": str(target_member.project_id),
            "email": user.email if user else "",
            "username": user.username if user else None,
            "first_name": user.first_name if user else None,
            "last_name": user.last_name if user else None,
            "avatar_url": user.avatar_url if user else None,
            "role": target_member.role,
            "joined_at": target_member.joined_at.isoformat() if target_member.joined_at else None,
            "updated_at": target_member.updated_at.isoformat() if target_member.updated_at else None,
            "is_you": (target_member.user_id == context.user.id),
        }

    @classmethod
    def remove_member(
        cls,
        db: Session,
        context: ProjectContext,
        target_user_id: str,
    ) -> None:
        """
        Remove collaborator from project (Rule 4.7).
        Access: OWNER or ADMIN.
        Member can also remove themselves to leave project.
        """
        target_uuid = cls._parse_uuid(target_user_id, "user ID")

        target_member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == context.project.id,
                ProjectMember.user_id == target_uuid,
            )
            .first()
        )
        if not target_member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found in this project.",
            )

        is_self_removal = context.user.id == target_uuid

        if target_member.role == ProjectRole.OWNER.value:
            if is_self_removal:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Project owner cannot leave the project. Please transfer ownership or delete the project.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove project owner from project.",
            )

        # RBAC Check
        if not is_self_removal:
            if context.member.role in (ProjectRole.EDITOR.value, ProjectRole.VIEWER.value):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to remove members from this project.",
                )
            if context.member.role == ProjectRole.ADMIN.value:
                if target_member.role not in (ProjectRole.EDITOR.value, ProjectRole.VIEWER.value):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Administrators can only remove members with EDITOR or VIEWER role.",
                    )

        db.delete(target_member)
        db.commit()

        audit_logger.log_event(
            event_type=AuditEventType.COLLABORATOR_REMOVED,
            status=AuditStatus.SUCCESS,
            user_id=context.user.id,
            details={
                "project_id": str(context.project.id),
                "removed_user_id": str(target_uuid),
                "is_self_removal": is_self_removal,
            },
            db=db,
        )

        # Notify the removed member if removed by another user
        if not is_self_removal:
            try:
                NotificationService.send_to_user(
                    db=db,
                    user_id=target_uuid,
                    actor_id=context.user.id,
                    project_id=context.project.id,
                    type=NotificationType.MEMBER_REMOVED.value,
                    category=NotificationCategory.COLLABORATION.value,
                    title=f"Removed from {context.project.name}",
                    message=f"You have been removed from {context.project.name}.",
                    link_url="/workspace/projects",
                    data={
                        "project_code": context.project.project_code,
                        "project_name": context.project.name,
                    },
                )
            except Exception as e:
                logger.warning("Failed to notify member of removal: %s", e)

