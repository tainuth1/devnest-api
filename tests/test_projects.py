import uuid
import pytest
from app.core.enums import ProjectRole, ProjectStatus
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectMember


def _create_test_user(db_session, email="developer@example.com", username="developer"):
    user = User(
        email=email,
        username=username,
        password=hash_password("DevPassword123!"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_user(client, email="developer@example.com", password="DevPassword123!"):
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
    session_cookie = resp.cookies.get("session_id")
    assert session_cookie is not None
    client.cookies.set("session_id", session_cookie)
    return session_cookie


def test_create_project_success(client, db_session):
    """Test 2.2: Create New Project (Blank or From Template)"""
    user = _create_test_user(db_session)
    _login_user(client, user.email)

    resp = client.post(
        "/api/projects",
        json={
            "name": "Fintech Core Gateway",
            "description": "High-throughput transaction router and double-entry ledger.",
            "settings": {
                "default_sql_dialect": "postgresql",
                "auto_save_interval_ms": 2000,
            },
        },
    )
    assert resp.status_code == 201, resp.json()
    data = resp.json()["data"]

    assert data["name"] == "Fintech Core Gateway"
    assert data["slug"] == "fintech-core-gateway"
    assert len(data["project_code"]) == 20
    assert data["my_role"] == "OWNER"
    assert data["status"] == "Not Started"
    assert data["color"] == "#6366F1"
    assert data["icon"] == "folder"
    assert data["settings"]["default_sql_dialect"] == "postgresql"

    # Verify Project and ProjectMember in database
    project_db = db_session.query(Project).filter_by(id=uuid.UUID(data["id"])).first()
    assert project_db is not None
    assert project_db.project_code == data["project_code"]

    member_db = db_session.query(ProjectMember).filter_by(project_id=project_db.id, user_id=user.id).first()
    assert member_db is not None
    assert member_db.role == ProjectRole.OWNER.value


def test_create_project_blank_name_validation(client, db_session):
    """Test 2.2: Blank name validation on create project"""
    user = _create_test_user(db_session, email="validator@example.com", username="validator")
    _login_user(client, user.email)

    # Blank name
    resp = client.post(
        "/api/projects",
        json={"name": "   "},
    )
    assert resp.status_code == 422


def test_list_projects_and_filtering(client, db_session):
    """Test 2.1: List User Projects with filters, search, and pagination"""
    user1 = _create_test_user(db_session, email="u1@example.com", username="u1")
    user2 = _create_test_user(db_session, email="u2@example.com", username="u2")

    _login_user(client, user1.email)

    # Create 3 projects as user1
    resp_p1 = client.post("/api/projects", json={"name": "Alpha Service"})
    p1_id = resp_p1.json()["data"]["id"]
    client.patch(f"/api/projects/{p1_id}/status", json={"status": "In Progress"})

    resp_p2 = client.post("/api/projects", json={"name": "Beta API"})

    resp_p3 = client.post("/api/projects", json={"name": "Gamma Portal"})
    p3_id = resp_p3.json()["data"]["id"]
    client.patch(f"/api/projects/{p3_id}/status", json={"status": "In Review"})

    p1_code = resp_p1.json()["data"]["project_code"]
    p2_code = resp_p2.json()["data"]["project_code"]

    # Add user2 to p1 as EDITOR
    p1_id = uuid.UUID(resp_p1.json()["data"]["id"])
    pm_user2 = ProjectMember(
        project_id=p1_id,
        user_id=user2.id,
        role=ProjectRole.EDITOR.value,
        order_index=5,
        is_pinned=False,
    )
    db_session.add(pm_user2)
    db_session.commit()

    # User 1 listings
    list_resp = client.get("/api/projects")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert len(items) == 3

    # Filter by status: In Progress
    filter_status_resp = client.get("/api/projects?status=In Progress")
    assert filter_status_resp.status_code == 200
    assert len(filter_status_resp.json()["data"]["items"]) == 1
    assert filter_status_resp.json()["data"]["items"][0]["name"] == "Alpha Service"

    # Search by q
    search_resp = client.get(f"/api/projects?q={p2_code}")
    assert search_resp.status_code == 200
    assert len(search_resp.json()["data"]["items"]) == 1
    assert search_resp.json()["data"]["items"][0]["name"] == "Beta API"

    # Switch to User 2: should only see p1 where user2 is member
    _login_user(client, user2.email)
    u2_list = client.get("/api/projects")
    assert u2_list.status_code == 200
    u2_items = u2_list.json()["data"]["items"]
    assert len(u2_items) == 1
    assert u2_items[0]["name"] == "Alpha Service"
    assert u2_items[0]["my_role"] == "EDITOR"
    assert u2_items[0]["order_index"] == 5
    assert u2_items[0]["members_count"] == 2


def test_get_project_summary(client, db_session):
    """Test 2.3: Get Project Workspace Summary by UUID and by project_code"""
    owner = _create_test_user(db_session, email="owner@example.com", username="owner")
    other = _create_test_user(db_session, email="other@example.com", username="other")

    _login_user(client, owner.email)

    create_resp = client.post(
        "/api/projects",
        json={"name": "E-Commerce Gateway", "description": "Cloud native microservices."},
    )
    p_data = create_resp.json()["data"]
    p_id = p_data["id"]
    p_code = p_data["project_code"]

    # 1. Fetch by UUID
    get_by_id = client.get(f"/api/projects/{p_id}")
    assert get_by_id.status_code == 200
    assert get_by_id.json()["data"]["name"] == "E-Commerce Gateway"
    assert len(get_by_id.json()["data"]["members"]) == 1

    # 2. Fetch by 20-character project_code
    get_by_code = client.get(f"/api/projects/{p_code}")
    assert get_by_code.status_code == 200
    assert get_by_code.json()["data"]["id"] == p_id

    # 3. Non-member access returns 404
    _login_user(client, other.email)
    forbidden_get = client.get(f"/api/projects/{p_id}")
    assert forbidden_get.status_code == 404


def test_update_project_details_and_rbac(client, db_session):
    """Test 2.4: Update Project Details & Settings + RBAC permissions"""
    owner = _create_test_user(db_session, email="p_owner@example.com", username="p_owner")
    viewer = _create_test_user(db_session, email="p_viewer@example.com", username="p_viewer")

    _login_user(client, owner.email)
    p_resp = client.post("/api/projects", json={"name": "Original Name"})
    p_id = p_resp.json()["data"]["id"]

    # Add viewer
    pm = ProjectMember(
        project_id=uuid.UUID(p_id),
        user_id=viewer.id,
        role=ProjectRole.VIEWER.value,
    )
    db_session.add(pm)
    db_session.commit()

    # Owner updates details
    update_resp = client.patch(
        f"/api/projects/{p_id}",
        json={
            "name": "Updated Name v2",
            "color": "#0EA5E9",
            "icon": "server",
            "settings": {"auto_save_interval_ms": 1500},
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"] == "Updated Name v2"
    assert update_resp.json()["data"]["color"] == "#0EA5E9"
    assert update_resp.json()["data"]["settings"]["auto_save_interval_ms"] == 1500

    # Viewer attempts update -> 403 Forbidden
    _login_user(client, viewer.email)
    viewer_update = client.patch(
        f"/api/projects/{p_id}",
        json={"name": "Hacked Name"},
    )
    assert viewer_update.status_code == 403


def test_update_project_status(client, db_session):
    """Test 2.5: Update Project Lifecycle Status"""
    owner = _create_test_user(db_session, email="status_owner@example.com", username="status_owner")
    _login_user(client, owner.email)

    p_resp = client.post("/api/projects", json={"name": "Status Project"})
    p_id = p_resp.json()["data"]["id"]

    status_resp = client.patch(
        f"/api/projects/{p_id}/status",
        json={"status": "In Review"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "In Review"

    # Invalid status
    bad_status = client.patch(
        f"/api/projects/{p_id}/status",
        json={"status": "Bad Status"},
    )
    assert bad_status.status_code == 422


def test_update_project_personal_order_isolation(client, db_session):
    """Test 2.6: Updating order_index isolates changes to caller only (rule BR-PROJ-06)"""
    userA = _create_test_user(db_session, email="usera@example.com", username="usera")
    userB = _create_test_user(db_session, email="userb@example.com", username="userb")

    _login_user(client, userA.email)
    p_resp = client.post("/api/projects", json={"name": "Shared Project"})
    p_id = uuid.UUID(p_resp.json()["data"]["id"])

    # Add userB to project with order_index 10
    pm_b = ProjectMember(
        project_id=p_id,
        user_id=userB.id,
        role=ProjectRole.EDITOR.value,
        order_index=10,
        is_pinned=False,
    )
    db_session.add(pm_b)
    db_session.commit()

    # User A updates order to 5
    order_a_resp = client.patch(f"/api/projects/{p_id}/order", json={"order_index": 5, "is_pinned": True})
    assert order_a_resp.status_code == 200
    assert order_a_resp.json()["data"]["order_index"] == 5

    # Verify in DB: User A's member row is 5, User B's member row remains 10!
    pm_a_db = db_session.query(ProjectMember).filter_by(project_id=p_id, user_id=userA.id).first()
    pm_b_db = db_session.query(ProjectMember).filter_by(project_id=p_id, user_id=userB.id).first()

    assert pm_a_db.order_index == 5
    assert pm_a_db.is_pinned is True
    assert pm_b_db.order_index == 10
    assert pm_b_db.is_pinned is False


def test_batch_reorder(client, db_session):
    """Test PUT /projects/reorder"""
    user = _create_test_user(db_session, email="batch_user@example.com", username="batch_user")
    _login_user(client, user.email)

    p1 = client.post("/api/projects", json={"name": "Batch P1"}).json()["data"]["id"]
    p2 = client.post("/api/projects", json={"name": "Batch P2"}).json()["data"]["id"]

    reorder_resp = client.put(
        "/api/projects/reorder",
        json={
            "items": [
                {"project_id": p1, "order_index": 2},
                {"project_id": p2, "order_index": 1},
            ]
        },
    )
    assert reorder_resp.status_code == 200
    assert len(reorder_resp.json()["data"]) == 2


def test_delete_project_slug_match_and_rbac(client, db_session):
    """Test 2.7: Delete Project requires OWNER role and slug match"""
    owner = _create_test_user(db_session, email="del_owner@example.com", username="del_owner")
    admin_member = _create_test_user(db_session, email="del_admin@example.com", username="del_admin")

    _login_user(client, owner.email)
    p_resp = client.post("/api/projects", json={"name": "Fintech Ledger Gateway"})
    p_data = p_resp.json()["data"]
    p_id = p_data["id"]
    p_slug = p_data["slug"]

    # Add admin_member to project as ADMIN
    pm_admin = ProjectMember(
        project_id=uuid.UUID(p_id),
        user_id=admin_member.id,
        role=ProjectRole.ADMIN.value,
    )
    db_session.add(pm_admin)
    db_session.commit()

    # 1. Admin tries to delete -> 403 Forbidden (Only OWNER can delete)
    _login_user(client, admin_member.email)
    admin_del = client.request(
        "DELETE",
        f"/api/projects/{p_id}",
        json={"confirm_slug": p_slug},
    )
    assert admin_del.status_code == 403

    # 2. Owner supplies mismatched slug -> 400 Bad Request
    _login_user(client, owner.email)
    mismatch_del = client.request(
        "DELETE",
        f"/api/projects/{p_id}",
        json={"confirm_slug": "wrong-slug"},
    )
    assert mismatch_del.status_code == 400

    # 3. Owner supplies correct slug -> 200 OK and purged
    success_del = client.request(
        "DELETE",
        f"/api/projects/{p_id}",
        json={"confirm_slug": p_slug},
    )
    assert success_del.status_code == 200
    assert success_del.json()["data"] is None

    # Project and members should no longer exist
    assert db_session.query(Project).filter_by(id=uuid.UUID(p_id)).first() is None
    assert db_session.query(ProjectMember).filter_by(project_id=uuid.UUID(p_id)).first() is None


def test_exhaustive_rbac_matrix_enforcement(client, db_session):
    """
    Exhaustively tests the Role-Based Access Control (RBAC) matrix from
    Section 2 of 2_BUSINESS_LOGICS.md:
      - Owner: All actions allowed
      - Admin: Allowed except Delete Project
      - Editor: Allowed to View and Reorder; Denied on Update Details, Status, Delete
      - Viewer: Allowed to View and Reorder; Denied on Update Details, Status, Delete
      - Non-Member: Strictly Denied (404 Not Found to prevent enumeration) on all endpoints
    """
    owner = _create_test_user(db_session, email="matrix_owner@example.com", username="m_owner")
    admin = _create_test_user(db_session, email="matrix_admin@example.com", username="m_admin")
    editor = _create_test_user(db_session, email="matrix_editor@example.com", username="m_editor")
    viewer = _create_test_user(db_session, email="matrix_viewer@example.com", username="m_viewer")
    non_member = _create_test_user(db_session, email="matrix_nonmember@example.com", username="m_nonmember")

    _login_user(client, owner.email)
    p_resp = client.post("/api/projects", json={"name": "RBAC Fortress Gateway"})
    p_data = p_resp.json()["data"]
    p_id = p_data["id"]
    p_slug = p_data["slug"]
    p_uuid = uuid.UUID(p_id)

    # Assign roles in project_members
    db_session.add_all([
        ProjectMember(project_id=p_uuid, user_id=admin.id, role=ProjectRole.ADMIN.value, order_index=1),
        ProjectMember(project_id=p_uuid, user_id=editor.id, role=ProjectRole.EDITOR.value, order_index=2),
        ProjectMember(project_id=p_uuid, user_id=viewer.id, role=ProjectRole.VIEWER.value, order_index=3),
    ])
    db_session.commit()

    # ── 1. Action: View Project & Workspace Summary (GET /projects/{id}) ──
    # Expected: Owner(200), Admin(200), Editor(200), Viewer(200), Non-Member(404)
    for u in (owner, admin, editor, viewer):
        _login_user(client, u.email)
        res = client.get(f"/api/projects/{p_id}")
        assert res.status_code == 200, f"Failed for role {u.email}: {res.text}"

    _login_user(client, non_member.email)
    assert client.get(f"/api/projects/{p_id}").status_code == 404

    # ── 2. Action: Update Project Details & Settings (PATCH /projects/{id}) ──
    # Expected: Owner(200), Admin(200), Editor(403), Viewer(403), Non-Member(404)
    for u in (owner, admin):
        _login_user(client, u.email)
        res = client.patch(f"/api/projects/{p_id}", json={"description": f"Updated by {u.email}"})
        assert res.status_code == 200, f"Expected 200 for {u.email}, got {res.status_code}"

    for u in (editor, viewer):
        _login_user(client, u.email)
        res = client.patch(f"/api/projects/{p_id}", json={"description": "Unauthorized edit"})
        assert res.status_code == 403, f"Expected 403 for {u.email}, got {res.status_code}"

    _login_user(client, non_member.email)
    assert client.patch(f"/api/projects/{p_id}", json={"description": "Hacked"}).status_code == 404

    # ── 3. Action: Change Project Lifecycle Status (PATCH /projects/{id}/status) ──
    # Expected: Owner(200), Admin(200), Editor(403), Viewer(403), Non-Member(404)
    for u in (owner, admin):
        _login_user(client, u.email)
        res = client.patch(f"/api/projects/{p_id}/status", json={"status": "In Progress"})
        assert res.status_code == 200, f"Expected 200 for {u.email}, got {res.status_code}"

    for u in (editor, viewer):
        _login_user(client, u.email)
        res = client.patch(f"/api/projects/{p_id}/status", json={"status": "Completed"})
        assert res.status_code == 403, f"Expected 403 for {u.email}, got {res.status_code}"

    _login_user(client, non_member.email)
    assert client.patch(f"/api/projects/{p_id}/status", json={"status": "Cancelled"}).status_code == 404

    # ── 4. Action: Reorder Projects (Personal View) (PATCH /projects/{id}/order) ──
    # Expected: Owner(200), Admin(200), Editor(200), Viewer(200), Non-Member(404)
    for idx, u in enumerate((owner, admin, editor, viewer), start=1):
        _login_user(client, u.email)
        res = client.patch(f"/api/projects/{p_id}/order", json={"order_index": idx * 10})
        assert res.status_code == 200, f"Expected 200 for {u.email}, got {res.status_code}"

    _login_user(client, non_member.email)
    assert client.patch(f"/api/projects/{p_id}/order", json={"order_index": 99}).status_code == 404

    # ── 5. Action: Delete Project (DELETE /projects/{id}) ──
    # Expected: Non-Member(404), Viewer(403), Editor(403), Admin(403), Owner(200)
    _login_user(client, non_member.email)
    assert client.request("DELETE", f"/api/projects/{p_id}", json={"confirm_slug": p_slug}).status_code == 404

    for u in (viewer, editor, admin):
        _login_user(client, u.email)
        res = client.request("DELETE", f"/api/projects/{p_id}", json={"confirm_slug": p_slug})
        assert res.status_code == 403, f"Expected 403 for {u.email}, got {res.status_code}"

    # Finally, Owner purges project
    _login_user(client, owner.email)
    owner_del = client.request("DELETE", f"/api/projects/{p_id}", json={"confirm_slug": p_slug})
    assert owner_del.status_code == 200
