import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.projects.dependencies import (
    ProjectContext,
    require_project_admin_or_owner,
    require_project_member,
    require_project_owner,
)
from app.modules.projects.schemas import (
    ProjectBatchReorderRequest,
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectOrderUpdateRequest,
    ProjectStatusUpdateRequest,
    ProjectUpdateRequest,
)
from app.modules.projects.service import ProjectService
from app.shared import responses as res

logger = logging.getLogger("app.projects.router")

router = APIRouter()


@router.get(
    "",
    summary="List User Projects",
    description="Retrieves all projects where the authenticated user is an active member with personalized dashboard sequence.",
)
def list_projects(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str = Query(default="all", description="Filter by project status (all or specific status)"),
    role: str = Query(default="all", description="Filter by user role in project (all, OWNER, MEMBER)"),
    sort_by: str = Query(default="order", description="Sort field (order, name, updated_at, created_at)"),
    order_dir: str = Query(default="asc", description="Sort direction (asc, desc)"),
    q: Optional[str] = Query(default=None, description="Search term for name, description, or project_code"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ProjectService.list_user_projects(
        db=db,
        user=current_user,
        page=page,
        limit=limit,
        status_filter=status,
        role_filter=role,
        sort_by=sort_by,
        order_dir=order_dir,
        q=q,
    )
    return res.ok(message="Projects retrieved successfully.", data=result)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create New Project",
    description="Initializes a new project workspace, generates unique project_code, and assigns caller as OWNER.",
)
def create_project(
    data: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ProjectService.create_project(
        db=db,
        user=current_user,
        data=data,
    )
    return res.created(message="Project created successfully.", data=result)


@router.put(
    "/reorder",
    summary="Batch Reorder Projects",
    description="Reorders multiple projects on caller's personal dashboard view (rule BR-PROJ-06).",
)
def reorder_projects(
    data: ProjectBatchReorderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = ProjectService.reorder_projects_batch(
        db=db,
        user=current_user,
        data=data,
    )
    return res.ok(message="Projects display order updated successfully.", data=result)


@router.get(
    "/{project_code}",
    summary="Get Project Workspace Summary",
    description="Returns project metadata, caller's effective permissions, artifact counts, and personalized settings by 20-character project_code. Enforced for active members (OWNER, ADMIN, EDITOR, VIEWER).",
)
def get_project(
    project_code: str,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    result = ProjectService.get_project_summary(
        db=db,
        user=context.user,
        project_id_or_code=project_code,
    )
    return res.ok(message="Project details retrieved successfully.", data=result)


@router.patch(
    "/{project_id}",
    summary="Update Project Details & Settings",
    description="Updates shared project metadata and settings. Backend-enforced: requires OWNER or ADMIN role.",
)
def update_project(
    data: ProjectUpdateRequest,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    result = ProjectService.update_project(
        db=db,
        user=context.user,
        project_id_or_code=str(context.project.id),
        data=data,
    )
    return res.ok(message="Project updated successfully.", data=result)


@router.patch(
    "/{project_id}/status",
    summary="Update Project Lifecycle Status",
    description="Updates the project operational lifecycle status. Backend-enforced: requires OWNER or ADMIN role.",
)
def update_project_status(
    data: ProjectStatusUpdateRequest,
    context: ProjectContext = Depends(require_project_admin_or_owner),
    db: Session = Depends(get_db),
):
    result = ProjectService.update_project_status(
        db=db,
        user=context.user,
        project_id_or_code=str(context.project.id),
        data=data,
    )
    return res.ok(message="Project status updated successfully.", data=result)


@router.patch(
    "/{project_id}/order",
    summary="Update Personal Project Display Order",
    description="Exclusively updates the calling user's personalized dashboard sort order. Backend-enforced for active members.",
)
def update_project_order(
    data: ProjectOrderUpdateRequest,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    result = ProjectService.update_project_order(
        db=db,
        user=context.user,
        project_id_or_code=str(context.project.id),
        data=data,
    )
    return res.ok(message="Personal project display order updated successfully.", data=result)


@router.delete(
    "/{project_id}",
    summary="Delete Project",
    description="Permanently purges project and all associated data. Backend-enforced: strictly requires OWNER role and slug match.",
)
def delete_project(
    project_id: str,
    data: Optional[ProjectDeleteRequest] = None,
    confirm_slug: Optional[str] = Query(default=None, description="Confirmation project slug"),
    context: ProjectContext = Depends(require_project_owner),
    db: Session = Depends(get_db),
):
    slug_val = None
    if data and data.confirm_slug:
        slug_val = data.confirm_slug
    elif confirm_slug:
        slug_val = confirm_slug

    if not slug_val:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation slug is required.",
        )

    ProjectService.delete_project(
        db=db,
        user=context.user,
        project_id_or_code=str(context.project.id),
        data=ProjectDeleteRequest(confirm_slug=slug_val),
    )
    return res.ok(message="Project permanently deleted.", data=None)
