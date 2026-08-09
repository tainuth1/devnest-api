"""
OTP (One-Time Password) generation and verification utilities.

Design decisions:
- Uses `secrets.randbelow` (CSPRNG) instead of `random` for cryptographic security.
- Stores OTPs as bcrypt hashes — the same algorithm used for passwords — so even
  if the DB is compromised, an attacker cannot directly reuse stolen OTP hashes.
- A 5-attempt limit + 10-minute expiry makes brute-forcing the 6-digit space
  completely infeasible in practice (at most 5 guesses per 10-minute window).
"""

import secrets
from passlib.context import CryptContext

from app.core.config import settings

# Use a dedicated context so OTP hashes are identifiable separately from passwords
_otp_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_otp() -> str:
    """
    Generate a cryptographically secure numeric OTP of `OTP_LENGTH` digits.

    Returns a zero-padded string so it always has exactly OTP_LENGTH characters.
    Example (OTP_LENGTH=6): "042819"
    """
    upper = 10 ** settings.OTP_LENGTH
    return str(secrets.randbelow(upper)).zfill(settings.OTP_LENGTH)


def hash_otp(otp: str) -> str:
    """Return the bcrypt hash of a plain OTP string for safe DB storage."""
    return _otp_context.hash(otp)


def verify_otp(plain: str, hashed: str) -> bool:
    """
    Verify a plain OTP string against its stored bcrypt hash.

    Returns True if they match, False otherwise.
    """
    return _otp_context.verify(plain, hashed)
