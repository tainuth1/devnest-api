"""
Software and Data Integrity Module.

Provides HMAC-SHA256 cryptographic signatures, constant-time verification,
and tamper-evident payload signing to ensure data integrity across system boundaries.
"""

import base64
import hmac
import hashlib
import json
from typing import Any

from app.core import timezone as tz
from app.core.config import settings


class IntegrityError(ValueError):
    """Raised when data signature or payload integrity verification fails."""
    pass


def generate_data_signature(data: str | bytes) -> str:
    """
    Generate an HMAC-SHA256 signature for data using the application SECRET_KEY.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    
    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


def verify_data_signature(data: str | bytes, signature: str) -> bool:
    """
    Constant-time HMAC-SHA256 signature verification to prevent timing attacks.
    """
    expected = generate_data_signature(data)
    return hmac.compare_digest(expected, signature)


def sign_payload(payload: dict[str, Any], ttl_seconds: int = 3600) -> str:
    """
    Create a tamper-evident, cryptographic signed token payload.

    Args:
        payload: Dict containing arbitrary serializable data.
        ttl_seconds: Validity lifetime of the token in seconds.

    Returns:
        URL-safe base64 encoded signed token string.
    """
    now = int(tz.now().timestamp())
    signed_data = {
        "data": payload,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    
    raw_json = json.dumps(signed_data, sort_keys=True, separators=(",", ":"))
    signature = generate_data_signature(raw_json)
    
    container = {
        "body": raw_json,
        "sig": signature,
    }
    
    container_bytes = json.dumps(container, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(container_bytes).decode("utf-8")


def verify_signed_payload(token: str) -> dict[str, Any]:
    """
    Decode and verify a signed token payload.

    Raises:
        IntegrityError: If token structure is invalid, signature is tampered, or expired.
    """
    try:
        decoded_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
        container = json.loads(decoded_bytes.decode("utf-8"))
        raw_body = container["body"]
        provided_sig = container["sig"]
    except Exception as e:
        raise IntegrityError("Invalid token format or structure") from e

    # Constant-time signature verification
    if not verify_data_signature(raw_body, provided_sig):
        from app.core.audit import audit_logger, AuditEventType, AuditStatus
        audit_logger.log_event(
            event_type=AuditEventType.INTEGRITY_CHECK_FAILED,
            status=AuditStatus.ALERT,
            details={"reason": "HMAC signature mismatch — possible tampering detected"},
        )
        raise IntegrityError("Data integrity check failed: signature mismatch (tampering detected)")


    try:
        signed_data = json.loads(raw_body)
    except Exception as e:
        raise IntegrityError("Invalid payload content") from e

    now = int(tz.now().timestamp())
    exp = signed_data.get("exp", 0)

    if now >= exp:
        raise IntegrityError("Token has expired")

    return signed_data.get("data", {})
