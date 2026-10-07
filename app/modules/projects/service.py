import logging
import re
import secrets
import string
import uuid
from typing import Any, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core import timezone as tz
from app.core.audit import audit_logger, AuditEventType, AuditStatus
from app.core.enums import ProjectRole, ProjectStatus
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.schemas import (
    ProjectBatchReorderRequest,
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectOrderUpdateRequest,
    ProjectStatusUpdateRequest,
    ProjectUpdateRequest,
)

logger = logging.getLogger("app.projects.service")

DEFAULT_PROJECT_SETTINGS: dict[str, Any] = {
    "default_sql_dialect": "postgresql",
    "auto_save_interval_ms": 2000,
}


class ProjectService:
    @staticmethod
    def generate_project_code(db: Session) -> str:
        """
        Generate a unique 20-character random lowercase alphanumeric string (rule BR-PROJ-04).
        Example: gis3qngfcvp2retskpw1
        """
        alphabet = string.ascii_lowercase + string.digits
        for _ in range(10):
            code = "".join(secrets.choice(alphabet) for _ in range(20))
            existing = db.query(Project.id).filter(Project.project_code == code).first()
            if not existing:
                return code
        # Fallback if extremely improbable collision happens
        return secrets.token_hex(10)[:20]

    @staticmethod
    def generate_slug(db: Session, name: str, exclude_project_id: Optional[uuid.UUID] = None) -> str:
        """
        Generate a clean URL-safe slug from project name.
        Ensures uniqueness across all projects by appending short hex suffixes if needed.
        """
        cleaned = name.lower()
        cleaned = re.sub(r"[^\w\s-]", "", cleaned)
        slug = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
        if not slug:
            slug = "project"

        base_slug = slug[:100]
        unique_slug = base_slug
        counter = 1

        while True:
            query = db.query(Project.id).filter(Project.slug == unique_slug)
            if exclude_project_id:
                query = query.filter(Project.id != exclude_project_id)
            if not query.first():
                return unique_slug

            # Append unique suffix
            suffix = f"-{secrets.token_hex(2)}" if counter > 3 else f"-{counter}"
            unique_slug = f"{base_slug[:110]}{suffix}"
            counter += 1

    @classmethod
    def get_project_by_id_or_code(cls, db: Session, project_id_or_code: str) -> Project | None:
        """
        Resolves a Project by its UUID string or 20-character unique project_code.
        """
        # 1. Try UUID parse
        try:
            val_uuid = uuid.UUID(project_id_or_code)
            project = db.query(Project).filter(Project.id == val_uuid).first()
            if project:
                return project
        except (ValueError, TypeError, AttributeError):
            pass

        # 2. Try project_code lookup
        return db.query(Project).filter(Project.project_code == project_id_or_code).first()

    @classmethod
    def get_project_and_member(
        cls,
        db: Session,
        project_id_or_code: str,
        user: User,
    ) -> tuple[Project, ProjectMember]:
        """
        Retrieves project and caller's ProjectMember membership.
        Raises 404 if project does not exist or caller is not an active member (prevents enumeration).
        """
        project = cls.get_project_by_id_or_code(db, project_id_or_code)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
            )
            .first()
        )

        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        return project, member

    @classmethod
    def list_user_projects(
        cls,
        db: Session,
        user: User,
        page: int = 1,
        limit: int = 20,
        status_filter: str = "all",
        role_filter: str = "all",
        sort_by: str = "order",
        order_dir: str = "asc",
        q: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Retrieves all projects where user is an active member with personalized dashboard preferences (order_index, is_pinned).
        """
        query = (
            db.query(Project, ProjectMember)
            .join(ProjectMember, Project.id == ProjectMember.project_id)
            .filter(ProjectMember.user_id == user.id)
        )

        # Status filter
        if status_filter and status_filter.lower() != "all":
            query = query.filter(Project.status == status_filter)

        # Role filter
        if role_filter and role_filter.upper() != "ALL":
            if role_filter.upper() == "OWNER":
                query = query.filter(ProjectMember.role == ProjectRole.OWNER.value)
            elif role_filter.upper() == "MEMBER":
                query = query.filter(ProjectMember.role != ProjectRole.OWNER.value)

        # Search filter
        if q and q.strip():
            search_term = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    Project.name.ilike(search_term),
                    Project.description.ilike(search_term),
                    Project.project_code.ilike(search_term),
                )
            )

        # Total items count
        total_items = query.count()
        total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1

        # Sorting
        is_asc = order_dir.lower() == "asc"
        if sort_by == "order":
            # Pinned items always appear first, followed by order_index
            if is_asc:
                query = query.order_by(
                    ProjectMember.is_pinned.desc(),
                    ProjectMember.order_index.asc(),
                    Project.created_at.desc(),
                )
            else:
                query = query.order_by(
                    ProjectMember.is_pinned.desc(),
                    ProjectMember.order_index.desc(),
                    Project.created_at.desc(),
                )
        elif sort_by == "name":
            order_col = Project.name.asc() if is_asc else Project.name.desc()
            query = query.order_by(order_col)
        elif sort_by == "updated_at":
            order_col = Project.updated_at.asc() if is_asc else Project.updated_at.desc()
            query = query.order_by(order_col)
        elif sort_by == "created_at":
            order_col = Project.created_at.asc() if is_asc else Project.created_at.desc()
            query = query.order_by(order_col)
        else:
            query = query.order_by(ProjectMember.order_index.asc())

        # Pagination window
        offset = (page - 1) * limit
        results = query.offset(offset).limit(limit).all()

        # Gather members count for each project
        project_ids = [p.id for p, _ in results]
        members_count_map: dict[uuid.UUID, int] = {}
        if project_ids:
            counts = (
                db.query(ProjectMember.project_id, func.count(ProjectMember.id))
                .filter(ProjectMember.project_id.in_(project_ids))
                .group_by(ProjectMember.project_id)
                .all()
            )
            members_count_map = {p_id: count for p_id, count in counts}

        items = []
        for project, member in results:
            items.append({
                "id": str(project.id),
                "project_code": project.project_code,
                "name": project.name,
                "slug": project.slug,
                "description": project.description,
                "status": project.status,
                "order_index": member.order_index,
                "is_pinned": member.is_pinned,
                "color": project.color,
                "icon": project.icon,
                "my_role": member.role,
                "members_count": members_count_map.get(project.id, 1),
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat() if project.updated_at else project.created_at.isoformat(),
            })

        return {
            "items": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    @classmethod
    def create_project(
        cls,
        db: Session,
        user: User,
        data: ProjectCreateRequest,
    ) -> dict[str, Any]:
        """
        Initializes a new project workspace, generates unique project_code and slug,
        and assigns current user as OWNER with caller's personalized order_index (rule BR-PROJ-04).
        """
        project_code = cls.generate_project_code(db)
        slug = cls.generate_slug(db, data.name)

        # Merge settings with defaults
        project_settings = dict(DEFAULT_PROJECT_SETTINGS)
        if data.settings:
            project_settings.update(data.settings)

        # Calculate caller's personalized order_index
        current_max = (
            db.query(func.max(ProjectMember.order_index))
            .filter(ProjectMember.user_id == user.id)
            .scalar()
        )
        order_index = (current_max + 1) if current_max is not None else 0

        project = Project(
            project_code=project_code,
            name=data.name,
            slug=slug,
            description=data.description,
            status=ProjectStatus.NOT_STARTED.value,
            owner_id=user.id,
            color="#6366F1",
            icon="folder",
            settings=project_settings,
            created_at=tz.now(),
            updated_at=tz.now(),
        )
        db.add(project)
        db.flush()

        # Add current user as OWNER
        member = ProjectMember(
            project_id=project.id,
            user_id=user.id,
            role=ProjectRole.OWNER.value,
            order_index=order_index,
            is_pinned=False,
            joined_at=tz.now(),
            updated_at=tz.now(),
        )
        db.add(member)
        db.commit()
        db.refresh(project)
        db.refresh(member)

        # Audit log creation
        audit_logger.log_event(
            event_type=AuditEventType.PROJECT_CREATED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={
                "project_id": str(project.id),
                "project_code": project.project_code,
                "name": project.name,
                "slug": project.slug,
            },
            db=db,
        )

        return {
            "id": str(project.id),
            "project_code": project.project_code,
            "name": project.name,
            "slug": project.slug,
            "description": project.description,
            "status": project.status,
            "order_index": member.order_index,
            "is_pinned": member.is_pinned,
            "color": project.color,
            "icon": project.icon,
            "owner_id": str(project.owner_id),
            "my_role": member.role,
            "settings": project.settings,
            "created_at": project.created_at.isoformat(),
        }

    @classmethod
    def get_project_summary(
        cls,
        db: Session,
        user: User,
        project_id_or_code: str,
    ) -> dict[str, Any]:
        """
        Returns structured project overview data required by the overview page.
        Joins project members with users to build profile stack, initials, and roles.
        Omits unused properties (rule: do not return data that is not used).
        """
        project, _ = cls.get_project_and_member(db, project_id_or_code, user)

        # 1. Join project_members with users to retrieve active members with names, roles, initials
        member_records = (
            db.query(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .filter(ProjectMember.project_id == project.id)
            .order_by(ProjectMember.order_index.asc(), ProjectMember.joined_at.asc())
            .all()
        )

        members_list: list[dict[str, Any]] = []
        for pm, u in member_records:
            if u.first_name and u.last_name:
                display_name = f"{u.first_name} {u.last_name}".strip()
            elif u.first_name:
                display_name = u.first_name.strip()
            elif u.username:
                display_name = u.username
            else:
                display_name = u.email.split("@")[0]

            parts = display_name.split()
            if len(parts) >= 2:
                initials = f"{parts[0][0]}{parts[1][0]}".upper()
            elif len(display_name) >= 2:
                initials = display_name[:2].upper()
            else:
                initials = display_name[:1].upper() or "U"

            role_label = pm.role.capitalize() if pm.role else "Member"

            members_list.append({
                "id": str(u.id),
                "name": display_name,
                "role": role_label,
                "initials": initials,
                "avatar_url": u.avatar_url,
            })

        # 2. Extract dialect from settings with default
        settings = project.settings or {}
        raw_dialect = settings.get("default_sql_dialect", "PostgreSQL 16")
        if raw_dialect.lower() == "postgresql":
            dialect = "POSTGRESQL 16"
        else:
            dialect = raw_dialect.upper()

        return {
            "id": str(project.id),
            "project_code": project.project_code,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "color": project.color,
            "icon": project.icon,
            "settings": project.settings or {},
            "dialect": dialect,
            "flows_count": int(settings.get("flows_count", 0)),
            "tables_count": int(settings.get("tables_count", 0)),
            "relations_count": int(settings.get("relations_count", 0)),
            "documents_count": int(settings.get("documents_count", 0)),
            "backup_status": settings.get("backup_status", "Healthy"),
            "backup_size": settings.get("backup_size", None),
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat() if project.updated_at else project.created_at.isoformat(),
            "pending_invites_count": int(settings.get("pending_invites_count", 0)),
            "members": members_list,
        }

    @classmethod
    def update_project(
        cls,
        db: Session,
        user: User,
        project_id_or_code: str,
        data: ProjectUpdateRequest,
    ) -> dict[str, Any]:
        """
        Updates shared project metadata and settings. Requires OWNER or ADMIN role.
        """
        project, member = cls.get_project_and_member(db, project_id_or_code, user)

        # RBAC Check: OWNER or ADMIN only
        if member.role not in (ProjectRole.OWNER.value, ProjectRole.ADMIN.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners and admins can update project details.",
            )

        updated_fields: dict[str, Any] = {}

        if data.name is not None and data.name.strip():
            project.name = data.name.strip()
            updated_fields["name"] = project.name
        if data.description is not None:
            project.description = data.description
            updated_fields["description"] = project.description
        if data.status is not None:
            project.status = data.status
            updated_fields["status"] = project.status
        if data.color is not None:
            project.color = data.color
            updated_fields["color"] = project.color
        if data.icon is not None:
            project.icon = data.icon
            updated_fields["icon"] = project.icon
        if data.settings is not None:
            current_settings = dict(project.settings or {})
            current_settings.update(data.settings)
            project.settings = current_settings
            updated_fields["settings"] = project.settings

        project.updated_at = tz.now()
        db.commit()
        db.refresh(project)

        # Audit log update
        audit_logger.log_event(
            event_type=AuditEventType.PROJECT_UPDATED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={
                "project_id": str(project.id),
                "project_code": project.project_code,
                "updated_fields": list(updated_fields.keys()),
            },
            db=db,
        )

        return cls.get_project_summary(db, user, project.project_code)

    @classmethod
    def update_project_status(
        cls,
        db: Session,
        user: User,
        project_id_or_code: str,
        data: ProjectStatusUpdateRequest,
    ) -> dict[str, Any]:
        """
        Updates project operational lifecycle status (rule BR-PROJ-05).
        Requires OWNER or ADMIN role.
        """
        project, member = cls.get_project_and_member(db, project_id_or_code, user)

        if member.role not in (ProjectRole.OWNER.value, ProjectRole.ADMIN.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners and admins can update lifecycle status.",
            )

        old_status = project.status
        new_status = data.status

        project.status = new_status
        project.updated_at = tz.now()
        db.commit()
        db.refresh(project)

        # Audit log status transition
        audit_logger.log_event(
            event_type=AuditEventType.PROJECT_STATUS_CHANGED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={
                "project_id": str(project.id),
                "project_code": project.project_code,
                "old_status": old_status,
                "new_status": new_status,
            },
            db=db,
        )

        return {
            "id": str(project.id),
            "project_code": project.project_code,
            "status": project.status,
            "updated_at": project.updated_at.isoformat(),
        }

    @classmethod
    def update_project_order(
        cls,
        db: Session,
        user: User,
        project_id_or_code: str,
        data: ProjectOrderUpdateRequest,
    ) -> dict[str, Any]:
        """
        Exclusively updates the calling user's personalized dashboard sort order (rule BR-PROJ-06).
        Does NOT alter any other collaborator's view.
        """
        project, member = cls.get_project_and_member(db, project_id_or_code, user)

        member.order_index = data.order_index
        if data.is_pinned is not None:
            member.is_pinned = data.is_pinned
        member.updated_at = tz.now()
        db.commit()
        db.refresh(member)

        # Audit log personal order change
        audit_logger.log_event(
            event_type=AuditEventType.PROJECT_ORDER_CHANGED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={
                "project_id": str(project.id),
                "order_index": member.order_index,
                "is_pinned": member.is_pinned,
            },
            db=db,
        )

        return {
            "project_id": str(project.id),
            "project_code": project.project_code,
            "user_id": str(user.id),
            "order_index": member.order_index,
            "updated_at": member.updated_at.isoformat(),
        }

    @classmethod
    def reorder_projects_batch(
        cls,
        db: Session,
        user: User,
        data: ProjectBatchReorderRequest,
    ) -> list[dict[str, Any]]:
        """
        Reorders multiple projects on the caller's personal dashboard view (rule BR-PROJ-06).
        """
        updated_items = []
        for item in data.items:
            project = cls.get_project_by_id_or_code(db, item.project_id)
            if not project:
                continue
            member = (
                db.query(ProjectMember)
                .filter(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == user.id,
                )
                .first()
            )
            if not member:
                continue

            member.order_index = item.order_index
            if item.is_pinned is not None:
                member.is_pinned = item.is_pinned
            member.updated_at = tz.now()
            updated_items.append({
                "project_id": str(project.id),
                "project_code": project.project_code,
                "order_index": member.order_index,
            })

        db.commit()
        return updated_items

    @classmethod
    def delete_project(
        cls,
        db: Session,
        user: User,
        project_id_or_code: str,
        data: ProjectDeleteRequest,
    ) -> None:
        """
        Permanently purges a project. Requires OWNER role and confirm_slug match.
        """
        project, member = cls.get_project_and_member(db, project_id_or_code, user)

        # RBAC Check: OWNER only
        if member.role != ProjectRole.OWNER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the project owner can delete this project.",
            )

        # Confirmation slug match
        if data.confirm_slug.strip() != project.slug:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Project slug confirmation mismatch. Expected '{project.slug}'.",
            )

        project_id_str = str(project.id)
        project_code_str = project.project_code
        project_name = project.name

        db.delete(project)
        db.commit()

        # Audit log deletion
        audit_logger.log_event(
            event_type=AuditEventType.PROJECT_DELETED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={
                "project_id": project_id_str,
                "project_code": project_code_str,
                "name": project_name,
            },
            db=db,
        )
