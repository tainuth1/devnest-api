import html
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.modules.auth.models import User
from app.modules.flow import drawio_utils
from app.modules.flow.models import FlowDiagram, FlowPage
from app.modules.flow.schemas import (
    FlowDiagramCreateRequest,
    FlowDiagramDetailResponse,
    FlowDiagramSummaryResponse,
    FlowDiagramSyncRequest,
    FlowDiagramSyncResult,
    FlowDiagramUpdateRequest,
    FlowPageCreateRequest,
    FlowPageReorderRequest,
    FlowPageResponse,
    FlowPageUpdateRequest,
    UserMinimalInfo,
)
from app.modules.projects.models import Project

LOCK_TIMEOUT_MINUTES = 15


class FlowService:

    @staticmethod
    def _is_lock_expired(diagram: FlowDiagram) -> bool:
        if not diagram.is_locked or not diagram.locked_at:
            return True
        now = tz.now()
        locked_at = diagram.locked_at
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=now.tzinfo)
        return now - locked_at > timedelta(minutes=LOCK_TIMEOUT_MINUTES)

    @staticmethod
    def _to_user_minimal(user: Optional[User]) -> Optional[UserMinimalInfo]:
        if not user:
            return None
        display_name = (
            user.username
            or f"{user.first_name or ''} {user.last_name or ''}".strip()
            or user.email
        )
        return UserMinimalInfo(id=user.id, name=display_name, email=user.email)

    @classmethod
    def list_diagrams(
        cls,
        db: Session,
        project_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
        q: Optional[str] = None,
    ) -> dict[str, Any]:
        query = db.query(FlowDiagram).filter(FlowDiagram.project_id == project_id)

        if q:
            term = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    FlowDiagram.title.ilike(term),
                    FlowDiagram.description.ilike(term),
                )
            )

        total = query.count()
        diagrams = (
            query.order_by(FlowDiagram.updated_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        items = []
        for d in diagrams:
            # Check expired lock
            if d.is_locked and cls._is_lock_expired(d):
                d.is_locked = False
                d.locked_by_user_id = None
                d.locked_at = None
                db.add(d)

            items.append(
                FlowDiagramSummaryResponse(
                    id=d.id,
                    project_id=d.project_id,
                    title=d.title,
                    description=d.description,
                    thumbnail_url=d.thumbnail_url,
                    pages_count=len(d.pages),
                    is_locked=d.is_locked,
                    locked_by=cls._to_user_minimal(d.locked_by_user) if d.is_locked else None,
                    locked_at=d.locked_at if d.is_locked else None,
                    created_by=d.created_by,
                    updated_by=d.updated_by,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
            )

        db.commit()

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [item.model_dump(mode="json") for item in items],
        }

    @classmethod
    def create_diagram(
        cls,
        db: Session,
        project: Project,
        user: User,
        data: FlowDiagramCreateRequest,
    ) -> FlowDiagramDetailResponse:
        # Parse XML or generate default scaffolding
        if data.xml_content and data.xml_content.strip():
            try:
                pages_meta = drawio_utils.parse_mxfile(data.xml_content)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid Draw.io XML: {e}",
                )
        else:
            pages_meta = drawio_utils.build_default_diagram_pages(title=data.title)

        diagram = FlowDiagram(
            project_id=project.id,
            title=data.title.strip(),
            description=data.description.strip() if data.description else None,
            version=1,
            is_locked=False,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(diagram)
        db.flush()

        created_pages = []
        for idx, pm in enumerate(pages_meta):
            page_record = FlowPage(
                diagram_id=diagram.id,
                drawio_page_id=pm["drawio_page_id"],
                name=pm["name"],
                page_order=idx,
                xml_content=pm["xml_content"],
                compressed_xml=pm.get("compressed_xml"),
                background_color=pm.get("background_color", "#FFFFFF"),
                grid_enabled=pm.get("grid_enabled", True),
                grid_size=pm.get("grid_size", 10),
                page_width=pm.get("page_width", 1050),
                page_height=pm.get("page_height", 1485),
            )
            db.add(page_record)
            created_pages.append(page_record)

        db.commit()
        db.refresh(diagram)

        mxfile_xml = drawio_utils.build_mxfile(
            pages=created_pages,
            modified=diagram.updated_at,
        )

        return FlowDiagramDetailResponse(
            id=diagram.id,
            project_id=diagram.project_id,
            title=diagram.title,
            description=diagram.description,
            thumbnail_url=diagram.thumbnail_url,
            version=diagram.version,
            is_locked=diagram.is_locked,
            locked_by=None,
            locked_at=None,
            xml_content=mxfile_xml,
            pages=[
                FlowPageResponse(
                    id=p.id,
                    diagram_id=p.diagram_id,
                    drawio_page_id=p.drawio_page_id,
                    name=p.name,
                    page_order=p.page_order,
                    xml_content=p.xml_content,
                    compressed_xml=p.compressed_xml,
                    background_color=p.background_color,
                    grid_enabled=p.grid_enabled,
                    grid_size=p.grid_size,
                    page_width=p.page_width,
                    page_height=p.page_height,
                    updated_at=p.updated_at,
                )
                for p in created_pages
            ],
            created_at=diagram.created_at,
            updated_at=diagram.updated_at,
        )

    @classmethod
    def get_diagram(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
    ) -> FlowDiagramDetailResponse:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        # Check expired lock
        if diagram.is_locked and cls._is_lock_expired(diagram):
            diagram.is_locked = False
            diagram.locked_by_user_id = None
            diagram.locked_at = None
            db.commit()
            db.refresh(diagram)

        mxfile_xml = drawio_utils.build_mxfile(
            pages=diagram.pages,
            modified=diagram.updated_at,
        )

        return FlowDiagramDetailResponse(
            id=diagram.id,
            project_id=diagram.project_id,
            title=diagram.title,
            description=diagram.description,
            thumbnail_url=diagram.thumbnail_url,
            version=diagram.version,
            is_locked=diagram.is_locked,
            locked_by=cls._to_user_minimal(diagram.locked_by_user) if diagram.is_locked else None,
            locked_at=diagram.locked_at if diagram.is_locked else None,
            xml_content=mxfile_xml,
            pages=[
                FlowPageResponse(
                    id=p.id,
                    diagram_id=p.diagram_id,
                    drawio_page_id=p.drawio_page_id,
                    name=p.name,
                    page_order=p.page_order,
                    xml_content=p.xml_content,
                    compressed_xml=p.compressed_xml,
                    background_color=p.background_color,
                    grid_enabled=p.grid_enabled,
                    grid_size=p.grid_size,
                    page_width=p.page_width,
                    page_height=p.page_height,
                    updated_at=p.updated_at,
                )
                for p in diagram.pages
            ],
            created_at=diagram.created_at,
            updated_at=diagram.updated_at,
        )

    @classmethod
    def update_diagram_meta(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
        data: FlowDiagramUpdateRequest,
    ) -> FlowDiagramDetailResponse:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        if data.title is not None:
            diagram.title = data.title.strip()
        if data.description is not None:
            diagram.description = data.description.strip() if data.description else None

        diagram.updated_by = user.id
        diagram.updated_at = tz.now()
        db.commit()
        db.refresh(diagram)

        return cls.get_diagram(db, project_id, diagram_id)

    @classmethod
    def acquire_lock(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
    ) -> dict[str, Any]:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        now = tz.now()
        if diagram.is_locked and not cls._is_lock_expired(diagram):
            if diagram.locked_by_user_id != user.id:
                holder_name = (
                    diagram.locked_by_user.username
                    or diagram.locked_by_user.first_name
                    or diagram.locked_by_user.email
                    if diagram.locked_by_user
                    else "Another user"
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Canvas is currently locked by {holder_name}.",
                )
            # Re-affirm own lock
            diagram.locked_at = now
        else:
            diagram.is_locked = True
            diagram.locked_by_user_id = user.id
            diagram.locked_at = now

        db.commit()
        db.refresh(diagram)

        return {
            "diagram_id": diagram.id,
            "is_locked": True,
            "locked_by": cls._to_user_minimal(diagram.locked_by_user),
            "locked_at": diagram.locked_at,
        }

    @classmethod
    def release_lock(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
        can_force_unlock: bool = False,
    ) -> dict[str, Any]:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        if diagram.is_locked:
            if diagram.locked_by_user_id != user.id and not can_force_unlock:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the current lock holder or a project admin can release the canvas lock.",
                )
            diagram.is_locked = False
            diagram.locked_by_user_id = None
            diagram.locked_at = None
            db.commit()

        return {
            "diagram_id": diagram.id,
            "is_locked": False,
        }

    @classmethod
    def sync_diagram(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
        data: FlowDiagramSyncRequest,
    ) -> FlowDiagramSyncResult:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        # Check lock
        if diagram.is_locked and not cls._is_lock_expired(diagram):
            if diagram.locked_by_user_id != user.id:
                holder_name = (
                    diagram.locked_by_user.username
                    or diagram.locked_by_user.first_name
                    or diagram.locked_by_user.email
                    if diagram.locked_by_user
                    else "Another collaborator"
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f"Canvas edit locked by {holder_name}. Sync blocked.",
                )

        # Optimistic concurrency lock
        if diagram.version != data.expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Diagram has been modified by another collaborator (expected version {data.expected_version}, current version {diagram.version}). Please refresh and merge.",
            )

        # Process synchronization payload
        if data.xml_content and data.xml_content.strip():
            try:
                pages_meta = drawio_utils.parse_mxfile(data.xml_content)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid Draw.io XML sync payload: {e}",
                )

            # Map existing pages by drawio_page_id
            existing_by_drawio_id = {p.drawio_page_id: p for p in diagram.pages}
            new_drawio_ids = {pm["drawio_page_id"] for pm in pages_meta}

            # Delete removed pages
            for p in diagram.pages:
                if p.drawio_page_id not in new_drawio_ids:
                    db.delete(p)

            # Update existing or insert new
            for idx, pm in enumerate(pages_meta):
                pid = pm["drawio_page_id"]
                if pid in existing_by_drawio_id:
                    page = existing_by_drawio_id[pid]
                    page.name = pm["name"]
                    page.page_order = idx
                    page.xml_content = pm["xml_content"]
                    page.background_color = pm.get("background_color", page.background_color)
                    page.grid_enabled = pm.get("grid_enabled", page.grid_enabled)
                    page.grid_size = pm.get("grid_size", page.grid_size)
                    page.page_width = pm.get("page_width", page.page_width)
                    page.page_height = pm.get("page_height", page.page_height)
                    page.updated_at = tz.now()
                else:
                    new_page = FlowPage(
                        diagram_id=diagram.id,
                        drawio_page_id=pid,
                        name=pm["name"],
                        page_order=idx,
                        xml_content=pm["xml_content"],
                        compressed_xml=pm.get("compressed_xml"),
                        background_color=pm.get("background_color", "#FFFFFF"),
                        grid_enabled=pm.get("grid_enabled", True),
                        grid_size=pm.get("grid_size", 10),
                        page_width=pm.get("page_width", 1050),
                        page_height=pm.get("page_height", 1485),
                    )
                    db.add(new_page)

        elif data.pages:
            existing_by_drawio_id = {p.drawio_page_id: p for p in diagram.pages}
            submitted_drawio_ids = set()

            for idx, p_item in enumerate(data.pages):
                pid = p_item.drawio_page_id or (str(p_item.id) if p_item.id else str(uuid.uuid4())[:8])
                submitted_drawio_ids.add(pid)
                if pid in existing_by_drawio_id:
                    page = existing_by_drawio_id[pid]
                    page.name = p_item.name or page.name
                    page.page_order = p_item.page_order if p_item.page_order is not None else idx
                    if p_item.xml_content:
                        page.xml_content = p_item.xml_content
                    page.background_color = p_item.background_color or page.background_color
                    page.grid_enabled = p_item.grid_enabled if p_item.grid_enabled is not None else page.grid_enabled
                    page.grid_size = p_item.grid_size if p_item.grid_size is not None else page.grid_size
                    page.page_width = p_item.page_width if p_item.page_width is not None else page.page_width
                    page.page_height = p_item.page_height if p_item.page_height is not None else page.page_height
                    page.updated_at = tz.now()
                else:
                    new_page = FlowPage(
                        diagram_id=diagram.id,
                        drawio_page_id=pid,
                        name=p_item.name or f"Page-{idx + 1}",
                        page_order=p_item.page_order if p_item.page_order is not None else idx,
                        xml_content=p_item.xml_content or drawio_utils.DEFAULT_MXGRAPH_XML,
                        background_color=p_item.background_color or "#FFFFFF",
                        grid_enabled=p_item.grid_enabled if p_item.grid_enabled is not None else True,
                        grid_size=p_item.grid_size if p_item.grid_size is not None else 10,
                        page_width=p_item.page_width if p_item.page_width is not None else 1050,
                        page_height=p_item.page_height if p_item.page_height is not None else 1485,
                    )
                    db.add(new_page)

        if data.thumbnail_base64:
            diagram.thumbnail_url = data.thumbnail_base64

        diagram.version += 1
        diagram.updated_by = user.id
        diagram.updated_at = tz.now()
        db.commit()
        db.refresh(diagram)

        return FlowDiagramSyncResult(
            diagram_id=diagram.id,
            version=diagram.version,
            pages_count=len(diagram.pages),
            updated_at=diagram.updated_at,
        )

    @classmethod
    def delete_diagram(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
    ) -> None:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        db.delete(diagram)
        db.commit()

    @classmethod
    def add_page(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
        data: FlowPageCreateRequest,
    ) -> FlowPageResponse:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        max_order = max([p.page_order for p in diagram.pages], default=-1)
        new_page = FlowPage(
            diagram_id=diagram.id,
            drawio_page_id=str(uuid.uuid4())[:8],
            name=data.name.strip(),
            page_order=max_order + 1,
            xml_content=data.xml_content or drawio_utils.DEFAULT_MXGRAPH_XML,
            background_color=data.background_color,
            grid_enabled=data.grid_enabled,
            grid_size=data.grid_size,
            page_width=data.page_width,
            page_height=data.page_height,
        )
        db.add(new_page)

        diagram.version += 1
        diagram.updated_by = user.id
        diagram.updated_at = tz.now()
        db.commit()
        db.refresh(new_page)

        return FlowPageResponse(
            id=new_page.id,
            diagram_id=new_page.diagram_id,
            drawio_page_id=new_page.drawio_page_id,
            name=new_page.name,
            page_order=new_page.page_order,
            xml_content=new_page.xml_content,
            compressed_xml=new_page.compressed_xml,
            background_color=new_page.background_color,
            grid_enabled=new_page.grid_enabled,
            grid_size=new_page.grid_size,
            page_width=new_page.page_width,
            page_height=new_page.page_height,
            updated_at=new_page.updated_at,
        )

    @classmethod
    def update_page(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        page_id: uuid.UUID,
        user: User,
        data: FlowPageUpdateRequest,
    ) -> FlowPageResponse:
        page = (
            db.query(FlowPage)
            .join(FlowDiagram)
            .filter(
                FlowPage.id == page_id,
                FlowPage.diagram_id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Page not found in this diagram.",
            )

        if data.name is not None:
            page.name = data.name.strip()
        if data.xml_content is not None:
            page.xml_content = data.xml_content
        if data.background_color is not None:
            page.background_color = data.background_color
        if data.grid_enabled is not None:
            page.grid_enabled = data.grid_enabled
        if data.grid_size is not None:
            page.grid_size = data.grid_size
        if data.page_width is not None:
            page.page_width = data.page_width
        if data.page_height is not None:
            page.page_height = data.page_height

        page.updated_at = tz.now()
        page.diagram.version += 1
        page.diagram.updated_by = user.id
        page.diagram.updated_at = tz.now()

        db.commit()
        db.refresh(page)

        return FlowPageResponse(
            id=page.id,
            diagram_id=page.diagram_id,
            drawio_page_id=page.drawio_page_id,
            name=page.name,
            page_order=page.page_order,
            xml_content=page.xml_content,
            compressed_xml=page.compressed_xml,
            background_color=page.background_color,
            grid_enabled=page.grid_enabled,
            grid_size=page.grid_size,
            page_width=page.page_width,
            page_height=page.page_height,
            updated_at=page.updated_at,
        )

    @classmethod
    def delete_page(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        page_id: uuid.UUID,
        user: User,
    ) -> None:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        if len(diagram.pages) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the last remaining page in a diagram. A diagram must contain at least one canvas page.",
            )

        target = next((p for p in diagram.pages if p.id == page_id), None)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Page not found in this diagram.",
            )

        db.delete(target)
        diagram.version += 1
        diagram.updated_by = user.id
        diagram.updated_at = tz.now()

        # Reindex remaining pages
        remaining = [p for p in diagram.pages if p.id != page_id]
        remaining.sort(key=lambda p: p.page_order)
        for idx, p in enumerate(remaining):
            p.page_order = idx

        db.commit()

    @classmethod
    def reorder_pages(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        user: User,
        data: FlowPageReorderRequest,
    ) -> list[FlowPageResponse]:
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        page_map = {p.id: p for p in diagram.pages}
        for item in data.page_orders:
            if item.page_id in page_map:
                page_map[item.page_id].page_order = item.page_order

        diagram.version += 1
        diagram.updated_by = user.id
        diagram.updated_at = tz.now()
        db.commit()
        db.refresh(diagram)

        sorted_pages = sorted(diagram.pages, key=lambda p: p.page_order)
        return [
            FlowPageResponse(
                id=p.id,
                diagram_id=p.diagram_id,
                drawio_page_id=p.drawio_page_id,
                name=p.name,
                page_order=p.page_order,
                xml_content=p.xml_content,
                compressed_xml=p.compressed_xml,
                background_color=p.background_color,
                grid_enabled=p.grid_enabled,
                grid_size=p.grid_size,
                page_width=p.page_width,
                page_height=p.page_height,
                updated_at=p.updated_at,
            )
            for p in sorted_pages
        ]

    # ── Export Generator ───────────────────────────────────────────────────────

    @classmethod
    def export_diagram(
        cls,
        db: Session,
        project_id: uuid.UUID,
        diagram_id: uuid.UUID,
        format_type: str = "drawio",
        page_id: Optional[str] = None,
    ) -> tuple[str, str, str]:
        """
        Generates exported payload matching format.
        Returns tuple: (content_str, content_type, filename)
        """
        diagram = (
            db.query(FlowDiagram)
            .filter(
                FlowDiagram.id == diagram_id,
                FlowDiagram.project_id == project_id,
            )
            .first()
        )
        if not diagram:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flow diagram not found.",
            )

        pages = list(diagram.pages)
        if page_id:
            pages = [p for p in pages if str(p.id) == page_id or p.drawio_page_id == page_id]
            if not pages:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Specified page '{page_id}' not found in diagram.",
                )

        sanitized_title = drawio_utils.sanitize_filename(diagram.title)
        fmt = format_type.lower()

        if fmt in ["drawio", "drawio_xml", "xml"]:
            xml_content = drawio_utils.build_mxfile(pages, modified=diagram.updated_at)
            ext = "drawio" if fmt == "drawio" else "drawio.xml"
            return (
                xml_content,
                "application/vnd.jgraph.mxfile",
                f"{sanitized_title}.{ext}",
            )

        elif fmt == "svg":
            first_page = pages[0]
            w = first_page.page_width
            h = first_page.page_height
            bg = first_page.background_color
            mx_xml = drawio_utils.build_mxfile(pages, modified=diagram.updated_at)
            escaped_xml = html.escape(mx_xml)

            # Standard Draw.io embedded SVG wrapper
            svg_content = (
                f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="{w}px" height="{h}px" viewBox="-0.5 -0.5 {w} {h}" '
                f'content="{escaped_xml}">\n'
                f'  <defs/>\n'
                f'  <rect width="100%" height="100%" fill="{bg}"/>\n'
                f'  <g>\n'
                f'    <text x="20" y="40" font-family="Helvetica" font-size="16" fill="#333333">{html.escape(diagram.title)}</text>\n'
                f'  </g>\n'
                f'</svg>'
            )
            return (
                svg_content,
                "image/svg+xml",
                f"{sanitized_title}.svg",
            )

        elif fmt == "json":
            detail = cls.get_diagram(db, project_id, diagram_id)
            import json

            return (
                json.dumps(detail.model_dump(mode="json"), indent=2),
                "application/json",
                f"{sanitized_title}.json",
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported export format '{format_type}'. Supported formats: 'drawio', 'xml', 'svg', 'json'.",
            )
