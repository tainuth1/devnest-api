import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.projects.dependencies import (
    ProjectContext,
    require_project_editor_or_above,
    require_project_member,
)
from app.modules.flow.schemas import (
    FlowDiagramCreateRequest,
    FlowDiagramSyncRequest,
    FlowDiagramUpdateRequest,
    FlowPageCreateRequest,
    FlowPageReorderRequest,
    FlowPageUpdateRequest,
)
from app.modules.flow.service import FlowService
from app.shared import responses as res

router = APIRouter()


# ── Flow Diagrams Master Endpoints ─────────────────────────────────────────────

@router.get(
    "/{project_id}/flow-diagrams",
    summary="List Flow Diagrams",
    description="Retrieves flow diagrams within a project workspace.",
)
def list_flow_diagrams(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    q: Optional[str] = Query(default=None),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    result = FlowService.list_diagrams(
        db=db,
        project_id=context.project.id,
        page=page,
        limit=limit,
        q=q,
    )
    return res.ok(message="Flow diagrams retrieved.", data=result)


@router.post(
    "/{project_id}/flow-diagrams",
    status_code=status.HTTP_201_CREATED,
    summary="Create Flow Diagram",
    description="Initializes a new diagram or imports an existing Draw.io mxfile document.",
)
def create_flow_diagram(
    data: FlowDiagramCreateRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.create_diagram(
        db=db,
        project=context.project,
        user=context.user,
        data=data,
    )
    return res.created(
        message="Flow diagram created successfully.",
        data=result.model_dump(mode="json"),
    )


@router.get(
    "/{project_id}/flow-diagrams/{diagram_id}",
    summary="Get Flow Diagram Details",
    description="Hydrates all diagram pages and outputs valid <mxfile> XML for the Draw.io embed iframe.",
)
def get_flow_diagram(
    diagram_id: uuid.UUID,
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    result = FlowService.get_diagram(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
    )
    return res.ok(message="Diagram retrieved.", data=result.model_dump(mode="json"))


@router.patch(
    "/{project_id}/flow-diagrams/{diagram_id}",
    summary="Update Flow Diagram Metadata",
    description="Updates diagram title or technical description.",
)
def update_flow_diagram(
    diagram_id: uuid.UUID,
    data: FlowDiagramUpdateRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.update_diagram_meta(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
        data=data,
    )
    return res.ok(
        message="Diagram updated successfully.",
        data=result.model_dump(mode="json"),
    )


@router.delete(
    "/{project_id}/flow-diagrams/{diagram_id}",
    summary="Delete Flow Diagram",
    description="Permanently deletes the diagram and all contained pages.",
)
def delete_flow_diagram(
    diagram_id: uuid.UUID,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    FlowService.delete_diagram(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
    )
    return res.ok(message="Diagram deleted successfully.")


# ── Collaborative Locking & Auto-Save Sync ─────────────────────────────────────

@router.post(
    "/{project_id}/flow-diagrams/{diagram_id}/lock",
    summary="Acquire Canvas Edit Lock",
    description="Acquires exclusive editing lock for collaborator session.",
)
def acquire_lock(
    diagram_id: uuid.UUID,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.acquire_lock(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
    )
    return res.ok(message="Canvas lock acquired.", data=result)


@router.post(
    "/{project_id}/flow-diagrams/{diagram_id}/unlock",
    summary="Release Canvas Edit Lock",
    description="Releases active editing lock so other collaborators can edit.",
)
def release_lock(
    diagram_id: uuid.UUID,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    is_admin = context.is_admin or context.is_owner
    result = FlowService.release_lock(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
        can_force_unlock=is_admin,
    )
    return res.ok(message="Canvas lock released.", data=result)


@router.put(
    "/{project_id}/flow-diagrams/{diagram_id}/sync",
    summary="Auto-Save & Sync Canvas State",
    description="Debounced auto-save directly accepting Draw.io embed postMessage XML payload with version check.",
)
def sync_diagram(
    diagram_id: uuid.UUID,
    data: FlowDiagramSyncRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.sync_diagram(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
        data=data,
    )
    return res.ok(
        message="Diagram auto-saved successfully.",
        data=result.model_dump(mode="json"),
    )


# ── Flow Canvas Pages Management ───────────────────────────────────────────────

@router.post(
    "/{project_id}/flow-diagrams/{diagram_id}/pages",
    status_code=status.HTTP_201_CREATED,
    summary="Add Canvas Page",
    description="Adds a new tab/page to the diagram.",
)
def add_page(
    diagram_id: uuid.UUID,
    data: FlowPageCreateRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.add_page(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
        data=data,
    )
    return res.created(
        message="Page added successfully.",
        data=result.model_dump(mode="json"),
    )


@router.patch(
    "/{project_id}/flow-diagrams/{diagram_id}/pages/{page_id}",
    summary="Update Canvas Page",
    description="Updates page name, background color, dimensions, or graph model.",
)
def update_page(
    diagram_id: uuid.UUID,
    page_id: uuid.UUID,
    data: FlowPageUpdateRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.update_page(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        page_id=page_id,
        user=context.user,
        data=data,
    )
    return res.ok(
        message="Page updated successfully.",
        data=result.model_dump(mode="json"),
    )


@router.delete(
    "/{project_id}/flow-diagrams/{diagram_id}/pages/{page_id}",
    summary="Delete Canvas Page",
    description="Removes a page tab from the diagram (must keep at least 1 page).",
)
def delete_page(
    diagram_id: uuid.UUID,
    page_id: uuid.UUID,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    FlowService.delete_page(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        page_id=page_id,
        user=context.user,
    )
    return res.ok(message="Page deleted successfully.")


@router.post(
    "/{project_id}/flow-diagrams/{diagram_id}/pages/reorder",
    summary="Reorder Canvas Pages",
    description="Reorders tab display positions in the Draw.io UI.",
)
def reorder_pages(
    diagram_id: uuid.UUID,
    data: FlowPageReorderRequest,
    context: ProjectContext = Depends(require_project_editor_or_above),
    db: Session = Depends(get_db),
):
    result = FlowService.reorder_pages(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        user=context.user,
        data=data,
    )
    return res.ok(
        message="Pages reordered successfully.",
        data=[p.model_dump(mode="json") for p in result],
    )


# ── Export Endpoint ────────────────────────────────────────────────────────────

@router.get(
    "/{project_id}/flow-diagrams/{diagram_id}/export",
    summary="Export Flow Diagram",
    description="Exports diagram as native Draw.io XML (.drawio), SVG, or JSON file stream.",
)
def export_flow_diagram(
    diagram_id: uuid.UUID,
    format: str = Query(default="drawio", description="Export format: drawio, xml, svg, json"),
    page_id: Optional[str] = Query(default=None, description="Optional page ID for single page export"),
    context: ProjectContext = Depends(require_project_member),
    db: Session = Depends(get_db),
):
    content, media_type, filename = FlowService.export_diagram(
        db=db,
        project_id=context.project.id,
        diagram_id=diagram_id,
        format_type=format,
        page_id=page_id,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
