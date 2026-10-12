import uuid
from datetime import timedelta
from unittest import mock
import pytest

from app.core import timezone as tz
from app.core.enums import (
    NotificationActionStatus,
    NotificationCategory,
    NotificationType,
    OwnershipTransferStatus,
    ProjectRole,
)
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.collaborators.models import ProjectOwnershipTransfer
from app.modules.notifications.models import Notification
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


def _setup_project(client, db_session):
    owner = _create_test_user(
        db_session,
        email="owner@example.com",
        username="owner_user",
        first_name="Alice",
        last_name="Owner",
    )
    nominee = _create_test_user(
        db_session,
        email="nominee@example.com",
        username="nominee_user",
        first_name="Bob",
        last_name="Nominee",
    )
    other_member = _create_test_user(
        db_session,
        email="other@example.com",
        username="other_user",
        first_name="Charlie",
        last_name="Viewer",
    )
    outsider = _create_test_user(
        db_session,
        email="outsider@example.com",
        username="outsider_user",
        first_name="Eve",
        last_name="Outsider",
    )

    # Create project by owner
    _login_user(client, owner.email)
    res = client.post("/api/projects", json={"name": "Handshake Project"})
    assert res.status_code == 201, res.text
    p_id = res.json()["data"]["id"]
    p_uuid = uuid.UUID(p_id)

    # Add nominee (as ADMIN) and other_member (as VIEWER)
    m_nominee = ProjectMember(
        project_id=p_uuid,
        user_id=nominee.id,
        role=ProjectRole.ADMIN.value,
        invited_by=owner.id,
    )
    m_other = ProjectMember(
        project_id=p_uuid,
        user_id=other_member.id,
        role=ProjectRole.VIEWER.value,
        invited_by=owner.id,
    )
    db_session.add_all([m_nominee, m_other])
    db_session.commit()

    return {
        "project_id": p_id,
        "p_uuid": p_uuid,
        "owner": owner,
        "nominee": nominee,
        "other_member": other_member,
        "outsider": outsider,
    }


# ── 5.1 Tests: Initiate Ownership Transfer Request ───────────────────────────

def test_initiate_ownership_transfer_success(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    _login_user(client, owner.email)

    with mock.patch("app.modules.collaborators.service.send_ownership_transfer_proposal_email") as mock_email:
        res = client.post(
            f"/api/projects/{p_id}/transfer-ownership",
            json={"nominee_user_id": str(nominee.id)},
        )
        assert res.status_code == 202, res.text
        data = res.json()
        assert data["success"] is True
        assert data["status"] == 202
        assert "Waiting for nominee confirmation" in data["message"]

        payload = data["data"]
        assert payload["project_id"] == p_id
        assert payload["nominee_user_id"] == str(nominee.id)
        assert payload["status"] == OwnershipTransferStatus.PENDING.value
        assert "transfer_id" in payload
        assert "expires_at" in payload

        # Verify DB transfer record
        t_uuid = uuid.UUID(payload["transfer_id"])
        db_transfer = db_session.query(ProjectOwnershipTransfer).filter(ProjectOwnershipTransfer.id == t_uuid).first()
        assert db_transfer is not None
        assert db_transfer.current_owner_id == owner.id
        assert db_transfer.nominee_user_id == nominee.id
        assert db_transfer.status == OwnershipTransferStatus.PENDING.value

        # Verify in-app notification sent to nominee
        notif = (
            db_session.query(Notification)
            .filter(
                Notification.user_id == nominee.id,
                Notification.type == NotificationType.OWNERSHIP_TRANSFER_REQUEST.value,
            )
            .first()
        )
        assert notif is not None
        assert notif.category == NotificationCategory.OWNERSHIP.value
        assert notif.action_status == NotificationActionStatus.PENDING.value
        assert notif.data["transfer_id"] == str(t_uuid)

        # Verify email dispatched
        assert mock_email.called


def test_initiate_ownership_transfer_validation(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    owner = setup["owner"]
    nominee = setup["nominee"]
    outsider = setup["outsider"]

    _login_user(client, owner.email)

    # 1. Cannot transfer to self (BR-TRANS-01)
    res_self = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(owner.id)},
    )
    assert res_self.status_code == 400
    assert "Cannot transfer project ownership to yourself" in res_self.text

    # 2. Cannot transfer to non-member outsider (BR-TRANS-02)
    res_outsider = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(outsider.id)},
    )
    assert res_outsider.status_code == 400
    assert "not an active member" in res_outsider.text

    # 3. Cannot transfer to non-existent user
    fake_id = str(uuid.uuid4())
    res_fake = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": fake_id},
    )
    assert res_fake.status_code == 400
    assert "does not exist" in res_fake.text

    # 4. Initiate successfully once
    res_init = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_init.status_code == 202

    # 5. Conflict when already pending
    res_conflict = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_conflict.status_code == 409
    assert "already pending" in res_conflict.text


def test_initiate_ownership_transfer_rbac(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    nominee = setup["nominee"]
    other_member = setup["other_member"]
    outsider = setup["outsider"]

    # Admin cannot initiate
    _login_user(client, nominee.email)
    res_admin = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(other_member.id)},
    )
    assert res_admin.status_code == 403

    # Viewer cannot initiate
    _login_user(client, other_member.email)
    res_viewer = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_viewer.status_code == 403

    # Outsider cannot initiate (404 isolation)
    _login_user(client, outsider.email)
    res_outsider = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_outsider.status_code == 404


# ── 5.2 Tests: Get Pending Transfer Request Status ────────────────────────────

def test_get_pending_transfer_status(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    owner = setup["owner"]
    nominee = setup["nominee"]
    other_member = setup["other_member"]

    # Before initiation: null
    _login_user(client, owner.email)
    res_empty = client.get(f"/api/projects/{p_id}/transfer-ownership")
    assert res_empty.status_code == 200
    assert res_empty.json()["data"] is None

    # Initiate proposal
    res_init = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_init.status_code == 202

    # Owner can get details
    res_owner = client.get(f"/api/projects/{p_id}/transfer-ownership")
    assert res_owner.status_code == 200
    data_owner = res_owner.json()["data"]
    assert data_owner["status"] == "PENDING"
    assert data_owner["nominee"]["email"] == nominee.email

    # Nominee can get details
    _login_user(client, nominee.email)
    res_nominee = client.get(f"/api/projects/{p_id}/transfer-ownership")
    assert res_nominee.status_code == 200
    data_nominee = res_nominee.json()["data"]
    assert data_nominee["status"] == "PENDING"
    assert data_nominee["current_owner"]["email"] == owner.email

    # Unrelated member is forbidden (403)
    _login_user(client, other_member.email)
    res_other = client.get(f"/api/projects/{p_id}/transfer-ownership")
    assert res_other.status_code == 403


# ── 5.3 Tests: Accept Ownership Transfer (Step 2) ─────────────────────────────

def test_accept_ownership_transfer_success(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    p_uuid = setup["p_uuid"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    # Owner initiates
    _login_user(client, owner.email)
    res_init = client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )
    assert res_init.status_code == 202

    # Nominee accepts
    _login_user(client, nominee.email)
    with mock.patch("app.modules.collaborators.service.send_ownership_transfer_completed_email") as mock_email:
        res_accept = client.post(f"/api/projects/{p_id}/transfer-ownership/accept")
        assert res_accept.status_code == 200, res_accept.text
        data = res_accept.json()
        assert data["success"] is True
        assert "Ownership successfully transferred" in data["message"]
        assert data["data"]["project_id"] == p_id
        assert data["data"]["new_owner_id"] == str(nominee.id)
        assert data["data"]["previous_owner_role"] == "ADMIN"

        # Verify DB updates (Atomic transaction)
        project = db_session.query(Project).filter(Project.id == p_uuid).first()
        assert project.owner_id == nominee.id

        m_nominee = db_session.query(ProjectMember).filter(
            ProjectMember.project_id == p_uuid,
            ProjectMember.user_id == nominee.id,
        ).first()
        assert m_nominee.role == ProjectRole.OWNER.value

        m_old_owner = db_session.query(ProjectMember).filter(
            ProjectMember.project_id == p_uuid,
            ProjectMember.user_id == owner.id,
        ).first()
        assert m_old_owner.role == ProjectRole.ADMIN.value

        # Verify transfer record marked ACCEPTED
        transfer = db_session.query(ProjectOwnershipTransfer).filter(
            ProjectOwnershipTransfer.project_id == p_uuid,
        ).first()
        assert transfer.status == OwnershipTransferStatus.ACCEPTED.value
        assert transfer.responded_at is not None

        # Verify notification sent to old owner
        notif = (
            db_session.query(Notification)
            .filter(
                Notification.user_id == owner.id,
                Notification.type == NotificationType.OWNERSHIP_TRANSFER_ACCEPTED.value,
            )
            .first()
        )
        assert notif is not None
        assert notif.actor_id == nominee.id

        # Verify completion email dispatched
        assert mock_email.called


def test_accept_ownership_transfer_forbidden_for_non_nominee(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    owner = setup["owner"]
    nominee = setup["nominee"]
    other_member = setup["other_member"]

    # Owner initiates
    _login_user(client, owner.email)
    client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )

    # Owner tries to accept -> 404 (no pending transfer for owner)
    res_owner = client.post(f"/api/projects/{p_id}/transfer-ownership/accept")
    assert res_owner.status_code == 404

    # Other member tries to accept -> 404
    _login_user(client, other_member.email)
    res_other = client.post(f"/api/projects/{p_id}/transfer-ownership/accept")
    assert res_other.status_code == 404


def test_accept_expired_ownership_transfer(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    p_uuid = setup["p_uuid"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    # Owner initiates
    _login_user(client, owner.email)
    client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )

    # Manually backdate expiration to simulate expired request
    transfer = db_session.query(ProjectOwnershipTransfer).filter(
        ProjectOwnershipTransfer.project_id == p_uuid,
    ).first()
    transfer.expires_at = tz.now() - timedelta(hours=1)
    db_session.commit()

    # Nominee tries to accept -> 400 Bad Request
    _login_user(client, nominee.email)
    res = client.post(f"/api/projects/{p_id}/transfer-ownership/accept")
    assert res.status_code == 400
    assert "expired" in res.text

    # Verify status changed to EXPIRED
    db_session.refresh(transfer)
    assert transfer.status == OwnershipTransferStatus.EXPIRED.value


# ── 5.4 Tests: Reject Ownership Transfer ──────────────────────────────────────

def test_reject_ownership_transfer_success(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    p_uuid = setup["p_uuid"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    # Owner initiates
    _login_user(client, owner.email)
    client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )

    # Nominee rejects
    _login_user(client, nominee.email)
    res_reject = client.post(f"/api/projects/{p_id}/transfer-ownership/reject")
    assert res_reject.status_code == 200
    assert res_reject.json()["success"] is True

    # Verify DB transfer status
    transfer = db_session.query(ProjectOwnershipTransfer).filter(
        ProjectOwnershipTransfer.project_id == p_uuid,
    ).first()
    assert transfer.status == OwnershipTransferStatus.REJECTED.value
    assert transfer.responded_at is not None

    # Verify owner received rejection notification
    notif = (
        db_session.query(Notification)
        .filter(
            Notification.user_id == owner.id,
            Notification.type == NotificationType.OWNERSHIP_TRANSFER_REJECTED.value,
        )
        .first()
    )
    assert notif is not None
    assert notif.actor_id == nominee.id


# ── 5.5 Tests: Cancel Ownership Transfer Proposal ─────────────────────────────

def test_cancel_ownership_transfer_success(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    p_uuid = setup["p_uuid"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    # Owner initiates
    _login_user(client, owner.email)
    client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )

    # Owner cancels
    res_cancel = client.delete(f"/api/projects/{p_id}/transfer-ownership")
    assert res_cancel.status_code == 200
    assert res_cancel.json()["success"] is True

    # Verify DB transfer status
    transfer = db_session.query(ProjectOwnershipTransfer).filter(
        ProjectOwnershipTransfer.project_id == p_uuid,
    ).first()
    assert transfer.status == OwnershipTransferStatus.CANCELLED.value

    # Cancelling again returns 404 (none pending)
    res_cancel2 = client.delete(f"/api/projects/{p_id}/transfer-ownership")
    assert res_cancel2.status_code == 404


def test_cancel_ownership_transfer_rbac(client, db_session):
    setup = _setup_project(client, db_session)
    p_id = setup["project_id"]
    owner = setup["owner"]
    nominee = setup["nominee"]

    # Owner initiates
    _login_user(client, owner.email)
    client.post(
        f"/api/projects/{p_id}/transfer-ownership",
        json={"nominee_user_id": str(nominee.id)},
    )

    # Nominee tries to cancel -> 403 Forbidden (requires OWNER)
    _login_user(client, nominee.email)
    res_nominee = client.delete(f"/api/projects/{p_id}/transfer-ownership")
    assert res_nominee.status_code == 403
