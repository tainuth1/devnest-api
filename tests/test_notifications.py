import uuid
from unittest import mock
import pytest

from app.core.enums import (
    NotificationActionStatus,
    NotificationCategory,
    NotificationType,
    ProjectRole,
)
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService
from app.modules.projects.models import Project, ProjectMember


def _create_user(
    db_session,
    email="testuser@example.com",
    username="testuser",
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


def _login(client, email="testuser@example.com", password="DevPassword123!"):
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


def test_notification_service_send_and_get_list(client, db_session):
    user = _create_user(db_session, email="alice@example.com", username="alice")
    sender = _create_user(db_session, email="bob@example.com", username="bob")

    # Dispatch notification
    notif = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        actor_id=sender.id,
        type=NotificationType.PROJECT_INVITATION.value,
        category=NotificationCategory.COLLABORATION.value,
        title="Project Invitation",
        message="Bob invited you to join Dev Nest as EDITOR.",
        link_url="/workspace/projects/proj123/team",
        data={"role": "EDITOR", "invitation_token": "token_abc"},
    )
    assert notif.id is not None
    assert notif.is_read is False
    assert notif.link_url == "/workspace/projects/proj123/team"

    # Log in as Alice and fetch notifications list
    _login(client, alice_email := "alice@example.com")
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["id"] == str(notif.id)
    assert item["title"] == "Project Invitation"
    assert item["link_url"] == "/workspace/projects/proj123/team"
    assert item["data"]["role"] == "EDITOR"
    assert item["actor"]["username"] == "bob"
    assert data["unread_count"] == 1


def test_get_unread_count(client, db_session):
    user = _create_user(db_session, email="carol@example.com", username="carol")

    # Send 3 notifications
    n1 = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.SECURITY_ALERT.value,
        category=NotificationCategory.SECURITY.value,
        title="New Login",
        message="New login from Chrome.",
    )
    n2 = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.BACKUP_COMPLETED.value,
        category=NotificationCategory.BACKUP.value,
        title="Backup Succeeded",
        message="Daily backup completed.",
    )
    n3 = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.AI_PROPOSAL_READY.value,
        category=NotificationCategory.AI.value,
        title="AI Proposal Ready",
        message="AI generated schema diff.",
    )

    _login(client, "carol@example.com")

    # Unread count should be 3
    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["data"]["unread_count"] == 3

    # Mark n1 as read
    NotificationService.mark_as_read(db_session, user.id, n1.id)

    resp = client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["data"]["unread_count"] == 2


def test_mark_single_notification_as_read(client, db_session):
    user = _create_user(db_session, email="dave@example.com", username="dave")
    notif = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.MEMBER_ROLE_CHANGED.value,
        category=NotificationCategory.COLLABORATION.value,
        title="Role Updated",
        message="Your role was updated to ADMIN.",
        link_url="/workspace/projects/test/team",
    )

    _login(client, "dave@example.com")
    resp = client.patch(f"/api/notifications/{notif.id}/read")
    assert resp.status_code == 200
    assert resp.json()["data"]["is_read"] is True
    assert resp.json()["data"]["read_at"] is not None

    # Check unread count
    resp2 = client.get("/api/notifications/unread-count")
    assert resp2.json()["data"]["unread_count"] == 0


def test_mark_all_notifications_as_read(client, db_session):
    user = _create_user(db_session, email="eve@example.com", username="eve")
    for i in range(4):
        NotificationService.send_to_user(
            db=db_session,
            user_id=user.id,
            type=NotificationType.SYSTEM_ANNOUNCEMENT.value,
            category=NotificationCategory.SYSTEM.value,
            title=f"Announcement {i}",
            message=f"Message {i}",
        )

    _login(client, "eve@example.com")
    resp = client.patch("/api/notifications/mark-all-read")
    assert resp.status_code == 200
    assert resp.json()["data"]["updated_count"] == 4

    resp_count = client.get("/api/notifications/unread-count")
    assert resp_count.json()["data"]["unread_count"] == 0


def test_update_action_status(client, db_session):
    user = _create_user(db_session, email="frank@example.com", username="frank")
    notif = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.PROJECT_INVITATION.value,
        category=NotificationCategory.COLLABORATION.value,
        title="Invite",
        message="Invite to join project",
        data={"invitation_token": "xyz123"},
    )

    _login(client, "frank@example.com")
    resp = client.patch(
        f"/api/notifications/{notif.id}/action",
        json={"action": "ACCEPTED"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["action_status"] == "ACCEPTED"
    assert data["is_read"] is True


def test_delete_notification(client, db_session):
    user = _create_user(db_session, email="grace@example.com", username="grace")
    notif = NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.SYSTEM_ANNOUNCEMENT.value,
        category=NotificationCategory.SYSTEM.value,
        title="Dismissible notice",
        message="Notice text",
    )

    _login(client, "grace@example.com")
    resp = client.delete(f"/api/notifications/{notif.id}")
    assert resp.status_code == 200

    # Ensure it no longer appears in notifications list
    resp_list = client.get("/api/notifications")
    assert len(resp_list.json()["data"]["items"]) == 0


def test_user_isolation(client, db_session):
    user1 = _create_user(db_session, email="u1@example.com", username="user1")
    user2 = _create_user(db_session, email="u2@example.com", username="user2")

    notif_u2 = NotificationService.send_to_user(
        db=db_session,
        user_id=user2.id,
        type=NotificationType.SECURITY_ALERT.value,
        category=NotificationCategory.SECURITY.value,
        title="User 2 Secret",
        message="Secret message",
    )

    _login(client, "u1@example.com")

    # User 1 cannot see User 2's notifications
    resp_list = client.get("/api/notifications")
    assert len(resp_list.json()["data"]["items"]) == 0

    # User 1 cannot mark User 2's notification as read
    resp_read = client.patch(f"/api/notifications/{notif_u2.id}/read")
    assert resp_read.status_code == 404

    # User 1 cannot delete User 2's notification
    resp_del = client.delete(f"/api/notifications/{notif_u2.id}")
    assert resp_del.status_code == 404


def test_filters_by_category_and_type(client, db_session):
    user = _create_user(db_session, email="hank@example.com", username="hank")

    NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.PROJECT_INVITATION.value,
        category=NotificationCategory.COLLABORATION.value,
        title="Invite",
        message="Invite msg",
    )
    NotificationService.send_to_user(
        db=db_session,
        user_id=user.id,
        type=NotificationType.BACKUP_FAILED.value,
        category=NotificationCategory.BACKUP.value,
        title="Backup Failed",
        message="Backup failed msg",
    )

    _login(client, "hank@example.com")

    # Filter by category
    resp = client.get("/api/notifications?category=COLLABORATION")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["category"] == "COLLABORATION"

    # Filter by type
    resp_type = client.get("/api/notifications?type=BACKUP_FAILED")
    assert resp_type.status_code == 200
    items_type = resp_type.json()["data"]["items"]
    assert len(items_type) == 1
    assert items_type[0]["type"] == "BACKUP_FAILED"


def test_broadcast_to_project_members(db_session):
    owner = _create_user(db_session, email="powner@example.com", username="powner")
    m1 = _create_user(db_session, email="pm1@example.com", username="pm1")
    m2 = _create_user(db_session, email="pm2@example.com", username="pm2")

    project = Project(
        name="Team Workspace",
        slug="team-workspace",
        project_code="teamspace1234567890",
        owner_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    pm_owner = ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER.value)
    pm1 = ProjectMember(project_id=project.id, user_id=m1.id, role=ProjectRole.EDITOR.value)
    pm2 = ProjectMember(project_id=project.id, user_id=m2.id, role=ProjectRole.VIEWER.value)
    db_session.add_all([pm_owner, pm1, pm2])
    db_session.commit()

    # Broadcast excluding owner
    count = NotificationService.send_to_project_members(
        db=db_session,
        project_id=project.id,
        actor_id=owner.id,
        exclude_user_ids=[owner.id],
        type=NotificationType.SYSTEM_ANNOUNCEMENT.value,
        category=NotificationCategory.SYSTEM.value,
        title="Meeting Soon",
        message="Architecture sync at 3pm.",
    )
    assert count == 2

    # Verify m1 and m2 received it, owner did not
    assert NotificationService.get_unread_count(db_session, owner.id) == 0
    assert NotificationService.get_unread_count(db_session, m1.id) == 1
    assert NotificationService.get_unread_count(db_session, m2.id) == 1


@mock.patch("app.modules.collaborators.service.send_project_invitation_email")
def test_integration_invitation_dispatches_in_app_notification(mock_email, client, db_session):
    mock_email.return_value = True

    # Project owner
    owner = _create_user(db_session, email="lead@example.com", username="lead")
    # Registered developer to invite
    dev = _create_user(db_session, email="invited_dev@example.com", username="invited_dev")

    project = Project(
        name="Alpha Project",
        slug="alpha-project",
        project_code="alpha123456789012345",
        owner_id=owner.id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    pm_owner = ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.OWNER.value)
    db_session.add(pm_owner)
    db_session.commit()

    # Lead logs in and invites invited_dev
    _login(client, "lead@example.com")
    invite_resp = client.post(
        f"/api/projects/{project.project_code}/invitations",
        json={"email": "invited_dev@example.com", "role": "EDITOR"},
    )
    assert invite_resp.status_code == 201

    # Now invited_dev logs in and checks notifications
    _login(client, "invited_dev@example.com")
    notif_resp = client.get("/api/notifications")
    assert notif_resp.status_code == 200
    items = notif_resp.json()["data"]["items"]
    assert len(items) == 1
    notif_item = items[0]
    assert notif_item["type"] == "PROJECT_INVITATION"
    assert notif_item["category"] == "COLLABORATION"
    assert notif_item["link_url"] == f"/workspace/projects/{project.project_code}/team"
    assert notif_item["data"]["role"] == "EDITOR"
    assert notif_item["actor"]["username"] == "lead"
