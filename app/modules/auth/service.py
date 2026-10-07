"""
Auth service — business logic for the authentication module.

Keeps all domain logic out of the router layer. Raises HTTPException directly
since this is a small project with a single HTTP transport layer.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import timezone as tz
from app.core.config import settings
from app.core.enums import UserStatus
from app.core.sanitize import sanitize_for_log
from app.core.security import (
    hash_password,
    verify_password,
    verify_dummy_password,
    generate_session_token,
    hash_session_token,
)
from app.core.otp import generate_otp, hash_otp, verify_otp
from app.core.email import send_otp_email, send_password_reset_otp_email, send_already_registered_email
from app.modules.auth.models import PendingRegistration, UserSession, User, PasswordReset
from app.modules.auth.schemas import (
    RegisterRequest,
    VerifyOtpRequest,
    LoginRequest,
    LoginResponseData,
    UserInfoData,
    UserMeResponseData,
    UpdateProfileRequest,
    UpdateAvatarRequest,
    SessionResponseData,
    ForgotPasswordRequest,
    VerifyResetOtpRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
)

from app.core.audit import audit_logger, AuditEventType, AuditStatus

logger = logging.getLogger("app.auth.service")


class _EmailAlreadyRegistered(Exception):

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"Email already registered: {email}")


class AuthService:
    """Stateless auth service. Each method receives a DB session explicitly."""

    @staticmethod
    async def register(db: Session, data: RegisterRequest) -> PendingRegistration:
        """
        Phase 1 of two-phase registration.

        1. Check email / username uniqueness against the live User table.
        2. Replace any stale PendingRegistration for the same email (resend flow).
        3. Hash password + generate/hash OTP.
        4. Persist PendingRegistration.
        5. Send OTP email.

        Returns:
            The newly created PendingRegistration row.

        Raises:
            409 Conflict  — email or username already registered.
            500           — email sending failed.
        """
        # Check existing User
        existing_email = db.query(User).filter(User.email == data.email).first()
        if existing_email:
            logger.warning(
                "Registration attempt for existing email (silent notification sent) | email=%s",
                sanitize_for_log(data.email),
            )
            try:
                await send_already_registered_email(
                    to_email=data.email,
                    username=existing_email.username or existing_email.email,
                )
            except Exception:
                pass 
            raise _EmailAlreadyRegistered(email=data.email)

        existing_username = db.query(User).filter(User.username == data.username).first()
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken. Please choose a different one.",
            )

        # Remove stale PendingRegistration (resend flow)
        stale = (
            db.query(PendingRegistration)
            .filter(PendingRegistration.email == data.email)
            .first()
        )
        if stale:
            db.delete(stale)
            db.flush()
            logger.info("Replaced stale pending registration for %s", sanitize_for_log(data.email))

        # Hash password + generate OTP
        otp_plain = generate_otp()
        expires_at = tz.now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        pending = PendingRegistration(
            username=data.username,
            email=data.email,
            hashed_password=hash_password(data.password),
            otp_hash=hash_otp(otp_plain),
            expires_at=expires_at,
        )

        # Persist
        db.add(pending)
        db.commit()
        db.refresh(pending)
        logger.info("PendingRegistration created for %s", sanitize_for_log(data.email))

        # Send OTP email
        try:
            await send_otp_email(
                to_email=data.email,
                username=data.username,
                otp_code=otp_plain,
            )
        except Exception:
            # Roll back if we can't send the email so user can retry
            db.delete(pending)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "We could not send a verification email. "
                    "Please try again in a few moments."
                ),
            )

        return pending

    @staticmethod
    def verify_register_otp(db: Session, data: VerifyOtpRequest) -> User:
        """
        Phase 2 of two-phase registration.

        1. Look up PendingRegistration by email.
        2. Check expiry.
        3. Check attempt limit.
        4. Increment attempts, verify OTP hash.
        5. On success: create User, delete PendingRegistration.

        Returns:
            The newly created (ACTIVE) User row.

        Raises:
            404 — no pending registration found for this email.
            422 — OTP expired / max attempts exceeded / invalid OTP.
        """
        # Find pending registration
        pending: PendingRegistration | None = (
            db.query(PendingRegistration)
            .filter(PendingRegistration.email == data.email)
            .first()
        )
        if not pending:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No pending registration found for this email. "
                    "Please register first."
                ),
            )

        # Check expiry
        if pending.is_expired:
            db.delete(pending)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Your OTP has expired (valid for {settings.OTP_EXPIRE_MINUTES} minutes). "
                    "Please register again to receive a new code."
                ),
            )

        # Check attempt limit
        if pending.is_locked:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Maximum verification attempts exceeded. "
                    "Please register again to receive a new code."
                ),
            )

        # Increment attempts + verify OTP
        pending.attempts += 1
        db.flush()  # persist attempt increment before verifying

        if not verify_otp(data.otp_code, pending.otp_hash):
            db.commit()  # commit the incremented attempt
            remaining = settings.OTP_MAX_ATTEMPTS - pending.attempts
            if remaining > 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Invalid OTP. No attempts remaining. "
                        "Please register again to receive a new code."
                    ),
                )

        # OTP valid — create User, remove pending row
        user = User(
            username=pending.username,
            email=pending.email,
            password=pending.hashed_password,  # already bcrypt-hashed
        )
        db.add(user)
        db.delete(pending)
        db.commit()
        db.refresh(user)

        logger.info(
            "User registered successfully | user_id=%s email=%s username=%s",
            user.id,
            sanitize_for_log(user.email),
            sanitize_for_log(user.username or ""),
        )

        return user

    @staticmethod
    def login(
        db: Session,
        data: LoginRequest,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> tuple[LoginResponseData, str]:
        """
        High-security user authentication with server-side session creation.

        1. Lookup user by email or username.
        2. Timing-attack mitigation: if user doesn't exist, verify dummy password and raise 401.
        3. Check account lockout: if locked_until is active, calculate remaining time and raise 401.
           If lockout expired, auto-unlock and clear failed counter.
        4. Enforce account status: SUSPENDED, BANNED, INACTIVE.
        5. Verify password. On failure:
           - Increment failed_login_attempts.
           - If failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS: set locked_until to now + ACCOUNT_LOCKOUT_MINUTES and raise 401.
           - Raise 401 with generic message.
        6. On success:
           - Clear failed_login_attempts and locked_until.
           - Update last_login_at.
           - Create UserSession record in DB (token stored as SHA-256 hash).
           - Return (LoginResponseData, raw_session_token).
        """
        login_target = data.login_id.strip().lower()
        user: User | None = (
            db.query(User)
            .filter((User.email == login_target) | (User.username == login_target))
            .first()
        )

        # Timing-attack defense
        if not user:
            verify_dummy_password()
            audit_logger.log_event(
                event_type=AuditEventType.AUTH_LOGIN_FAILED,
                status=AuditStatus.FAILURE,
                client_ip=ip_address,
                user_agent=user_agent,
                details={"target": sanitize_for_log(login_target), "reason": "User not found"},
                db=db,
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )


        # Check Lockout
        if user.is_locked_out:
            locked_dt = tz.ensure_tz_aware(user.locked_until)
            remaining_seconds = int((locked_dt - tz.now()).total_seconds()) if locked_dt else 0
            remaining_minutes = max(1, (remaining_seconds + 59) // 60)
            audit_logger.log_event(
                event_type=AuditEventType.AUTH_BLOCKED_LOCKED,
                status=AuditStatus.BLOCKED,
                user_id=user.id,
                client_ip=ip_address,
                user_agent=user_agent,
                details={"locked_until": locked_dt.isoformat() if locked_dt else None},
                db=db,
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"Account is temporarily locked due to multiple failed login attempts. "
                    f"Please try again in {remaining_minutes} minute(s)."
                ),
            )


        # Lockout expired — auto unlock
        locked_until_dt = tz.ensure_tz_aware(user.locked_until)
        if locked_until_dt and tz.now() >= locked_until_dt:
            user.locked_until = None
            user.failed_login_attempts = 0
            db.flush()

        # Check Account Status
        if user.status == UserStatus.SUSPENDED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been suspended. Please contact support.",
            )
        elif user.status == UserStatus.BANNED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been permanently banned.",
            )
        elif user.status == UserStatus.INACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is deactivated.",
            )

        # Verify Password
        if not verify_password(data.password, user.password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                user.locked_until = tz.now() + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
                db.commit()
                audit_logger.log_event(
                    event_type=AuditEventType.AUTH_LOCKOUT_TRIGGERED,
                    status=AuditStatus.BLOCKED,
                    user_id=user.id,
                    client_ip=ip_address,
                    user_agent=user_agent,
                    details={
                        "failed_attempts": user.failed_login_attempts,
                        "locked_until": user.locked_until.isoformat(),
                    },
                    db=db,
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        f"Too many failed login attempts. Your account has been temporarily locked for "
                        f"{settings.ACCOUNT_LOCKOUT_MINUTES} minutes."
                    ),
                )
            else:
                db.commit()
                audit_logger.log_event(
                    event_type=AuditEventType.AUTH_LOGIN_FAILED,
                    status=AuditStatus.FAILURE,
                    user_id=user.id,
                    client_ip=ip_address,
                    user_agent=user_agent,
                    details={
                        "attempt": user.failed_login_attempts,
                        "max_attempts": settings.MAX_FAILED_LOGIN_ATTEMPTS,
                        "reason": "Invalid password",
                    },
                    db=db,
                )

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid login credentials.",
                )


        # Successful Authentication
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = tz.now()

        # Determine session lifetime based on remember_me flag
        remember_me = data.remember_me
        session_days = (
            settings.SESSION_REMEMBER_ME_DAYS if remember_me else settings.SESSION_DEFAULT_DAYS
        )

        # Create Session (raw token is sent in cookie; only SHA-256 hash stored in DB)
        raw_token = generate_session_token()
        session = UserSession(
            token_hash=hash_session_token(raw_token),
            user_id=user.id,
            expires_at=tz.now() + timedelta(days=session_days),
            remember_me=remember_me,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(session)
        db.commit()
        db.refresh(user)

        audit_logger.log_event(
            event_type=AuditEventType.AUTH_LOGIN_SUCCESS,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            client_ip=ip_address,
            user_agent=user_agent,
            details={"session_id": str(session.id), "remember_me": remember_me},
            db=db,
        )

        return (
            LoginResponseData(
                user=UserInfoData(
                    id=str(user.id),
                    email=user.email,
                    username=user.username,
                    role=user.role.value,
                    status=user.status.value,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    avatar_url=user.avatar_url,
                ),
            ),
            raw_token,
        )

    @staticmethod
    def get_me(user: User) -> UserMeResponseData:
        """Construct profile response payload for the authenticated user."""
        return UserMeResponseData(
            id=str(user.id),
            email=user.email,
            username=user.username,
            role=user.role.value,
            status=user.status.value,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    def update_profile(
        db: Session,
        user: User,
        data: UpdateProfileRequest,
    ) -> UserMeResponseData:
        """
        Update profile details for the authenticated user.

        Checks username and email uniqueness if they are being updated to new values.

        Returns:
            Updated UserMeResponseData profile.

        Raises:
            409 Conflict — if new username or email is already taken by another account.
        """
        update_data = data.model_dump(exclude_unset=True)

        if "username" in update_data and update_data["username"] != user.username:
            new_username = update_data["username"]
            if new_username:
                existing_username = (
                    db.query(User)
                    .filter(User.username == new_username, User.id != user.id)
                    .first()
                )
                if existing_username:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This username is already taken. Please choose a different one.",
                    )
            user.username = new_username

        if "email" in update_data and update_data["email"] != user.email:
            new_email = update_data["email"]
            if new_email:
                existing_email = (
                    db.query(User)
                    .filter(User.email == new_email, User.id != user.id)
                    .first()
                )
                if existing_email:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="An account with this email address already exists.",
                    )
            user.email = new_email

        if "first_name" in update_data:
            user.first_name = update_data["first_name"]

        if "last_name" in update_data:
            user.last_name = update_data["last_name"]

        if "avatar_url" in update_data:
            avatar_val = update_data["avatar_url"]
            user.avatar_url = str(avatar_val) if avatar_val is not None else None

        user.updated_at = tz.now()
        db.commit()
        db.refresh(user)

        logger.info("User profile updated successfully | user_id=%s", user.id)

        return AuthService.get_me(user=user)

    @staticmethod
    def update_avatar(
        db: Session,
        user: User,
        data: UpdateAvatarRequest,
    ) -> UserMeResponseData:
        """
        Update the profile image (avatar_url) for the authenticated user.
        Uses user identity from the active session directly (no user_id needed in request).
        """
        user.avatar_url = str(data.avatar_url) if data.avatar_url is not None else None
        user.updated_at = tz.now()
        db.commit()
        db.refresh(user)

        logger.info("User avatar updated successfully | user_id=%s", user.id)
        return AuthService.get_me(user=user)

    @staticmethod
    def get_sessions(
        db: Session,
        user: User,
        current_session_token: str | None = None,
    ) -> list[SessionResponseData]:
        """
        Retrieve all active sessions for the authenticated user.
        """
        current_hash = hash_session_token(current_session_token) if current_session_token else None
        active_sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id, UserSession.revoked == False)
            .order_by(UserSession.created_at.desc())
            .all()
        )
        result: list[SessionResponseData] = []
        for s in active_sessions:
            if not s.is_expired:
                is_current = bool(current_hash is not None and s.token_hash == current_hash)
                result.append(
                    SessionResponseData(
                        id=str(s.id),
                        ip_address=s.ip_address,
                        user_agent=s.user_agent,
                        created_at=s.created_at,
                        expires_at=s.expires_at,
                        is_current=is_current,
                        remember_me=s.remember_me,
                    )
                )
        return result

    @staticmethod
    def revoke_all_sessions(db: Session, user_id: Any) -> int:
        """
        Revoke all active sessions for the user, including the current session.

        Returns:
            The number of sessions revoked.
        """
        active_sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == user_id, UserSession.revoked == False)
            .all()
        )
        count = len(active_sessions)
        for s in active_sessions:
            s.revoked = True

        db.commit()
        audit_logger.log_event(
            event_type=AuditEventType.AUTH_SESSIONS_REVOKED_ALL,
            status=AuditStatus.SUCCESS,
            user_id=user_id,
            details={"revoked_count": count},
            db=db,
        )
        logger.info("All sessions revoked for user_id=%s count=%d", user_id, count)
        return count

    @staticmethod
    def revoke_session(
        db: Session,
        user: User,
        session_id: uuid.UUID,
    ) -> UserSession:
        """
        Revoke a specific session by ID for the user.

        Raises:
            404 Not Found if the session does not exist.
            403 Forbidden if the session belongs to another user.
        """
        session_record = (
            db.query(UserSession)
            .filter(UserSession.id == session_id)
            .first()
        )
        if not session_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            )

        if session_record.user_id != user.id:
            audit_logger.log_event(
                event_type=AuditEventType.ACCESS_DENIED_UNAUTHORIZED,
                status=AuditStatus.BLOCKED,
                user_id=user.id,
                details={
                    "target_session_id": str(session_id),
                    "reason": "Attempted to revoke session belonging to another user",
                },
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to revoke this session.",
            )

        if not session_record.revoked:
            session_record.revoked = True
            db.commit()

        audit_logger.log_event(
            event_type=AuditEventType.AUTH_SESSION_REVOKED,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            details={"session_id": str(session_id)},
            db=db,
        )
        logger.info("Session %s revoked for user_id=%s", session_id, user.id)
        return session_record



    @staticmethod
    def logout(db: Session, session_token: str | None) -> None:
        """Revoke session in database if present."""
        if session_token:
            token_hash = hash_session_token(session_token)
            session_record = (
                db.query(UserSession)
                .filter(UserSession.token_hash == token_hash)
                .first()
            )
            if session_record and not session_record.revoked:
                session_record.revoked = True
                db.commit()
                audit_logger.log_event(
                    event_type=AuditEventType.AUTH_LOGOUT,
                    status=AuditStatus.SUCCESS,
                    user_id=session_record.user_id,
                    details={"session_id": str(session_record.id)},
                    db=db,
                )



    @staticmethod
    async def forgot_password(db: Session, data: ForgotPasswordRequest) -> None:
        """
        Request password reset OTP.

        1. Find User by email. To avoid account enumeration, silently log warning and return success if user does not exist.
        2. Delete any existing PasswordReset requests for this email.
        3. Generate 6-digit OTP + store hash + set expiry.
        4. Send password reset email with OTP.
        """
        user: User | None = db.query(User).filter(User.email == data.email).first()

        if not user:
            # User enumeration defense: do not reveal that email does not exist
            logger.warning("==> Password reset requested for non-existent email: %s", data.email)
            return

        # Check account status
        if user.status in (UserStatus.SUSPENDED, UserStatus.BANNED, UserStatus.INACTIVE):
            logger.warning("==> Password reset requested for inactive/banned user: %s", data.email)
            return

        # Delete existing reset records for this email
        stale_resets = db.query(PasswordReset).filter(PasswordReset.email == data.email).all()
        for r in stale_resets:
            db.delete(r)
        db.flush()

        otp_plain = generate_otp()
        expires_at = tz.now() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        reset_obj = PasswordReset(
            email=data.email,
            otp_hash=hash_otp(otp_plain),
            expires_at=expires_at,
        )

        db.add(reset_obj)
        db.commit()

        try:
            await send_password_reset_otp_email(
                to_email=data.email,
                username=user.username or user.email,
                otp_code=otp_plain,
            )
        except Exception:
            db.delete(reset_obj)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "We could not send a password reset verification email. "
                    "Please try again in a few moments."
                ),
            )

        logger.info("==> Password reset OTP requested for email: %s", sanitize_for_log(data.email))

    @staticmethod
    def verify_reset_otp(db: Session, data: VerifyResetOtpRequest) -> None:
        """
        Verify password reset OTP.

        1. Find PasswordReset by email.
        2. Check expiry.
        3. Check attempt limit.
        4. Verify OTP hash.
        """
        reset_record: PasswordReset | None = (
            db.query(PasswordReset)
            .filter(PasswordReset.email == data.email)
            .order_by(PasswordReset.created_at.desc())
            .first()
        )

        if not reset_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No password reset request found for this email address.",
            )

        if reset_record.is_expired:
            db.delete(reset_record)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Your password reset code has expired (valid for {settings.OTP_EXPIRE_MINUTES} minutes). "
                    "Please request a new password reset code."
                ),
            )

        if reset_record.is_locked:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Maximum verification attempts exceeded. Please request a new code.",
            )

        reset_record.attempts += 1
        db.flush()

        if not verify_otp(data.otp_code, reset_record.otp_hash):
            db.commit()
            remaining = settings.OTP_MAX_ATTEMPTS - reset_record.attempts
            if remaining > 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid OTP code. {remaining} attempt(s) remaining.",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid OTP code. No attempts remaining. Please request a new code.",
                )

    @staticmethod
    def reset_password(db: Session, data: ResetPasswordRequest) -> None:
        """
        Reset password with OTP verification.

        1. Verify OTP using verify_reset_otp.
        2. Update user password hash.
        3. Clear lockout / failed attempts.
        4. Revoke all active sessions.
        5. Delete PasswordReset record.
        """
        AuthService.verify_reset_otp(
            db=db,
            data=VerifyResetOtpRequest(email=data.email, otp_code=data.otp_code),
        )

        user: User | None = db.query(User).filter(User.email == data.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found.",
            )

        # Ensure new password is different from the current one
        if verify_password(data.new_password, user.password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must be different from your current password.",
            )

        # Update password & unlock account
        user.password = hash_password(data.new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = tz.now()

        # Revoke all active sessions for security
        active_sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id, UserSession.revoked == False)
            .all()
        )
        for sess in active_sessions:
            sess.revoked = True

        # Delete password reset record
        reset_record = (
            db.query(PasswordReset)
            .filter(PasswordReset.email == data.email)
            .first()
        )
        if reset_record:
            db.delete(reset_record)

        db.commit()
        logger.info("==> Password reset successful for user_id=%s email=%s", user.id, user.email)

    @staticmethod
    def change_password(
        db: Session,
        user: User,
        data: ChangePasswordRequest,
    ) -> None:
        """
        Change password for an authenticated user.

        1. Verify current password.
        2. Ensure new password is different from current password.
        3. Update password hash.
        4. Revoke all active sessions (force re-authentication on other devices).
        """
        if not verify_password(data.current_password, user.password):
            audit_logger.log_event(
                event_type=AuditEventType.PASSWORD_CHANGE_FAILED,
                status=AuditStatus.FAILURE,
                user_id=user.id,
                details={"reason": "Incorrect current password"},
                db=db,
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect.",
            )


        if verify_password(data.new_password, user.password):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must be different from your current password.",
            )

        user.password = hash_password(data.new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = tz.now()

        # Revoke all active sessions to force re-login on all devices
        active_sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == user.id, UserSession.revoked == False)
            .all()
        )
        for sess in active_sessions:
            sess.revoked = True

        db.commit()
        audit_logger.log_event(
            event_type=AuditEventType.PASSWORD_CHANGE_SUCCESS,
            status=AuditStatus.SUCCESS,
            user_id=user.id,
            db=db,
        )
