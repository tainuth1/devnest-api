import unittest.mock as mock
import pytest
from app.modules.auth.models import User, PendingRegistration, RefreshToken, PasswordReset
from app.core.security import hash_password, hash_refresh_token
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
    """Test successful user login, token retrieval, and logout."""
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
    assert "access_token" in data["tokens"]
    access_token = data["tokens"]["access_token"]
    refresh_cookie = login_resp.cookies.get("refresh_token")
    assert refresh_cookie is not None

    # Check refresh_tokens table in DB: token stored should be hashed
    hashed_cookie = hash_refresh_token(refresh_cookie)
    db_token = db_session.query(RefreshToken).filter_by(token=hashed_cookie).first()
    assert db_token is not None
    assert db_token.user_id == user.id

    # Test /api/auth/me using Access Token
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200, me_resp.json()
    assert me_resp.json()["data"]["email"] == "loginuser@example.com"

    # Test /api/auth/logout
    logout_resp = client.post(
        "/api/auth/logout",
        cookies={"refresh_token": refresh_cookie},
    )
    assert logout_resp.status_code == 200

    # DB token should now be revoked
    db_session.refresh(db_token)
    assert db_token.revoked is True


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


def test_token_refresh_and_revocation_on_reuse(client, db_session):
    """Test refresh token rotation and revocation of all sessions on stolen token reuse."""
    user = User(
        username="refreshuser",
        email="refreshuser@example.com",
        password=hash_password("Secret123!"),
    )
    db_session.add(user)
    db_session.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={
            "login_id": "refreshuser@example.com",
            "password": "Secret123!",
        },
    )
    first_refresh_cookie = login_resp.cookies.get("refresh_token")

    # Refresh tokens -> should rotate to a new refresh token
    refresh_resp = client.post(
        "/api/auth/refresh",
        cookies={"refresh_token": first_refresh_cookie},
    )
    assert refresh_resp.status_code == 200, refresh_resp.json()
    second_refresh_cookie = refresh_resp.cookies.get("refresh_token")
    assert second_refresh_cookie != first_refresh_cookie

    # Attempting to reuse the revoked first_refresh_cookie triggers theft detection
    reuse_resp = client.post(
        "/api/auth/refresh",
        cookies={"refresh_token": first_refresh_cookie},
    )
    assert reuse_resp.status_code == 401
    assert "Session security alert" in reuse_resp.json()["message"]

    # Validating that second_refresh_cookie was also revoked due to security alert
    all_tokens = db_session.query(RefreshToken).filter_by(user_id=user.id).all()
    assert len(all_tokens) == 2
    assert all(t.revoked for t in all_tokens)


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
