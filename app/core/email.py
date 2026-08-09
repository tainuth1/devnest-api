import logging
import httpx

from app.core.config import settings
from app.core.sanitize import sanitize_email_field
from app.core.ssrf import safe_fetch

logger = logging.getLogger("app.email")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


# Core Email Dispatcher

async def send_email(
    to_email: str,
    subject: str,
    text_content: str,
    recipient_name: str | None = None,
    html_content: str | None = None,
) -> None:
    """
    Core reusable function to send any email via Brevo's Transactional Email REST API.
    All specific email functions delegate to this method.
    """
    # Sanitize all user-supplied fields before embedding in the email payload
    safe_subject = sanitize_email_field(subject)
    safe_recipient_name = sanitize_email_field(recipient_name or to_email)
    safe_text_content = sanitize_email_field(text_content)

    payload: dict = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "to": [
            {
                "email": to_email,
                "name": safe_recipient_name,
            }
        ],
        "subject": safe_subject,
        "textContent": safe_text_content,
    }

    if html_content:
        payload["htmlContent"] = sanitize_email_field(html_content)

    headers = {
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
        "accept": "application/json",
    }

    response = await safe_fetch(
        url=BREVO_API_URL,
        method="POST",
        json=payload,
        headers=headers,
        timeout=10.0,
    )
    if response.status_code >= 400:
        logger.error(
            "Brevo API error [%s]: %s", response.status_code, response.text
        )
        response.raise_for_status()


    logger.info("Email '%s' sent successfully to %s via Brevo API", safe_subject, to_email)


# Specialized Mailers

async def send_otp_email(to_email: str, username: str, otp_code: str) -> None:
    """Send account registration verification OTP email."""
    text_content = (
        f"Hi {username},\n\n"
        f"Your verification code is: {otp_code}\n\n"
        f"This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes."
    )
    await send_email(
        to_email=to_email,
        subject=f"Your verification code — {settings.APP_NAME}",
        text_content=text_content,
        recipient_name=username,
    )


async def send_password_reset_otp_email(to_email: str, username: str, otp_code: str) -> None:
    """Send password reset verification OTP email."""
    text_content = (
        f"Hi {username},\n\n"
        f"Your password reset verification code is: {otp_code}\n\n"
        f"This code will expire in {settings.OTP_EXPIRE_MINUTES} minutes.\n\n"
        f"If you did not request a password reset, please ignore this email."
    )
    await send_email(
        to_email=to_email,
        subject=f"Password Reset Verification Code — {settings.APP_NAME}",
        text_content=text_content,
        recipient_name=username,
    )


async def send_already_registered_email(to_email: str, username: str) -> None:
    text_content = (
        f"Hi {username},\n\n"
        f"Someone tried to create a new {settings.APP_NAME} account using your email address.\n\n"
        f"If this was you and you forgot your password, you can reset it here:\n"
        f"Use the 'Forgot Password' option on the login page.\n\n"
        f"If you did not attempt to register, you can safely ignore this email.\n\n"
        f"Your account remains secure and no changes have been made."
    )
    await send_email(
        to_email=to_email,
        subject=f"Someone tried to register with your email — {settings.APP_NAME}",
        text_content=text_content,
        recipient_name=username,
    )

