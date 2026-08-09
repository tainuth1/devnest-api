"""Security utilities for password hashing, JWT creation, and timing attack mitigation."""

import hashlib
import secrets
import uuid
from datetime import timedelta

import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__about__"):
    class _About:
        __version__ = _bcrypt.__version__
    _bcrypt.__about__ = _About()

_orig_hashpw = _bcrypt.hashpw
def _safe_hashpw(password, salt):
    if isinstance(password, (bytes, bytearray)) and len(password) > 72:
        password = password[:72]
    return _orig_hashpw(password, salt)
_bcrypt.hashpw = _safe_hashpw


import jwt as pyjwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings
from app.core import timezone as tz

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed bcrypt hash of "DummyPassword123!" for constant-time verification when user is not found
_DUMMY_BCRYPT_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"


def hash_password(password: str) -> str:
    """Return the bcrypt hash of a plain-text password."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


def verify_dummy_password() -> bool:
    """
    Executes passlib bcrypt verification against a pre-computed dummy hash.
    Used when a target user is not found to ensure constant response times
    and prevent timing-based user enumeration attacks.
    """
    return _pwd_context.verify("DummyPassword123!", _DUMMY_BCRYPT_HASH)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Generate an HS512 JWT access token with claims (sub, email, role, jti, iat, exp, type).
    """
    to_encode = data.copy()
    now = tz.now()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "access",
    })
    return pyjwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate an HS512 JWT access token with claim integrity checks.

    Raises:
        jwt.exceptions.InvalidTokenError: If signature is invalid, token is expired,
            algorithm is disallowed, or mandatory claims are missing/tampered.
    """
    payload: dict = pyjwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={
            "require": ["sub", "jti", "iat", "exp", "type"],
            "verify_iss": False,
        },
    )
    if payload.get("type") != "access":
        raise InvalidTokenError("Invalid token type")
    if not payload.get("sub"):
        raise InvalidTokenError("Subject claim missing or invalid")
    return payload


def generate_refresh_token_string() -> str:
    """Generate a cryptographically secure random token string for refresh tokens."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """
    Compute a SHA-256 hex digest of a refresh token string.
    Ensures refresh tokens are stored securely at rest in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

