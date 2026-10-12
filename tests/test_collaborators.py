import hashlib
import uuid
from unittest import mock
import pytest
from datetime import timedelta

from app.core import timezone as tz
from app.core.enums import InvitationStatus, ProjectRole
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.collaborators.models import ProjectInvitation
from app.modules.projects.models import Project, ProjectMember


def _create_test_user(
    db_session,
    email="developer@example.com",
    username="developer",
    first_name="Test",
    last_name="User",
):
    user = User(
        email=email,
        username=username,
        first_name=first_name,
        last_name=last_name,
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


def _setup_project_with_roles(client, db_session):
    owner = _create_test_user(db_session, email="owner@example.com", username="owner_user", first_name="Owner", last_name="Dev")
    admin = _create_test_user(db_session, email="admin@example.com", username="admin_user", first_name="Admin", last_name="Dev")
    editor = _create_test_user(db_session, email="editor@example.com", username="editor_user", first_name="Editor", last_name="Dev")
    viewer = _create_test_user(db_session, email="viewer@example.com", username="viewer_user", first_name="Viewer", last_name="Dev")
    non_member = _create_test_user(db_session, email="outsider@example.com", username="outsider_user", first_name="Outsider", last_name="Dev")

    # Create project by owner
    _login_user(client, owner.email)
    res = client.post("/api/projects", json={"name": "Collaborative Nest"})
    assert res.status_code == 201, res.text
    p_id = res.json()["data"]["id"]
    p_uuid = uuid.UUID(p_id)

    # Add admin, editor, viewer memberships
    m_admin = ProjectMember(project_id=p_uuid, user_id=admin.id, role=ProjectRole.ADMIN.value, invited_by=owner.id)
    m_editor = ProjectMember(project_id=p_uuid, user_id=editor.id, role=ProjectRole.EDITOR.value, invited_by=owner.id)
    m_viewer = ProjectMember(project_id=p_uuid, user_id=viewer.id, role=ProjectRole.VIEWER.value, invited_by=owner.id)
    db_session.add_all([m_admin, m_editor, m_viewer])
    db_session.commit()

    return {
        "project_id": p_id,
        "owner": owner,
        "admin": admin,
        "editor": editor,
        "viewer": viewer,
        "non_member": non_member,
    }


# ── 4.1 Tests: List Project Members & Roles ───────────────────────────────────

def test_list_project_members(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]

    for u in [setup["owner"], setup["admin"], setup["editor"], setup["viewer"]]:
        _login_user(client, u.email)
        res = client.get(f"/api/projects/{p_id}/members")
        assert res.status_code == 200
        data = res.json()["data"]
        members = data["members"] if isinstance(data, dict) else data
        assert len(members) == 4
        if isinstance(data, dict):
            assert "pending_invites_count" in data
            assert data["pending_invites_count"] == 0
        # Verify schema keys
        member_emails = {m["email"] for m in members}
        assert "owner@example.com" in member_emails
        assert "admin@example.com" in member_emails
        assert all("role" in m and "joined_at" in m and "user_id" in m and "is_you" in m for m in members)
        # Verify is_you is strictly True for calling user and False for others
        for m in members:
            if m["email"] == u.email:
                assert m["is_you"] is True
            else:
                assert m["is_you"] is False

    # Non-member should receive 404 (isolation)
    _login_user(client, setup["non_member"].email)
    res = client.get(f"/api/projects/{p_id}/members")
    assert res.status_code == 404


# ── 4.2 Tests: Invite Collaborator & Dispatch Email ───────────────────────────

def test_invite_collaborator_owner_and_admin(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]

    with mock.patch("app.modules.collaborators.service.send_project_invitation_email") as mock_email:
        # Owner invites a new collaborator as EDITOR
        _login_user(client, setup["owner"].email)
        res = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "newbie_editor@example.com", "role": "EDITOR"},
        )
        assert res.status_code == 201, res.text
        data = res.json()["data"]
        assert data["invitee_email"] == "newbie_editor@example.com"
        assert data["role"] == "EDITOR"
        assert data["status"] == "PENDING"
        assert mock_email.called
        assert mock_email.call_args.kwargs["to_email"] == "newbie_editor@example.com"
        assert mock_email.call_args.kwargs["role"] == "EDITOR"

        # Admin invites a new collaborator as VIEWER (Allowed)
        _login_user(client, setup["admin"].email)
        res_admin = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "newbie_viewer@example.com", "role": "VIEWER"},
        )
        assert res_admin.status_code == 201
        assert res_admin.json()["data"]["role"] == "VIEWER"

        # Admin tries to invite someone as ADMIN (Forbidden: Admin can only invite Editor/Viewer)
        res_admin_forbidden = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "newbie_admin@example.com", "role": "ADMIN"},
        )
        assert res_admin_forbidden.status_code == 403

        # Inviting as OWNER should fail (400 or 422 validation)
        res_owner_invalid = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "attempt_owner@example.com", "role": "OWNER"},
        )
        assert res_owner_invalid.status_code in (400, 422)

        # Inviting existing member should fail
        res_existing = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": setup["editor"].email, "role": "VIEWER"},
        )
        assert res_existing.status_code == 400

        # Inviting same email again while an active pending invitation exists should fail
        res_dup = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "newbie_editor@example.com", "role": "EDITOR"},
        )
        assert res_dup.status_code == 400

        # Editor/Viewer cannot invite
        _login_user(client, setup["editor"].email)
        res_editor = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "another@example.com", "role": "VIEWER"},
        )
        assert res_editor.status_code == 403


# ── 4.3 Tests: List Pending Invitations ───────────────────────────────────────

def test_list_pending_invitations(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]

    with mock.patch("app.modules.collaborators.service.send_project_invitation_email"):
        _login_user(client, setup["owner"].email)
        client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "pending1@example.com", "role": "EDITOR"},
        )
        client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "pending2@example.com", "role": "VIEWER"},
        )

    # Owner lists invitations
    res = client.get(f"/api/projects/{p_id}/invitations")
    assert res.status_code == 200
    invites = res.json()["data"]
    assert len(invites) == 2
    emails = {i["invitee_email"] for i in invites}
    assert "pending1@example.com" in emails
    assert "pending2@example.com" in emails

    # Admin also can list
    _login_user(client, setup["admin"].email)
    res_admin = client.get(f"/api/projects/{p_id}/invitations")
    assert res_admin.status_code == 200

    # Editor cannot list invitations
    _login_user(client, setup["editor"].email)
    res_editor = client.get(f"/api/projects/{p_id}/invitations")
    assert res_editor.status_code == 403


# ── 4.4 Tests: Revoke / Cancel Invitation ─────────────────────────────────────

def test_revoke_invitation(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]

    with mock.patch("app.modules.collaborators.service.send_project_invitation_email"):
        _login_user(client, setup["owner"].email)
        inv_res = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "to_revoke@example.com", "role": "EDITOR"},
        )
        inv_id = inv_res.json()["data"]["invitation_id"]

    # Admin cancels invitation
    _login_user(client, setup["admin"].email)
    del_res = client.delete(f"/api/projects/{p_id}/invitations/{inv_id}")
    assert del_res.status_code == 200
    assert del_res.json()["message"] == "Invitation cancelled."

    # Listing pending invitations now should not include revoked one
    list_res = client.get(f"/api/projects/{p_id}/invitations")
    assert len(list_res.json()["data"]) == 0

    # Cancelling again should return 400
    del_res2 = client.delete(f"/api/projects/{p_id}/invitations/{inv_id}")
    assert del_res2.status_code == 400

    # Owner invites someone as ADMIN
    with mock.patch("app.modules.collaborators.service.send_project_invitation_email"):
        _login_user(client, setup["owner"].email)
        admin_inv_res = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "admin_pending@example.com", "role": "ADMIN"},
        )
        admin_inv_id = admin_inv_res.json()["data"]["invitation_id"]

    # Admin tries to revoke an ADMIN invitation -> 403 Forbidden
    _login_user(client, setup["admin"].email)
    admin_del_res = client.delete(f"/api/projects/{p_id}/invitations/{admin_inv_id}")
    assert admin_del_res.status_code == 403

    # Owner can revoke ADMIN invitation -> 200 Allowed
    _login_user(client, setup["owner"].email)
    owner_del_res = client.delete(f"/api/projects/{p_id}/invitations/{admin_inv_id}")
    assert owner_del_res.status_code == 200


# ── 4.5 Tests: Accept & Decline Invitation (Invited User) ──────────────────────

def test_accept_and_decline_invitation(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]

    captured_token = None

    async def fake_send_email(**kwargs):
        nonlocal captured_token
        captured_token = kwargs["invitation_token"]

    with mock.patch("app.modules.collaborators.service.send_project_invitation_email", side_effect=fake_send_email):
        _login_user(client, setup["owner"].email)
        inv_res = client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "joiner@example.com", "role": "EDITOR"},
        )
        assert inv_res.status_code == 201
        assert captured_token is not None

    # Inspect invitation details via GET /api/invitations/{token}
    detail_res = client.get(f"/api/invitations/{captured_token}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["project_name"] == "Collaborative Nest"
    assert detail_res.json()["data"]["invitee_email"] == "joiner@example.com"
    assert detail_res.json()["data"]["role"] == "EDITOR"

    # Create and login the invited user
    joiner_user = _create_test_user(db_session, email="joiner@example.com", username="joiner_dev")
    _login_user(client, joiner_user.email)

    # Wrong user attempts to accept -> 403 Forbidden
    _login_user(client, setup["non_member"].email)
    forbidden_res = client.post(f"/api/invitations/{captured_token}/accept")
    assert forbidden_res.status_code == 403

    # Correct user accepts invitation
    _login_user(client, joiner_user.email)
    accept_res = client.post(f"/api/invitations/{captured_token}/accept")
    assert accept_res.status_code == 200
    assert accept_res.json()["data"]["role"] == "EDITOR"

    # Now joiner is an active member: can list project members
    members_res = client.get(f"/api/projects/{p_id}/members")
    assert members_res.status_code == 200
    members_data = members_res.json()["data"]
    members_list = members_data["members"] if isinstance(members_data, dict) else members_data
    member_emails = {m["email"] for m in members_list}
    assert "joiner@example.com" in member_emails

    # Accepting again -> 400
    re_accept = client.post(f"/api/invitations/{captured_token}/accept")
    assert re_accept.status_code == 400

    # Test Decline flow
    captured_decline_token = None

    async def fake_send_email_decline(**kwargs):
        nonlocal captured_decline_token
        captured_decline_token = kwargs["invitation_token"]

    with mock.patch("app.modules.collaborators.service.send_project_invitation_email", side_effect=fake_send_email_decline):
        _login_user(client, setup["owner"].email)
        client.post(
            f"/api/projects/{p_id}/invitations",
            json={"email": "decliner@example.com", "role": "VIEWER"},
        )

    decliner_user = _create_test_user(db_session, email="decliner@example.com", username="decliner_dev")
    _login_user(client, decliner_user.email)
    decline_res = client.post(f"/api/invitations/{captured_decline_token}/decline")
    assert decline_res.status_code == 200
    assert decline_res.json()["message"] == "Invitation declined."

    # Decliner should not be a member
    mem_check = client.get(f"/api/projects/{p_id}/members")
    assert mem_check.status_code == 404  # Not a member


# ── 4.6 Tests: Update Collaborator Role ───────────────────────────────────────

def test_update_collaborator_role(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]
    editor_user = setup["editor"]
    viewer_user = setup["viewer"]
    admin_user = setup["admin"]
    owner_user = setup["owner"]

    # Owner promotes Editor to Admin
    _login_user(client, owner_user.email)
    patch_res = client.patch(
        f"/api/projects/{p_id}/members/{editor_user.id}",
        json={"role": "ADMIN"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["role"] == "ADMIN"

    # Attempt to change role to OWNER via PATCH -> 403 Forbidden
    res_try_owner = client.patch(
        f"/api/projects/{p_id}/members/{editor_user.id}",
        json={"role": "OWNER"},
    )
    assert res_try_owner.status_code == 403

    # Attempt to modify Owner's role via PATCH -> 403 Forbidden
    res_modify_owner = client.patch(
        f"/api/projects/{p_id}/members/{owner_user.id}",
        json={"role": "EDITOR"},
    )
    assert res_modify_owner.status_code == 403

    # Admin changes Viewer to Editor (Allowed)
    _login_user(client, admin_user.email)
    res_admin_patch = client.patch(
        f"/api/projects/{p_id}/members/{viewer_user.id}",
        json={"role": "EDITOR"},
    )
    assert res_admin_patch.status_code == 200
    assert res_admin_patch.json()["data"]["role"] == "EDITOR"

    # Admin changes Editor back to Viewer using PUT (Allowed)
    res_admin_put = client.put(
        f"/api/projects/{p_id}/members/{viewer_user.id}",
        json={"role": "VIEWER"},
    )
    assert res_admin_put.status_code == 200
    assert res_admin_put.json()["data"]["role"] == "VIEWER"

    # Admin tries to promote Viewer to Admin -> 403 Forbidden
    res_admin_promo = client.patch(
        f"/api/projects/{p_id}/members/{viewer_user.id}",
        json={"role": "ADMIN"},
    )
    assert res_admin_promo.status_code == 403

    # Admin tries to modify another Admin -> 403 Forbidden
    res_admin_mod_admin = client.patch(
        f"/api/projects/{p_id}/members/{editor_user.id}",  # editor was promoted to admin above
        json={"role": "VIEWER"},
    )
    assert res_admin_mod_admin.status_code == 403

    # Viewer/Editor cannot modify roles -> 403
    _login_user(client, viewer_user.email)
    res_viewer_patch = client.patch(
        f"/api/projects/{p_id}/members/{admin_user.id}",
        json={"role": "VIEWER"},
    )
    assert res_viewer_patch.status_code == 403


# ── 4.7 Tests: Remove Collaborator from Project ───────────────────────────────

def test_remove_collaborator_from_project(client, db_session):
    setup = _setup_project_with_roles(client, db_session)
    p_id = setup["project_id"]
    editor_user = setup["editor"]
    viewer_user = setup["viewer"]
    admin_user = setup["admin"]
    owner_user = setup["owner"]

    # Member removes themselves (leave project)
    _login_user(client, viewer_user.email)
    self_leave_res = client.delete(f"/api/projects/{p_id}/members/{viewer_user.id}")
    assert self_leave_res.status_code == 200
    assert self_leave_res.json()["message"] == "Member removed from project."

    # Viewer can no longer access project
    res_check = client.get(f"/api/projects/{p_id}/members")
    assert res_check.status_code == 404

    # Owner cannot leave project directly -> 400
    _login_user(client, owner_user.email)
    owner_leave = client.delete(f"/api/projects/{p_id}/members/{owner_user.id}")
    assert owner_leave.status_code == 400

    # Admin removes Editor (Allowed)
    _login_user(client, admin_user.email)
    admin_remove_editor = client.delete(f"/api/projects/{p_id}/members/{editor_user.id}")
    assert admin_remove_editor.status_code == 200

    # Admin attempts to remove Owner -> 403 Forbidden
    admin_remove_owner = client.delete(f"/api/projects/{p_id}/members/{owner_user.id}")
    assert admin_remove_owner.status_code == 403

    # Owner removes Admin -> 200 Allowed
    _login_user(client, owner_user.email)
    owner_remove_admin = client.delete(f"/api/projects/{p_id}/members/{admin_user.id}")
    assert owner_remove_admin.status_code == 200

    # Check remaining members: only Owner remains
    remaining_res = client.get(f"/api/projects/{p_id}/members")
    assert remaining_res.status_code == 200
    remaining_data = remaining_res.json()["data"]
    remaining_members = remaining_data["members"] if isinstance(remaining_data, dict) else remaining_data
    assert len(remaining_members) == 1
    assert remaining_members[0]["email"] == owner_user.email
