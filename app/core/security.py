"""Security utilities for password hashing and timing attack mitigation."""

import hashlib
import secrets

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


from passlib.context import CryptContext

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


def generate_session_token() -> str:
    """Generate a cryptographically secure random session token string."""
    return secrets.token_urlsafe(64)


def hash_session_token(token: str) -> str:
    """
    Compute a SHA-256 hex digest of a session token string.
    Ensures session tokens are stored securely at rest in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
