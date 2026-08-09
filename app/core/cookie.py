"""Cookie utilities for HTTP authentication and session management."""

from fastapi import Response

from app.core.config import settings

REFRESH_COOKIE_NAME = "refresh_token"


def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    """Set HttpOnly secure cookie for the refresh token."""
    max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        max_age=max_age,
        expires=max_age,
        path="/api/auth",
        samesite="strict",
        secure=not settings.DEBUG,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    """Clear the refresh token HttpOnly cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        samesite="strict",
        httponly=True,
        secure=not settings.DEBUG,
    )
