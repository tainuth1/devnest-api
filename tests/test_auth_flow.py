import unittest.mock as mock
import pytest
from app.modules.auth.models import User, PendingRegistration, UserSession, PasswordReset
from app.core.security import hash_password, hash_session_token
from app.core.otp import hash_otp


def test_register_flow_and_verify_otp(client, db_session):
    """Test phase 1 (registration) and phase 2 (OTP verification)."""
    # 1. Registration Phase
    with mock.patch("app.modules.auth.service.send_otp_email") as mock_email:
        mock_email.return_value = None
        response = client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "testuser@example.com",
                "password": "ComplexP@ssw0rd2026!",
                "website": "",
                "phone_confirm": "",
            },
        )
        assert response.status_code == 200, response.json()
        assert response.json()["success"] is True

    # Inspect pending registration row in DB
    pending = db_session.query(PendingRegistration).filter_by(email="testuser@example.com").first()
    assert pending is not None
    assert pending.username == "testuser"

    # Set known OTP hash for verification test
    pending.otp_hash = hash_otp("123456")
    db_session.commit()

    # 2. OTP Verification Phase
    verify_resp = client.post(
        "/api/auth/verify-otp",
        json={
            "email": "testuser@example.com",
            "otp_code": "123456",
            "website": "",
            "phone_confirm": "",
        },
    )
    assert verify_resp.status_code == 201, verify_resp.json()
    assert verify_resp.json()["success"] is True

    # User should now be active in User table
    user = db_session.query(User).filter_by(email="testuser@example.com").first()
    assert user is not None
    assert user.username == "testuser"


def test_login_success_and_logout(client, db_session):
    """Test successful user login, session cookie creation, and logout."""
    user = User(
        username="loginuser",
        email="loginuser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "loginuser@example.com",
            "password": "Secret123!",
            "website": "",
            "phone_confirm": "",
        },
    )
    assert login_resp.status_code == 200, login_resp.json()
    data = login_resp.json()["data"]
    assert "user" in data
    assert data["user"]["email"] == "loginuser@example.com"

    # Session cookie should be set
    session_cookie = login_resp.cookies.get("session_id")
    assert session_cookie is not None

    # Session record should be stored in DB with hashed token
    hashed_token = hash_session_token(session_cookie)
    db_session_record = db_session.query(UserSession).filter_by(token_hash=hashed_token).first()
    assert db_session_record is not None
    assert db_session_record.user_id == user.id
    assert db_session_record.revoked is False

    # Test /api/auth/me using session cookie
    me_resp = client.get(
        "/api/auth/me",
        cookies={"session_id": session_cookie},
    )
    assert me_resp.status_code == 200, me_resp.json()
    assert me_resp.json()["data"]["email"] == "loginuser@example.com"

    # Test /api/auth/logout
    logout_resp = client.post(
        "/api/auth/logout",
        cookies={"session_id": session_cookie},
    )
    assert logout_resp.status_code == 200

    # DB session should now be revoked
    db_session.refresh(db_session_record)
    assert db_session_record.revoked is True


def test_login_remember_me_extends_session(client, db_session):
    """Test that remember_me=true creates a session with 30-day expiry."""
    from datetime import timedelta
    from app.core import timezone as tz

    user = User(
        username="rememberuser",
        email="rememberuser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "rememberuser@example.com",
            "password": "Secret123!",
            "remember_me": True,
        },
    )
    assert login_resp.status_code == 200, login_resp.json()
    session_cookie = login_resp.cookies.get("session_id")
    assert session_cookie is not None

    hashed_token = hash_session_token(session_cookie)
    db_session_record = db_session.query(UserSession).filter_by(token_hash=hashed_token).first()
    assert db_session_record is not None
    assert db_session_record.remember_me is True

    # Expiry should be approximately 30 days from now
    expected_expiry = tz.now() + timedelta(days=30)
    actual_expiry = tz.ensure_tz_aware(db_session_record.expires_at)
    diff = abs((actual_expiry - expected_expiry).total_seconds())
    assert diff < 60, f"Expected ~30 day expiry, got diff of {diff}s"


def test_login_default_session_is_7_days(client, db_session):
    """Test that remember_me=false (default) creates a session with 7-day expiry."""
    from datetime import timedelta
    from app.core import timezone as tz

    user = User(
        username="defaultsess",
        email="defaultsess@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "defaultsess@example.com",
            "password": "Secret123!",
        },
    )
    assert login_resp.status_code == 200, login_resp.json()
    session_cookie = login_resp.cookies.get("session_id")

    hashed_token = hash_session_token(session_cookie)
    db_session_record = db_session.query(UserSession).filter_by(token_hash=hashed_token).first()
    assert db_session_record is not None
    assert db_session_record.remember_me is False

    # Expiry should be approximately 7 days from now
    expected_expiry = tz.now() + timedelta(days=7)
    actual_expiry = tz.ensure_tz_aware(db_session_record.expires_at)
    diff = abs((actual_expiry - expected_expiry).total_seconds())
    assert diff < 60, f"Expected ~7 day expiry, got diff of {diff}s"


def test_account_lockout_trigger(client, db_session):
    """Test account lockout after 5 consecutive failed login attempts."""
    user = User(
        username="lockoutuser",
        email="lockoutuser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    # Fail 4 attempts
    for _ in range(4):
        resp = client.post(
            "/api/auth/login",
            json={
                "login_id": "lockoutuser@example.com",
                "password": "WrongPassword123!",
            },
        )
        assert resp.status_code == 401

    # 5th attempt triggers lockout
    resp5 = client.post(
        "/api/auth/login",
        json={
            "login_id": "lockoutuser@example.com",
            "password": "WrongPassword123!",
        },
    )
    assert resp5.status_code == 401
    assert "temporarily locked" in resp5.json()["message"]

    db_session.refresh(user)
    assert user.is_locked_out is True


def test_unauthenticated_access_denied(client, db_session):
    """Test that /api/auth/me returns 401 without a session cookie."""
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 401


def test_revoked_session_denied(client, db_session):
    """Test that a revoked session cannot authenticate subsequent requests."""
    user = User(
        username="revokeduser",
        email="revokeduser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "revokeduser@example.com",
            "password": "Secret123!",
        },
    )
    session_cookie = login_resp.cookies.get("session_id")

    # Logout revokes the session
    client.post("/api/auth/logout", cookies={"session_id": session_cookie})

    # Subsequent request with the revoked cookie should be denied
    me_resp = client.get("/api/auth/me", cookies={"session_id": session_cookie})
    assert me_resp.status_code == 401


def test_password_reset_flow(client, db_session):
    """Test password reset via OTP."""
    user = User(
        username="resetuser",
        email="resetuser@example.com",
        password=hash_password("OldPassword123!"),
    )
    db_session.add(user)
    db_session.commit()

    # 1. Forgot password request
    with mock.patch("app.modules.auth.service.send_password_reset_otp_email") as mock_email:
        mock_email.return_value = None
        fp_resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "resetuser@example.com"},
        )
        assert fp_resp.status_code == 200

    reset_rec = db_session.query(PasswordReset).filter_by(email="resetuser@example.com").first()
    assert reset_rec is not None
    reset_rec.otp_hash = hash_otp("654321")
    db_session.commit()

    # 2. Reset password using OTP
    reset_resp = client.post(
        "/api/auth/reset-password",
        json={
            "email": "resetuser@example.com",
            "otp_code": "654321",
            "new_password": "NewPassword123!",
        },
    )
    assert reset_resp.status_code == 200

    # 3. Verify login with new password succeeds
    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "resetuser@example.com",
            "password": "NewPassword123!",
        },
    )
    assert login_resp.status_code == 200


def test_update_avatar_no_user_id_needed(client, db_session):
    """Test updating user avatar using session identity (no user ID in request)."""
    user = User(
        username="avataruser",
        email="avataruser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    # Login to get session cookie
    login_resp = client.post(
        "/api/auth/login",
        json={"login_id": "avataruser@example.com", "password": "Secret123!"},
    )
    assert login_resp.status_code == 200
    session_cookie = login_resp.cookies.get("session_id")

    # Update avatar with session cookie
    avatar_resp = client.post(
        "/api/auth/me/avatar",
        json={"avatar_url": "https://example.com/avatar_test.png"},
        cookies={"session_id": session_cookie},
    )
    assert avatar_resp.status_code == 200, avatar_resp.json()
    assert avatar_resp.json()["data"]["avatar_url"] == "https://example.com/avatar_test.png"

    # Verify /me returns updated avatar
    me_resp = client.get("/api/auth/me", cookies={"session_id": session_cookie})
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["avatar_url"] == "https://example.com/avatar_test.png"

    # Verify updating avatar_url via PUT /api/auth/me (reproduces previous HttpUrl adapter bug)
    update_profile_resp = client.put(
        "/api/auth/me",
        json={"avatar_url": "https://example.com/new_avatar.png"},
        cookies={"session_id": session_cookie},
    )
    assert update_profile_resp.status_code == 200, update_profile_resp.json()
    assert update_profile_resp.json()["data"]["avatar_url"] == "https://example.com/new_avatar.png"

    # Verify resetting avatar_url to null/empty via PATCH /api/auth/me
    patch_profile_resp = client.patch(
        "/api/auth/me",
        json={"avatar_url": None},
        cookies={"session_id": session_cookie},
    )
    assert patch_profile_resp.status_code == 200, patch_profile_resp.json()
    assert patch_profile_resp.json()["data"]["avatar_url"] is None


def test_revoke_specific_session(client, db_session):
    """Test revoking a specific session by ID while keeping other sessions active."""
    user = User(
        username="sessionuser",
        email="sessionuser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    # Session 1 (Device A)
    resp1 = client.post(
        "/api/auth/login",
        json={"login_id": "sessionuser@example.com", "password": "Secret123!"},
    )
    cookie1 = resp1.cookies.get("session_id")

    # Session 2 (Device B)
    resp2 = client.post(
        "/api/auth/login",
        json={"login_id": "sessionuser@example.com", "password": "Secret123!"},
    )
    cookie2 = resp2.cookies.get("session_id")

    # List sessions using Session 1
    list_resp = client.get("/api/auth/sessions", cookies={"session_id": cookie1})
    assert list_resp.status_code == 200
    sessions = list_resp.json()["data"]
    assert len(sessions) == 2

    # Identify Session 2 (not current for cookie1)
    sess2_id = [s["id"] for s in sessions if not s["is_current"]][0]

    # Revoke Session 2 using Session 1
    del_resp = client.delete(f"/api/auth/sessions/{sess2_id}", cookies={"session_id": cookie1})
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["is_current"] is False

    # Verify Session 1 is STILL valid
    me1 = client.get("/api/auth/me", cookies={"session_id": cookie1})
    assert me1.status_code == 200

    # Verify Session 2 is now REVOKED (401)
    me2 = client.get("/api/auth/me", cookies={"session_id": cookie2})
    assert me2.status_code == 401


def test_revoke_all_sessions(client, db_session):
    """Test revoking all sessions, including the current user's session."""
    user = User(
        username="alluser",
        email="alluser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    # Create two sessions
    resp1 = client.post("/api/auth/login", json={"login_id": "alluser@example.com", "password": "Secret123!"})
    cookie1 = resp1.cookies.get("session_id")
    resp2 = client.post("/api/auth/login", json={"login_id": "alluser@example.com", "password": "Secret123!"})
    cookie2 = resp2.cookies.get("session_id")

    # Revoke all sessions from Session 2
    revoke_all_resp = client.delete("/api/auth/sessions", cookies={"session_id": cookie2})
    assert revoke_all_resp.status_code == 200
    assert revoke_all_resp.json()["data"]["revoked_count"] >= 2

    # Both Session 1 and Session 2 must now be 401
    assert client.get("/api/auth/me", cookies={"session_id": cookie1}).status_code == 401
    assert client.get("/api/auth/me", cookies={"session_id": cookie2}).status_code == 401


def test_revoke_other_user_session_forbidden(client, db_session):
    """Test that a user cannot revoke another user's session (403 Forbidden)."""
    user_a = User(username="user_a", email="usera@example.com", password=hash_password("Secret123!"))
    user_b = User(username="user_b", email="userb@example.com", password=hash_password("Secret123!"))
    db_session.add_all([user_a, user_b])
    db_session.commit()

    # User A login
    resp_a = client.post("/api/auth/login", json={"login_id": "usera@example.com", "password": "Secret123!"})
    cookie_a = resp_a.cookies.get("session_id")

    # User B login
    resp_b = client.post("/api/auth/login", json={"login_id": "userb@example.com", "password": "Secret123!"})
    cookie_b = resp_b.cookies.get("session_id")

    # Get User B's session ID
    list_b = client.get("/api/auth/sessions", cookies={"session_id": cookie_b})
    sess_b_id = list_b.json()["data"][0]["id"]

    # User A attempts to revoke User B's session -> 403 Forbidden
    del_resp = client.delete(f"/api/auth/sessions/{sess_b_id}", cookies={"session_id": cookie_a})
    assert del_resp.status_code == 403

