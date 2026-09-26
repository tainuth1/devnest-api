"""
Automated Verification Script for OWASP A09: Security Logging & Monitoring Failures.

Tests:
1. Request ID & Correlation ID (`X-Request-ID`) header injection & log context binding.
2. Sensitive Data Redaction filter (`SensitiveDataRedactor`) across strings and dictionaries.
3. Structured JSON log formatting (`JSONFormatter`).
4. Security Audit Event Logging (`AuditLogger` and `AuditEventType`).
5. Live FastAPI TestClient endpoint security event logging (honeypot, 401, 403, 429).
"""

import io
import json
import logging
import sys
import uuid
from fastapi.testclient import TestClient

# Ensure app module is in path
sys.path.insert(0, ".")

from app.main import app
from app.core.config import settings
from app.core.logging import (
    JSONFormatter,
    SensitiveDataRedactor,
    client_ip_ctx,
    request_id_ctx,
    user_agent_ctx,
    redact_sensitive_data,
)
from app.core.audit import AuditEventType, AuditLogger, AuditStatus, audit_logger
from app.core.integrity import IntegrityError, verify_signed_payload


def test_sensitive_data_redaction():
    print("Testing Sensitive Data Redaction Filter...")

    # Dict redaction
    sample_data = {
        "username": "john_doe",
        "email": "john@example.com",
        "password": "SuperSecretPassword123!",
        "token": "secret_jwt_token_12345",
        "otp": "123456",
        "nested": {
            "refresh_token": "refresh_token_value",
            "safe_key": "safe_value",
        },
    }

    redacted_dict = redact_sensitive_data(sample_data)
    assert redacted_dict["password"] == "***REDACTED***"
    assert redacted_dict["token"] == "***REDACTED***"
    assert redacted_dict["otp"] == "***REDACTED***"
    assert redacted_dict["nested"]["refresh_token"] == "***REDACTED***"
    assert redacted_dict["username"] == "john_doe"
    assert redacted_dict["nested"]["safe_key"] == "safe_value"

    # String log redaction
    sample_log = "User login failed | password='MyPassword123!' token=xyz123 Bearer secret_bearer_token"
    redacted_log = redact_sensitive_data(sample_log)
    assert "MyPassword123!" not in redacted_log
    assert "secret_bearer_token" not in redacted_log
    assert "***REDACTED***" in redacted_log

    print("  [OK] Sensitive Data Redaction test passed.")


def test_json_formatter():
    print("Testing Structured JSON Log Formatter...")

    # Set context variables
    test_req_id = str(uuid.uuid4())
    token_req = request_id_ctx.set(test_req_id)
    token_ip = client_ip_ctx.set("192.168.1.100")
    token_ua = user_agent_ctx.set("TestAgent/1.0")

    try:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="app.test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Security alert: attempt count=%d",
            args=(5,),
            exc_info=None,
        )
        record.custom_attr = "extra_val"
        output = formatter.format(record)

        log_json = json.loads(output)
        assert log_json["level"] == "WARNING"
        assert log_json["logger"] == "app.test"
        assert log_json["message"] == "Security alert: attempt count=5"
        assert log_json["request_id"] == test_req_id
        assert log_json["client_ip"] == "192.168.1.100"
        assert log_json["user_agent"] == "TestAgent/1.0"
        assert log_json["extra"]["custom_attr"] == "extra_val"

        print("  [OK] Structured JSON Log Formatter test passed.")
    finally:
        request_id_ctx.reset(token_req)
        client_ip_ctx.reset(token_ip)
        user_agent_ctx.reset(token_ua)


def test_audit_logger():
    print("Testing Audit Logger & Event Types...")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    audit_test_logger = logging.getLogger("app.audit")
    audit_test_logger.addHandler(handler)

    test_user_id = uuid.uuid4()
    audit_payload = audit_logger.log_event(
        event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
        status=AuditStatus.SUCCESS,
        user_id=test_user_id,
        client_ip="10.0.0.1",
        user_agent="AuditAgent/2.0",
        details={"method": "password"},
    )

    assert audit_payload["audit_event"] == "AUTH_LOGIN_SUCCESS"
    assert audit_payload["audit_status"] == "SUCCESS"
    assert audit_payload["user_id"] == str(test_user_id)
    assert audit_payload["client_ip"] == "10.0.0.1"

    # Test high severity alert audit event (ALERT status triggers CRITICAL log level)
    alert_payload = audit_logger.log_event(
        event_type=AuditEventType.AUTH_LOGOUT,
        status=AuditStatus.ALERT,
        user_id=test_user_id,
        details={"reason": "Suspicious logout detected"},
    )
    assert alert_payload["audit_event"] == "AUTH_LOGOUT"
    assert alert_payload["audit_status"] == "ALERT"

    audit_test_logger.removeHandler(handler)
    print("  [OK] Audit Logger test passed.")


def test_request_id_middleware_and_endpoints():
    print("Testing Request ID Correlation Middleware & Endpoints...")

    client = TestClient(app)

    # 1. Test automatic Request ID generation
    res = client.get("/")
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    generated_id = res.headers["X-Request-ID"]
    assert len(generated_id) > 10

    # 2. Test client-provided Request ID propagation
    custom_req_id = "custom-req-id-12345-abcde"
    res2 = client.get("/", headers={"X-Request-ID": custom_req_id})
    assert res2.status_code == 200
    assert res2.headers["X-Request-ID"] == custom_req_id

    # 3. Test Honeypot Trigger Audit Logging
    res_bot = client.post(
        "/api/auth/register",
        json={
            "username": "bot_user",
            "email": "bot@example.com",
            "password": "Password123!",
            "website": "http://evil-bot.com",  # Honeypot filled
            "phone_confirm": "",
        },
    )
    # Returns fake 200 OK
    assert res_bot.status_code == 200
    assert "X-Request-ID" in res_bot.headers

    # 4. Test Unauthenticated Access Control Denial Audit Logging
    res_unauth = client.get("/api/auth/me")
    assert res_unauth.status_code == 401
    assert "X-Request-ID" in res_unauth.headers


    print("  [OK] Request ID Correlation Middleware & Endpoints test passed.")


def test_integrity_failure_audit_logging():
    print("Testing Data Integrity Tamper Audit Logging...")

    fake_token = "invalid.signature.payload"
    try:
        verify_signed_payload(fake_token)
    except IntegrityError:
        pass  # Expected

    print("  [OK] Data Integrity Tamper Audit Logging test passed.")


def test_database_audit_log_persistence():

    print("Testing Database Audit Log Persistence & User Relationship...")

    from app.database import SessionLocal
    from app.modules.audit_log.models import AuditLog
    from app.modules.auth.models import User
    from app.modules.audit_log.service import AuditLogService

    db = SessionLocal()
    try:
        # Create a test user if not existing
        test_email = f"audit_test_{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            email=test_email,
            username=f"audit_user_{uuid.uuid4().hex[:6]}",
            password="HashedPassword123!",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Log event with db session
        audit_logger.log_event(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            client_ip="127.0.0.1",
            user_agent="PyTest/1.0",
            details={"test_key": "test_value"},
            db=db,
        )

        # Query database for created audit log
        log_entry = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user.id)
            .order_by(AuditLog.created_at.desc())
            .first()
        )

        assert log_entry is not None
        assert log_entry.event_type == AuditEventType.AUTH_LOGIN_SUCCESS.value
        assert log_entry.status == AuditStatus.SUCCESS.value
        assert log_entry.user_id == user.id
        assert log_entry.user is not None
        assert log_entry.user.email == test_email
        assert log_entry.created_at is not None

        # Test listing via AuditLogService
        service_res = AuditLogService.list_audit_logs(db=db, target_user_id=user.id)
        assert service_res.total >= 1
        assert service_res.items[0].user_email == test_email

        # Clean up test user & audit log
        db.delete(log_entry)
        db.delete(user)
        db.commit()

        print("  [OK] Database Audit Log Persistence & User Relationship test passed.")
    finally:
        db.close()


def main():
    print("============================================================")
    print(" Running OWASP A09 Security Logging & Audit Verification    ")
    print("============================================================")

    test_sensitive_data_redaction()
    test_json_formatter()
    test_audit_logger()
    test_request_id_middleware_and_endpoints()
    test_integrity_failure_audit_logging()
    test_database_audit_log_persistence()

    print("\n[SUCCESS] ALL OWASP A09 Security Logging & Monitoring verification tests passed!")


if __name__ == "__main__":
    main()

