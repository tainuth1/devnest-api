import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


class UserMinimalInfo(BaseModel):
    id: uuid.UUID
    name: str
    email: str


class FlowDiagramSummaryResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    pages_count: int
    is_locked: bool
    locked_by: Optional[UserMinimalInfo] = None
    locked_at: Optional[datetime] = None
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FlowPageResponse(BaseModel):
    id: uuid.UUID
    diagram_id: uuid.UUID
    drawio_page_id: str
    name: str
    page_order: int
    xml_content: str
    compressed_xml: Optional[str] = None
    background_color: str
    grid_enabled: bool
    grid_size: int
    page_width: int
    page_height: int
    updated_at: datetime


class FlowDiagramDetailResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    version: int
    is_locked: bool
    locked_by: Optional[UserMinimalInfo] = None
    locked_at: Optional[datetime] = None
    xml_content: str
    pages: list[FlowPageResponse]
    created_at: datetime
    updated_at: datetime


class FlowDiagramCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150, description="Diagram title")
    description: Optional[str] = Field(None, max_length=2000, description="Diagram description")
    xml_content: Optional[str] = Field(None, description="Optional Draw.io <mxfile> XML to import")


class FlowDiagramUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)


class FlowPageSyncItem(BaseModel):
    id: Optional[uuid.UUID] = None
    drawio_page_id: Optional[str] = None
    name: Optional[str] = "Page-1"
    page_order: Optional[int] = 0
    xml_content: Optional[str] = None
    background_color: Optional[str] = "#FFFFFF"
    grid_enabled: Optional[bool] = True
    grid_size: Optional[int] = 10
    page_width: Optional[int] = 1050
    page_height: Optional[int] = 1485


class FlowDiagramSyncRequest(BaseModel):
    expected_version: int = Field(..., ge=1, description="Optimistic lock version")
    thumbnail_base64: Optional[str] = Field(None, description="Rendered PNG base64 thumbnail")
    xml_content: Optional[str] = Field(None, description="Native Draw.io <mxfile> XML from embed autosave/save")
    pages: Optional[list[FlowPageSyncItem]] = Field(None, description="Granular pages update")

    @model_validator(mode="after")
    def validate_payload(self):
        if not self.xml_content and not self.pages:
            raise ValueError("Either 'xml_content' or 'pages' must be provided for synchronization.")
        return self


class FlowDiagramSyncResult(BaseModel):
    diagram_id: uuid.UUID
    version: int
    pages_count: int
    updated_at: datetime


class FlowPageCreateRequest(BaseModel):
    name: str = Field(default="New Page", min_length=1, max_length=100)
    xml_content: Optional[str] = Field(None, description="Initial <mxGraphModel> XML")
    background_color: str = Field(default="#FFFFFF", max_length=7)
    grid_enabled: bool = True
    grid_size: int = Field(default=10, ge=1, le=100)
    page_width: int = Field(default=1050, ge=100, le=10000)
    page_height: int = Field(default=1485, ge=100, le=10000)


class FlowPageUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    xml_content: Optional[str] = None
    background_color: Optional[str] = Field(None, max_length=7)
    grid_enabled: Optional[bool] = None
    grid_size: Optional[int] = Field(None, ge=1, le=100)
    page_width: Optional[int] = Field(None, ge=100, le=10000)
    page_height: Optional[int] = Field(None, ge=100, le=10000)


class FlowPageOrderItem(BaseModel):
    page_id: uuid.UUID
    page_order: int = Field(..., ge=0)


class FlowPageReorderRequest(BaseModel):
    page_orders: list[FlowPageOrderItem]

