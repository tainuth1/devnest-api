"""
Pydantic request / response schemas for the auth module.

Validation rules applied here keep the service layer clean \u2014 by the time
data reaches the service, it is already structurally valid.
"""

import re
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.honeypot import HoneypotMixin
from app.core.password_security import validate_password_strength
from app.core.sanitize import strip_control_characters


class RegisterRequest(HoneypotMixin):
    """
    Body for POST /api/auth/register.

    Inherits `website` and `phone_confirm` honeypot fields from HoneypotMixin.
    Both fields are excluded from model_dump() output automatically.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="3–50 chars, letters / digits / underscores only.",
        examples=["john_doe"],
    )
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Min 8 chars, uppercase, lowercase, digit, special char, non-common.",
        examples=["Secret123!"],
    )

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        v = strip_control_characters(v).strip()
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username may only contain letters, numbers, and underscores."
            )
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str, info) -> str:
        data = info.data
        username = data.get("username", "")
        email = str(data.get("email", ""))
        return validate_password_strength(v, username=username, email=email)



class RegisterResponseData(BaseModel):
    """Data payload returned after a successful register request."""
    email: str


class VerifyOtpRequest(HoneypotMixin):
    """
    Body for POST /api/auth/verify-otp.

    Inherits honeypot fields from HoneypotMixin.
    """

    email: EmailStr = Field(..., examples=["john@example.com"])
    otp_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Exactly 6 numeric digits.",
        examples=["042819"],
    )


class VerifyOtpResponseData(BaseModel):
    """Data payload returned after successful OTP verification."""
    email: str
    username: str


class LoginRequest(HoneypotMixin):
    """
    Body for POST /api/auth/login.

    Accepts either email or username in `login_id`.
    Inherits honeypot fields (`website`, `phone_confirm`) from HoneypotMixin.
    """

    login_id: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Your registered email address or username.",
        examples=["john@example.com", "john_doe"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Account password.",
        examples=["Secret123"],
    )

    @field_validator("login_id")
    @classmethod
    def clean_login_id(cls, v: str) -> str:
        return strip_control_characters(v).strip().lower()


class UserInfoData(BaseModel):
    """User account details returned in login payload."""

    id: str
    email: str
    username: str | None = None
    role: str
    status: str
    first_name: str | None = None
    last_name: str | None = None


class TokenData(BaseModel):
    """Token payload returned upon successful authentication."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponseData(BaseModel):
    """Data payload returned after successful authentication."""

    user: UserInfoData
    tokens: TokenData


class RefreshTokenResponseData(BaseModel):
    """Data payload returned after successful token refresh."""

    tokens: TokenData



class UserMeResponseData(BaseModel):
    """Data payload returned for GET /api/auth/me."""

    id: str
    email: str
    username: str | None = None
    role: str
    status: str
    first_name: str | None = None
    last_name: str | None = None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UpdateProfileRequest(BaseModel):
    """
    Body for PUT/PATCH /api/auth/me.

    All fields are optional to allow partial or full profile updates.
    """

    first_name: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="First name (1–100 chars).",
        examples=["John"],
    )
    last_name: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        description="Last name (1–100 chars).",
        examples=["Doe"],
    )
    username: str | None = Field(
        None,
        min_length=3,
        max_length=50,
        description="3–50 chars, letters / digits / underscores only.",
        examples=["john_doe"],
    )
    email: EmailStr | None = Field(
        None,
        description="Valid email address.",
        examples=["john@example.com"],
    )

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = strip_control_characters(v).strip()
        if not v:
            raise ValueError("Username cannot be blank.")
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username may only contain letters, numbers, and underscores."
            )
        return v.lower()

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name_fields(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = strip_control_characters(v).strip()
        if not v:
            raise ValueError("Name fields cannot be blank strings.")
        return v


class ForgotPasswordRequest(HoneypotMixin):
    """
    Body for POST /api/auth/forgot-password.

    Inherits honeypot fields (`website`, `phone_confirm`) from HoneypotMixin.
    """

    email: EmailStr = Field(..., examples=["john@example.com"])


class VerifyResetOtpRequest(HoneypotMixin):
    """
    Body for POST /api/auth/verify-reset-otp.

    Inherits honeypot fields from HoneypotMixin.
    """

    email: EmailStr = Field(..., examples=["john@example.com"])
    otp_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Exactly 6 numeric digits.",
        examples=["042819"],
    )


class ResetPasswordRequest(HoneypotMixin):
    """
    Body for POST /api/auth/reset-password.

    Inherits honeypot fields from HoneypotMixin.
    """

    email: EmailStr = Field(..., examples=["john@example.com"])
    otp_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Exactly 6 numeric digits.",
        examples=["042819"],
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Min 8 chars, uppercase, lowercase, digit, special char, non-common.",
        examples=["NewSecret123!"],
    )

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str, info) -> str:
        email = str(info.data.get("email", ""))
        return validate_password_strength(v, email=email)


class ChangePasswordRequest(BaseModel):
    """
    Body for POST /api/auth/change-password.

    Requires current password for verification and new password meeting OWASP strength rules.
    """

    current_password: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Current account password.",
        examples=["OldSecret123!"],
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Min 8 chars, uppercase, lowercase, digit, special char, non-common.",
        examples=["NewSecret123!"],
    )

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return validate_password_strength(v)





