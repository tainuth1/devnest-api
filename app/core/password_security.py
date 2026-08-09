"""
Password Security & Breached Password Protection Module.

Provides robust password validation enforcing length, character complexity,
common breached password blocklist filtering, and user-context checks.
"""

import re
from typing import Container


# Top common breached / predictable passwords (lowercase for case-insensitive matching)
COMMON_BREACHED_PASSWORDS: set[str] = {
    "password",
    "password123",
    "password123!",
    "12345678",
    "123456789",
    "1234567890",
    "qwerty123",
    "admin123",
    "admin123!",
    "welcome123",
    "welcome123!",
    "secret123",
    "secret123!",
    "changeme123",
    "letmein123",
    "iloveyou123",
    "monkey123",
    "dragon123",
    "master123",
    "superman123",
}


def is_common_breached_password(password: str) -> bool:
    """Check if password is in the common breached password blocklist."""
    return password.strip().lower() in COMMON_BREACHED_PASSWORDS


def validate_password_strength(
    password: str,
    username: str = "",
    email: str = "",
) -> str:
    """
    Validate password strength

    Checks:
    1. Minimum length (8 characters).
    2. Character complexity: uppercase letter, lowercase letter, digit, special character.
    3. Common breached password blocklist.
    4. Contextual checks: password cannot contain username or email local-part.

    Returns:
        The validated password string if valid.

    Raises:
        ValueError: If password fails any strength check.
    """
    errors: list[str] = []

    if len(password) < 8:
        errors.append("be at least 8 characters long")

    if not any(c.isupper() for c in password):
        errors.append("contain at least one uppercase letter")

    if not any(c.islower() for c in password):
        errors.append("contain at least one lowercase letter")

    if not any(c.isdigit() for c in password):
        errors.append("contain at least one digit")

    if not any(not c.isalnum() for c in password):
        errors.append("contain at least one special character (e.g. !@#$%^&*)")

    if errors:
        raise ValueError("Password must: " + ", ".join(errors) + ".")

    # Common breached password check
    if is_common_breached_password(password):
        raise ValueError(
            "This password is too common and easily guessed. Please choose a more secure password."
        )

    # Contextual check: user details in password
    password_lower = password.lower()
    if username and len(username) >= 3 and username.lower() in password_lower:
        raise ValueError("Password must not contain your username.")

    if email:
        email_prefix = email.split("@")[0].lower()
        if len(email_prefix) >= 3 and email_prefix in password_lower:
            raise ValueError("Password must not contain your email address.")

    return password
