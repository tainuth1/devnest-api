import uuid
import pytest
from app.core.enums import ProjectRole
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.flow.models import FlowDiagram, FlowPage
from app.modules.projects.models import Project, ProjectMember


def _create_user(db_session, email="owner@example.com", username="owner_user"):
    user = User(
        email=email,
        username=username,
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email="owner@example.com", password="Secret123!"):
    resp = client.post(
        "/api/auth/login",
        json={
            "login_id": email,
            "password": password,
            "website": "",
            "phone_confirm": "",
        },
    )
    assert resp.status_code == 200, resp.json()
    cookie = resp.cookies.get("session_id")
    assert cookie is not None
    client.cookies.set("session_id", cookie)
    return cookie


def _create_project_with_members(db_session, owner, collaborators=None):
    code = str(uuid.uuid4()).replace("-", "")[:20].upper()
    proj = Project(
        project_code=code,
        name="Architecture Workspace",
        slug=f"arch-{code.lower()[:8]}",
        owner_id=owner.id,
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    owner_mem = ProjectMember(
        project_id=proj.id,
        user_id=owner.id,
        role=ProjectRole.OWNER.value,
    )
    db_session.add(owner_mem)

    if collaborators:
        for u, role in collaborators:
            m = ProjectMember(
                project_id=proj.id,
                user_id=u.id,
                role=role.value if hasattr(role, "value") else str(role),
            )
            db_session.add(m)

    db_session.commit()
    return proj


SAMPLE_DRAWIO_XML = """<mxfile host="dev-nest" modified="2026-10-13T12:00:00Z" agent="DevNest" version="24.7.17">
  <diagram id="diag_auth" name="Authentication Flow">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1050" pageHeight="1485" background="#F8FAFC" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="2" value="Auth Gateway" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="120" y="120" width="160" height="80" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
  <diagram id="diag_db" name="Database Pipeline">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="800" pageHeight="600" background="#FFFFFF" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="3" value="Postgres Primary" style="shape=cylinder3;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="200" y="200" width="100" height="120" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""


def test_create_flow_diagram_default(client, db_session):
    """Test 6.2: Create new diagram with default Draw.io scaffolding"""
    owner = _create_user(db_session, "owner1@example.com", "owner1")
    _login(client, "owner1@example.com")
    project = _create_project_with_members(db_session, owner)

    resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={
            "title": "Core System Flow",
            "description": "High-level service topology",
        },
    )
    assert resp.status_code == 201, resp.json()
    data = resp.json()["data"]

    assert data["title"] == "Core System Flow"
    assert data["description"] == "High-level service topology"
    assert data["version"] == 1
    assert data["is_locked"] is False
    assert len(data["pages"]) == 1
    assert data["pages"][0]["name"] == "Page-1"
    assert "<mxfile" in data["xml_content"]
    assert "<diagram" in data["xml_content"]
    assert "<mxGraphModel" in data["xml_content"]


def test_create_flow_diagram_with_imported_xml(client, db_session):
    """Test 6.2: Create diagram importing existing multi-page Draw.io XML"""
    owner = _create_user(db_session, "owner2@example.com", "owner2")
    _login(client, "owner2@example.com")
    project = _create_project_with_members(db_session, owner)

    resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={
            "title": "Imported Microservices Architecture",
            "description": "Imported from existing .drawio file",
            "xml_content": SAMPLE_DRAWIO_XML,
        },
    )
    assert resp.status_code == 201, resp.json()
    data = resp.json()["data"]

    assert data["title"] == "Imported Microservices Architecture"
    assert len(data["pages"]) == 2

    page_names = [p["name"] for p in data["pages"]]
    assert "Authentication Flow" in page_names
    assert "Database Pipeline" in page_names

    page_auth = next(p for p in data["pages"] if p["name"] == "Authentication Flow")
    assert page_auth["drawio_page_id"] == "diag_auth"
    assert page_auth["background_color"] == "#F8FAFC"
    assert "Auth Gateway" in page_auth["xml_content"]

    page_db = next(p for p in data["pages"] if p["name"] == "Database Pipeline")
    assert page_db["drawio_page_id"] == "diag_db"
    assert page_db["page_width"] == 800
    assert page_db["page_height"] == 600


def test_list_and_get_flow_diagrams(client, db_session):
    """Test 6.1 & 6.3: List diagrams with search and full canvas hydration"""
    owner = _create_user(db_session, "owner3@example.com", "owner3")
    _login(client, "owner3@example.com")
    project = _create_project_with_members(db_session, owner)

    # Create 2 diagrams
    client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Payment Gateway Pipeline"},
    )
    client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Notification Queue Worker"},
    )

    # List all
    list_resp = client.get(f"/api/projects/{project.id}/flow-diagrams")
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] == 2
    assert len(list_data["items"]) == 2

    # Search filter
    search_resp = client.get(f"/api/projects/{project.id}/flow-diagrams?q=payment")
    assert search_resp.status_code == 200
    search_data = search_resp.json()["data"]
    assert search_data["total"] == 1
    assert search_data["items"][0]["title"] == "Payment Gateway Pipeline"

    # Get single diagram
    diag_id = search_data["items"][0]["id"]
    get_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["id"] == diag_id
    assert "<mxfile" in get_data["xml_content"]
    assert len(get_data["pages"]) >= 1


def test_update_diagram_meta(client, db_session):
    """Test updating title and description"""
    owner = _create_user(db_session, "owner_meta@example.com", "owner_meta")
    _login(client, "owner_meta@example.com")
    project = _create_project_with_members(db_session, owner)

    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Old Name", "description": "Old Desc"},
    )
    diag_id = create_resp.json()["data"]["id"]

    patch_resp = client.patch(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}",
        json={"title": "New Name", "description": "New Desc"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["title"] == "New Name"
    assert patch_resp.json()["data"]["description"] == "New Desc"


def test_acquire_and_release_lock(client, db_session):
    """Test 6.4: Exclusive canvas editing lock lifecycle"""
    owner = _create_user(db_session, "owner4@example.com", "owner4")
    editor = _create_user(db_session, "editor4@example.com", "editor4")
    project = _create_project_with_members(
        db_session, owner, [(editor, ProjectRole.EDITOR)]
    )

    _login(client, "owner4@example.com")
    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Collaborative Diagram"},
    )
    diag_id = create_resp.json()["data"]["id"]

    # Owner acquires lock
    lock_resp = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/lock")
    assert lock_resp.status_code == 200
    assert lock_resp.json()["data"]["is_locked"] is True

    # Editor attempts to acquire lock -> 423 Locked
    _login(client, "editor4@example.com")
    locked_resp = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/lock")
    assert locked_resp.status_code == 423

    # Editor attempts to sync -> 423 Locked
    sync_blocked = client.put(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/sync",
        json={"expected_version": 1, "xml_content": SAMPLE_DRAWIO_XML},
    )
    assert sync_blocked.status_code == 423

    # Editor cannot release owner's lock -> 403 Forbidden
    cant_unlock = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/unlock")
    assert cant_unlock.status_code == 403

    # Owner releases lock
    _login(client, "owner4@example.com")
    unlock_resp = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/unlock")
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["data"]["is_locked"] is False

    # Editor can now acquire lock
    _login(client, "editor4@example.com")
    editor_lock = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/lock")
    assert editor_lock.status_code == 200
    assert editor_lock.json()["data"]["is_locked"] is True


def test_sync_diagram_with_xml_and_concurrency_conflict(client, db_session):
    """Test 6.5: Auto-Save & Sync with optimistic lock verification"""
    owner = _create_user(db_session, "owner5@example.com", "owner5")
    _login(client, "owner5@example.com")
    project = _create_project_with_members(db_session, owner)

    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Sync Test Diagram"},
    )
    diag_id = create_resp.json()["data"]["id"]
    version = create_resp.json()["data"]["version"]
    assert version == 1

    # Successful sync updating with complete <mxfile> XML directly
    sync_resp = client.put(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/sync",
        json={
            "expected_version": 1,
            "thumbnail_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "xml_content": SAMPLE_DRAWIO_XML,
        },
    )
    assert sync_resp.status_code == 200, sync_resp.json()
    sync_data = sync_resp.json()["data"]
    assert sync_data["version"] == 2
    assert sync_data["pages_count"] == 2

    # Verify updated diagram details
    get_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]["pages"]) == 2

    # Conflict on outdated expected_version (sending expected_version: 1 when version is now 2) -> 409 Conflict
    conflict_resp = client.put(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/sync",
        json={
            "expected_version": 1,
            "xml_content": SAMPLE_DRAWIO_XML,
        },
    )
    assert conflict_resp.status_code == 409
    assert "modified by another collaborator" in conflict_resp.json()["message"].lower()


def test_flow_page_crud_and_reorder(client, db_session):
    """Test 6.6: Canvas pages management (add, update, reorder, delete)"""
    owner = _create_user(db_session, "owner6@example.com", "owner6")
    _login(client, "owner6@example.com")
    project = _create_project_with_members(db_session, owner)

    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Multi-Page Workspace"},
    )
    diag_id = create_resp.json()["data"]["id"]
    page1_id = create_resp.json()["data"]["pages"][0]["id"]

    # 1. Add new page
    add_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/pages",
        json={
            "name": "Service Discovery",
            "background_color": "#EEEEEE",
            "page_width": 1200,
            "page_height": 900,
        },
    )
    assert add_resp.status_code == 201, add_resp.json()
    page2_id = add_resp.json()["data"]["id"]
    assert add_resp.json()["data"]["name"] == "Service Discovery"
    assert add_resp.json()["data"]["page_order"] == 1

    # 2. Update page
    patch_resp = client.patch(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/pages/{page2_id}",
        json={"name": "Consul Service Mesh", "background_color": "#F0FDF4"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["name"] == "Consul Service Mesh"
    assert patch_resp.json()["data"]["background_color"] == "#F0FDF4"

    # 3. Reorder pages (swap order)
    reorder_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams/{diag_id}/pages/reorder",
        json={
            "page_orders": [
                {"page_id": page2_id, "page_order": 0},
                {"page_id": page1_id, "page_order": 1},
            ]
        },
    )
    assert reorder_resp.status_code == 200
    pages_ordered = reorder_resp.json()["data"]
    assert pages_ordered[0]["id"] == page2_id
    assert pages_ordered[0]["page_order"] == 0
    assert pages_ordered[1]["id"] == page1_id
    assert pages_ordered[1]["page_order"] == 1

    # 4. Delete page
    del_resp = client.delete(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/pages/{page2_id}")
    assert del_resp.status_code == 200

    # 5. Cannot delete the only remaining page -> 400 Bad Request
    del_last = client.delete(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/pages/{page1_id}")
    assert del_last.status_code == 400
    assert "at least one" in del_last.json()["message"].lower()



def test_export_flow_diagram(client, db_session):
    """Test 6.8: Export diagram in drawio, svg, and json formats"""
    owner = _create_user(db_session, "owner8@example.com", "owner8")
    _login(client, "owner8@example.com")
    project = _create_project_with_members(db_session, owner)

    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Export Test", "xml_content": SAMPLE_DRAWIO_XML},
    )
    diag_id = create_resp.json()["data"]["id"]

    # 1. Export as drawio
    drawio_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/export?format=drawio")
    assert drawio_resp.status_code == 200
    assert "application/vnd.jgraph.mxfile" in drawio_resp.headers["Content-Type"]
    assert "attachment" in drawio_resp.headers["Content-Disposition"]
    assert "<mxfile" in drawio_resp.text

    # 2. Export as SVG
    svg_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/export?format=svg")
    assert svg_resp.status_code == 200
    assert "image/svg+xml" in svg_resp.headers["Content-Type"]
    assert "<svg" in svg_resp.text

    # 3. Export as JSON
    json_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/export?format=json")
    assert json_resp.status_code == 200
    assert "application/json" in json_resp.headers["Content-Type"]
    assert "pages" in json_resp.text


def test_delete_flow_diagram(client, db_session):
    """Test 6.9: Delete flow diagram and verify cascade"""
    owner = _create_user(db_session, "owner9@example.com", "owner9")
    _login(client, "owner9@example.com")
    project = _create_project_with_members(db_session, owner)

    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Diagram to Delete"},
    )
    diag_id = create_resp.json()["data"]["id"]

    del_resp = client.delete(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert del_resp.status_code == 200

    # Ensure 404 on subsequent get
    get_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert get_resp.status_code == 404

    # Ensure pages cascaded in DB
    pages_count = db_session.query(FlowPage).filter(FlowPage.diagram_id == uuid.UUID(diag_id)).count()
    assert pages_count == 0


def test_rbac_permissions(client, db_session):
    """Test RBAC enforcement: VIEWER can read/export, cannot edit; non-member gets 404"""
    owner = _create_user(db_session, "owner_rbac@example.com", "owner_rbac")
    viewer = _create_user(db_session, "viewer_rbac@example.com", "viewer_rbac")
    outsider = _create_user(db_session, "outsider@example.com", "outsider")

    project = _create_project_with_members(
        db_session, owner, [(viewer, ProjectRole.VIEWER)]
    )

    _login(client, "owner_rbac@example.com")
    create_resp = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "RBAC Secured Flow"},
    )
    diag_id = create_resp.json()["data"]["id"]

    # 1. VIEWER can read
    _login(client, "viewer_rbac@example.com")
    get_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert get_resp.status_code == 200

    # VIEWER can export
    export_resp = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/export")
    assert export_resp.status_code == 200

    # VIEWER cannot create diagram -> 403 Forbidden
    create_blocked = client.post(
        f"/api/projects/{project.id}/flow-diagrams",
        json={"title": "Viewer Attempt"},
    )
    assert create_blocked.status_code == 403

    # VIEWER cannot acquire lock -> 403 Forbidden
    lock_blocked = client.post(f"/api/projects/{project.id}/flow-diagrams/{diag_id}/lock")
    assert lock_blocked.status_code == 403

    # VIEWER cannot delete -> 403 Forbidden
    del_blocked = client.delete(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert del_blocked.status_code == 403

    # 2. Non-member receives 404 Not Found (tenant isolation)
    _login(client, "outsider@example.com")
    outsider_get = client.get(f"/api/projects/{project.id}/flow-diagrams/{diag_id}")
    assert outsider_get.status_code == 404
