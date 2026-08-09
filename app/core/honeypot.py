"""
Honeypot bot-detection for FastAPI authentication endpoints.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
How it works
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. The frontend includes hidden, invisible fields in its JSON payload:
       "website":       ""   ← hidden via CSS (display:none / aria-hidden)
       "phone_confirm": ""   ← hidden via CSS
   Real users never fill these. Bots that blindly populate all fields will.

2. On each protected route, a FastAPI Depends() guard reads the raw JSON body
   before schema validation and checks those two fields.

3. If any honeypot field is filled:
   - The event (IP, user-agent, endpoint, filled fields) is persisted to the
     `honeypot_events` table for threat intelligence.
   - A HoneypotTriggered exception is raised.
   - The global handler in main.py catches it and returns a *fake 200 OK*,
     so the bot never learns it was detected.

4. If the fields are empty, execution continues normally to the route handler.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Frontend contract
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every protected form must send these two extra fields (always empty strings):

    POST /api/auth/register
    {
      "email": "user@example.com",
      "password": "...",
      "website": "",          ← always empty
      "phone_confirm": ""     ← always empty
    }

To hide them from real users (React/Vue/plain HTML example):
    <input type="text" name="website"       value="" style="display:none" tabindex="-1" autocomplete="off" />
    <input type="text" name="phone_confirm" value="" style="display:none" tabindex="-1" autocomplete="off" />

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usage in route handlers
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Import the pre-configured guard for each endpoint:

    from app.core.honeypot import honeypot_register, HoneypotMixin

    class RegisterRequest(HoneypotMixin):
        email: EmailStr
        password: str

    @router.post("/register")
    async def register(
        _: None = Depends(honeypot_register),
        body: RegisterRequest = Body(...),
    ):
        clean_data = body.model_dump()  # website / phone_confirm excluded automatically
        ...

Available pre-configured guards:
    honeypot_register        → /auth/register
    honeypot_login           → /auth/login
    honeypot_forgot_password → /auth/forgot-password
    honeypot_verify_otp      → /auth/verify-otp

Or create a custom guard with make_honeypot_guard().
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, Session

from app.database import Base, get_db
from app.core import timezone as tz

logger = logging.getLogger("app.honeypot")

# Honeypot field names
# These must exactly match the hidden field names the frontend sends.
# Adding/removing fields here is the only change needed to update the contract.

HONEYPOT_FIELDS: tuple[str, ...] = ("website", "phone_confirm")

# Sensitive keys whose values are masked in the body snippet stored to the DB
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password",
    "new_password",
    "confirm_password",
    "current_password",
    "token",
    "otp",
    "code",
})


# Database model

class HoneypotEvent(Base):
    """
    Persisted record of every honeypot trigger.

    Useful for:
    - Auditing bot activity over time
    - Building IP block-lists
    - Detecting coordinated attacks across endpoints
    """

    __tablename__ = "honeypot_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The IP address of the bot (IPv4 or IPv6 — String(45) covers both)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)

    # Raw User-Agent header — useful for fingerprinting bots
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Which endpoint was targeted (e.g. "/auth/login")
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Comma-separated names of the honeypot fields that were filled in
    # e.g. "website" or "website,phone_confirm"
    filled_fields: Mapped[str] = mapped_column(String(255), nullable=False)

    # Sanitized JSON body snippet for debugging — passwords/tokens are redacted
    body_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=tz.now,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<HoneypotEvent id={self.id} "
            f"ip={self.ip_address} "
            f"endpoint={self.endpoint} "
            f"fields={self.filled_fields}>"
        )


# Silent rejection exception

class HoneypotTriggered(Exception):
    """
    Raised by the honeypot guard when a bot is detected.

    Deliberately NOT an HTTPException — it is caught by a dedicated handler
    in main.py that returns a convincing fake 200 OK response.  This way:
    - The bot receives no error signal (no 422/400 status codes to act on)
    - Retry logic in bots stalls without useful feedback
    - Log/monitoring systems can distinguish honeypot blocks from real errors
    """

    def __init__(self, silent_message: str) -> None:
        self.silent_message = silent_message
        super().__init__(silent_message)


# Pydantic mixin

class HoneypotMixin(BaseModel):
    """
    Pydantic mixin that adds invisible honeypot fields to a request schema.

    Both fields are excluded from model_dump() output, so they are never
    forwarded to service layers or stored in the database.

    Usage:
        class RegisterRequest(HoneypotMixin):
            email: EmailStr
            password: str

        # body.model_dump() → {"email": "...", "password": "..."}
        # "website" and "phone_confirm" are stripped automatically
    """

    website: str = Field(
        default="",
        exclude=True,
        description="Leave empty — bot detection field",
    )
    phone_confirm: str = Field(
        default="",
        exclude=True,
        description="Leave empty — bot detection field",
    )


# Guard dependency factory

def make_honeypot_guard(
    endpoint: str = "unknown",
    silent_message: str = "Request processed successfully.",
):
    """
    Returns a FastAPI dependency that performs honeypot validation.

    The dependency:
      1. Reads the raw request JSON before Pydantic schema parsing.
      2. Checks whether any honeypot field contains a non-empty value.
      3. On detection — logs to DB + raises HoneypotTriggered (→ fake 200 OK).
      4. On clean — returns None, allowing the request to proceed normally.

    Args:
        endpoint:       Label stored in the DB (e.g. "/auth/login").
        silent_message: Fake success message returned to the bot.

    Returns:
        An async FastAPI dependency (suitable for Depends()).

    Example:
        @router.post("/login")
        async def login(
            _: None = Depends(make_honeypot_guard(
                endpoint="/auth/login",
                silent_message="If your credentials are valid, you will be signed in.",
            )),
            body: LoginRequest = Body(...),
        ):
            ...
    """

    async def _guard(
        request: Request,
        db: Session = Depends(get_db),
    ) -> None:
        # 1. Parse JSON body
        # Safely read the body — if parsing fails, let FastAPI's own validation
        # handle the malformed input further down the stack.
        try:
            body: dict = await request.json()
        except Exception:
            return

        if not isinstance(body, dict):
            return

        # 2. Check honeypot fields
        filled = [field for field in HONEYPOT_FIELDS if body.get(field, "")]
        if not filled:
            return  # Legitimate request — pass through

        # 3. Bot detected
        ip: str = request.client.host if request.client else "unknown"
        user_agent: str = request.headers.get("user-agent", "")

        # Build sanitised body snippet (redact all sensitive keys)
        safe_body = {
            k: "***" if k in _SENSITIVE_KEYS else str(v)[:80]
            for k, v in body.items()
        }
        body_snippet: str = str(safe_body)[:500]

        # 4. Persist to database & log audit event
        try:
            event = HoneypotEvent(
                ip_address=ip,
                user_agent=user_agent[:512] if user_agent else None,
                endpoint=endpoint,
                filled_fields=",".join(filled),
                body_snippet=body_snippet,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            from app.core.audit import audit_logger, AuditEventType, AuditStatus
            audit_logger.log_event(
                event_type=AuditEventType.HONEYPOT_TRIGGERED,
                status=AuditStatus.BLOCKED,
                client_ip=ip,
                user_agent=user_agent,
                details={
                    "event_id": str(event.id),
                    "endpoint": endpoint,
                    "filled_fields": filled,
                },
                db=db,
            )

        except Exception as db_err:
            logger.error(
                "Honeypot DB write failed (event still logged) | ip=%s endpoint=%s error=%s",
                ip,
                endpoint,
                db_err,
                exc_info=True,
            )
            db.rollback()
            from app.core.audit import audit_logger, AuditEventType, AuditStatus
            audit_logger.log_event(
                event_type=AuditEventType.HONEYPOT_TRIGGERED,
                status=AuditStatus.BLOCKED,
                client_ip=ip,
                user_agent=user_agent,
                details={
                    "endpoint": endpoint,
                    "filled_fields": filled,
                    "db_error": str(db_err),
                },
            )


        # 5. Silent rejection
        # Raise HoneypotTriggered — caught by main.py handler → fake 200 OK
        raise HoneypotTriggered(silent_message=silent_message)

    return _guard


# Pre-configured guards
# Ready-to-use Depends() guards for each protected auth endpoint.
# Import and drop them directly into route definitions.

honeypot_register = make_honeypot_guard(
    endpoint="/auth/register",
    silent_message=(
        "Account created successfully. "
        "Please check your email to verify your account."
    ),
)

honeypot_login = make_honeypot_guard(
    endpoint="/auth/login",
    silent_message=(
        "If your credentials are correct, you will be signed in."
    ),
)

honeypot_forgot_password = make_honeypot_guard(
    endpoint="/auth/forgot-password",
    silent_message=(
        "If that email address is registered, "
        "you will receive a password reset link shortly."
    ),
)

honeypot_verify_otp = make_honeypot_guard(
    endpoint="/auth/verify-otp",
    silent_message="OTP verified successfully.",
)

honeypot_verify_reset_otp = make_honeypot_guard(
    endpoint="/auth/verify-reset-otp",
    silent_message="OTP verified successfully.",
)

honeypot_reset_password = make_honeypot_guard(
    endpoint="/auth/reset-password",
    silent_message="Password reset successfully.",
)



