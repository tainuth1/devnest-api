import uuid
from fastapi import APIRouter, Body, Cookie, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.limiter import (
    limiter,
    AUTH_OTP_LIMIT,
    AUTH_VERIFY_LIMIT,
    AUTH_SIGNIN_LIMIT,
    AUTH_SESSION_LIMIT,
    AUTH_ME_LIMIT,
    AUTH_PROFILE_LIMIT,
)
from app.core.security import hash_session_token
from app.core.honeypot import (
    honeypot_register,
    honeypot_verify_otp,
    honeypot_login,
    honeypot_forgot_password,
    honeypot_verify_reset_otp,
    honeypot_reset_password,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    RegisterRequest,
    RegisterResponseData,
    VerifyOtpRequest,
    VerifyOtpResponseData,
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
from app.core.cookie import (
    set_session_cookie,
    clear_session_cookie,
    SESSION_COOKIE_NAME,
)
from app.modules.auth.service import AuthService, _EmailAlreadyRegistered
from app.shared import responses as res

router = APIRouter()


@router.post(
    "/register",
    summary="Register a new account",
    description=(
        "Phase 1 of registration. Validates input, stores the registration temporarily, "
        "and sends a 6-digit OTP to the provided email address. "
        "The account is **not** created until the OTP is verified via `/verify-otp`."
    ),
    response_description="OTP sent successfully.",
)
@limiter.limit(AUTH_OTP_LIMIT)
async def register(
    request: Request,
    _: None = Depends(honeypot_register),
    body: RegisterRequest = Body(...),
    db: Session = Depends(get_db),
):
    try:
        await AuthService.register(db=db, data=body)
    except _EmailAlreadyRegistered:
        pass
    return res.ok(
        message=(
            f"A verification code has been sent to {body.email}. "
            f"Please check your inbox and enter the 6-digit code to complete registration."
        ),
        data=RegisterResponseData(email=body.email).model_dump(),
    )



@router.post(
    "/verify-otp",
    summary="Verify OTP and activate account",
    description=(
        "Phase 2 of registration. Submit the 6-digit OTP received by email. "
        "On success, the user account is created and activated immediately. "
        f"The OTP expires after the configured window and allows a limited number of attempts."
    ),
    response_description="Account created and activated.",
    status_code=201,
)
@limiter.limit(AUTH_VERIFY_LIMIT)
async def verify_otp(
    request: Request,
    _: None = Depends(honeypot_verify_otp),
    body: VerifyOtpRequest = Body(...),
    db: Session = Depends(get_db),
):
    user = AuthService.verify_register_otp(db=db, data=body)
    return res.created(
        message="Account created successfully. You can now sign in.",
        data=VerifyOtpResponseData(
            email=user.email,
            username=user.username,
        ).model_dump(),
    )


@router.post(
    "/login",
    summary="Authenticate user and create session",
    description=(
        "Authenticates a user with email/username and password. "
        "Enforces rate limiting, honeypot bot detection, anti-brute-force account lockout, "
        "timing-attack defense, and account status checks. "
        "On success, creates a server-side session and sets an HttpOnly `session_id` cookie. "
        "Set `remember_me: true` to extend session lifetime from 7 days to 30 days."
    ),
    response_description="Login successful — session cookie set.",
)
@limiter.limit(AUTH_SIGNIN_LIMIT)
async def login(
    request: Request,
    _: None = Depends(honeypot_login),
    body: LoginRequest = Body(...),
    db: Session = Depends(get_db),
):
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    login_data, raw_session_token = AuthService.login(
        db=db,
        data=body,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    response = res.ok(
        message="Login successful.",
        data=login_data.model_dump(),
    )
    set_session_cookie(
        response=response,
        session_token=raw_session_token,
        remember_me=body.remember_me,
    )
    return response


@router.get(
    "/me",
    summary="Get current user profile",
    description=(
        "Retrieves the account profile details of the currently authenticated user "
        "identified by the `session_id` HttpOnly cookie."
    ),
    response_description="User profile retrieved successfully.",
)
@limiter.limit(AUTH_ME_LIMIT)
async def get_me(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    result: UserMeResponseData = AuthService.get_me(user=current_user)
    return res.ok(
        message="User profile retrieved successfully.",
        data=result.model_dump(mode="json"),
    )


@router.put(
    "/me",
    summary="Update current user profile",
    description=(
        "Updates profile details (first_name, last_name, username, email) for the currently authenticated user "
        "identified by the `session_id` HttpOnly cookie."
    ),
    response_description="User profile updated successfully.",
)
@router.patch(
    "/me",
    summary="Update current user profile (partial)",
    description=(
        "Updates profile details (first_name, last_name, username, email) for the currently authenticated user "
        "identified by the `session_id` HttpOnly cookie."
    ),
    response_description="User profile updated successfully.",
)
@limiter.limit(AUTH_PROFILE_LIMIT)
async def update_me(
    request: Request,
    body: UpdateProfileRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result: UserMeResponseData = AuthService.update_profile(
        db=db,
        user=current_user,
        data=body,
    )
    return res.ok(
        message="User profile updated successfully.",
        data=result.model_dump(mode="json"),
    )


@router.post(
    "/me/avatar",
    summary="Update current user avatar",
    description=(
        "Updates the profile image (avatar_url) for the currently authenticated user "
        "identified by the session cookie. No user ID parameter required."
    ),
    response_description="Profile image updated successfully.",
)
@router.patch(
    "/me/avatar",
    summary="Update current user avatar (partial)",
    description=(
        "Updates the profile image (avatar_url) for the currently authenticated user "
        "identified by the session cookie. No user ID parameter required."
    ),
    response_description="Profile image updated successfully.",
)
@limiter.limit(AUTH_PROFILE_LIMIT)
async def update_avatar(
    request: Request,
    body: UpdateAvatarRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result: UserMeResponseData = AuthService.update_avatar(
        db=db,
        user=current_user,
        data=body,
    )
    return res.ok(
        message="Profile image updated successfully.",
        data=result.model_dump(mode="json"),
    )


@router.post(
    "/logout",
    summary="Sign out user",
    description=(
        "Revokes the user's server-side session in the database and clears the `session_id` HttpOnly cookie."
    ),
    response_description="Logged out successfully.",
)
@limiter.limit(AUTH_SESSION_LIMIT)
async def logout(
    request: Request,
    db: Session = Depends(get_db),
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    AuthService.logout(db=db, session_token=session_id)
    response = res.ok(message="Logged out successfully.")
    clear_session_cookie(response=response)
    return response


@router.get(
    "/sessions",
    summary="List active sessions for current user",
    description="Returns all active, non-expired sessions for the currently authenticated user.",
    response_description="Active sessions retrieved successfully.",
)
@limiter.limit(AUTH_SESSION_LIMIT)
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    sessions = AuthService.get_sessions(
        db=db,
        user=current_user,
        current_session_token=session_token,
    )
    return res.ok(
        message="Active sessions retrieved successfully.",
        data=[s.model_dump(mode="json") for s in sessions],
    )


@router.delete(
    "/sessions",
    summary="Revoke all sessions for current user",
    description=(
        "Revokes all active sessions for the currently authenticated user, including the current session. "
        "The session cookie is cleared, forcing re-authentication on all devices."
    ),
    response_description="All sessions revoked successfully.",
)
@limiter.limit(AUTH_SESSION_LIMIT)
async def revoke_all_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = AuthService.revoke_all_sessions(db=db, user_id=current_user.id)
    response = res.ok(
        message="All sessions have been revoked successfully. Please log in again.",
        data={"revoked_count": count},
    )
    clear_session_cookie(response=response)
    return response


@router.delete(
    "/sessions/{session_id}",
    summary="Revoke a specific session for current user",
    description=(
        "Revokes a specific session by ID for the currently authenticated user. "
        "Returns 403 if the session belongs to a different user. "
        "If the revoked session is the current session, the session cookie is cleared."
    ),
    response_description="Session revoked successfully.",
)
@limiter.limit(AUTH_SESSION_LIMIT)
async def revoke_session(
    request: Request,
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_record = AuthService.revoke_session(
        db=db,
        user=current_user,
        session_id=session_id,
    )
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    is_current = False
    if session_cookie:
        current_hash = hash_session_token(session_cookie)
        is_current = (session_record.token_hash == current_hash)

    response = res.ok(
        message="Session revoked successfully.",
        data={"session_id": str(session_id), "is_current": is_current},
    )
    if is_current:
        clear_session_cookie(response=response)
    return response


@router.post(
    "/forgot-password",
    summary="Request password reset OTP",
    description=(
        "Sends a 6-digit OTP code to the provided email address if an active account exists. "
        "To prevent email enumeration attacks, this endpoint always returns a generic success response."
    ),
    response_description="Password reset code sent to email if registered.",
)
@limiter.limit(AUTH_OTP_LIMIT)
async def forgot_password(
    request: Request,
    _: None = Depends(honeypot_forgot_password),
    body: ForgotPasswordRequest = Body(...),
    db: Session = Depends(get_db),
):
    await AuthService.forgot_password(db=db, data=body)
    return res.ok(
        message=(
            "If that email address is registered, "
            "you will receive a password reset verification code shortly."
        ),
        data={"email": body.email},
    )


@router.post(
    "/verify-reset-otp",
    summary="Verify password reset OTP",
    description=(
        "Verifies that the 6-digit OTP code sent for a password reset request is valid and not expired."
    ),
    response_description="OTP code verified successfully.",
)
@limiter.limit(AUTH_VERIFY_LIMIT)
async def verify_reset_otp(
    request: Request,
    _: None = Depends(honeypot_verify_reset_otp),
    body: VerifyResetOtpRequest = Body(...),
    db: Session = Depends(get_db),
):
    AuthService.verify_reset_otp(db=db, data=body)
    return res.ok(
        message="OTP code verified successfully. You can now set a new password.",
        data={"email": body.email},
    )


@router.post(
    "/reset-password",
    summary="Reset user password",
    description=(
        "Verifies the 6-digit OTP code and updates the user's password. "
        "Revokes all existing sessions for security."
    ),
    response_description="Password reset successfully.",
)
@limiter.limit(AUTH_VERIFY_LIMIT)
async def reset_password(
    request: Request,
    _: None = Depends(honeypot_reset_password),
    body: ResetPasswordRequest = Body(...),
    db: Session = Depends(get_db),
):
    AuthService.reset_password(db=db, data=body)
    return res.ok(
        message="Password reset successfully. You can now log in with your new password.",
    )


@router.post(
    "/change-password",
    summary="Change user password (authenticated)",
    description=(
        "Changes the password for the currently authenticated user. "
        "Requires verification of the current password. "
        "Revokes all active sessions across all devices for security."
    ),
    response_description="Password changed successfully.",
)
@limiter.limit(AUTH_PROFILE_LIMIT)
async def change_password(
    request: Request,
    body: ChangePasswordRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthService.change_password(db=db, user=current_user, data=body)
    response = res.ok(
        message="Password changed successfully. Please log in again with your new password.",
    )
    clear_session_cookie(response=response)
    return response
