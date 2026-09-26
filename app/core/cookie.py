"""Cookie utilities for HTTP session management."""

from fastapi import Response

from app.core.config import settings

SESSION_COOKIE_NAME = "session_id"

# Default session lifetime: 7 days
SESSION_DEFAULT_DAYS = 7
# Extended session lifetime when "Remember Me" is enabled: 30 days
SESSION_REMEMBER_ME_DAYS = 30


def set_session_cookie(response: Response, session_token: str, remember_me: bool = False) -> None:
    """
    Set HttpOnly secure session cookie.

    Args:
        response: FastAPI Response object.
        session_token: Raw (unhashed) session token string.
        remember_me: If True, cookie lasts 30 days; otherwise 7 days.
    """
    days = SESSION_REMEMBER_ME_DAYS if remember_me else SESSION_DEFAULT_DAYS
    max_age = days * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        max_age=max_age,
        expires=max_age,
        path="/",
        samesite="strict",
        secure=not settings.DEBUG,
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session HttpOnly cookie."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="strict",
        httponly=True,
        secure=not settings.DEBUG,
    )
