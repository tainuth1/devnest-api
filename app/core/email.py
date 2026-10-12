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


async def send_project_invitation_email(
    to_email: str,
    project_name: str,
    inviter_name: str,
    role: str,
    invitation_token: str,
) -> None:
    """Send project collaboration invitation email with 7-day expiration deadline."""
    invitation_url = f"{settings.FRONTEND_URL}/invitations/{invitation_token}"
    subject = f"You've been invited to join {project_name} on {settings.APP_NAME}"
    text_content = (
        f"Hello,\n\n"
        f"{inviter_name} has invited you to collaborate on the project '{project_name}' "
        f"with the role of {role} on {settings.APP_NAME}.\n\n"
        f"To accept this invitation and get started, click the link below:\n"
        f"{invitation_url}\n\n"
        f"Invitation Token: {invitation_token}\n\n"
        f"This invitation link will expire in 7 days.\n\n"
        f"If you do not recognize this request or do not wish to join, you can safely ignore this email.\n\n"
        f"Best regards,\nThe {settings.APP_NAME} Team"
    )
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }}
    .container {{ max-width: 560px; margin: 0 auto; background-color: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 32px; }}
    .header {{ font-size: 20px; font-weight: 700; color: #38bdf8; margin-bottom: 20px; }}
    .body-text {{ font-size: 15px; line-height: 1.6; color: #cbd5e1; margin-bottom: 24px; }}
    .badge {{ display: inline-block; background-color: #3b82f6; color: #ffffff; padding: 4px 10px; border-radius: 6px; font-size: 13px; font-weight: 600; text-transform: uppercase; }}
    .btn {{ display: inline-block; background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px; margin: 16px 0; }}
    .footer {{ font-size: 12px; color: #64748b; margin-top: 32px; border-top: 1px solid #334155; padding-top: 16px; }}
    .token-box {{ background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px 14px; font-family: monospace; font-size: 13px; color: #94a3b8; word-break: break-all; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">{settings.APP_NAME} Collaboration</div>
    <div class="body-text">
      <strong>{inviter_name}</strong> has invited you to collaborate on <strong>{project_name}</strong> as an <span class="badge">{role}</span>.
    </div>
    <div>
      <a href="{invitation_url}" class="btn" target="_blank">Accept Invitation</a>
    </div>
    <div class="body-text" style="margin-top: 20px;">
      Or paste this invitation token directly:
      <div class="token-box">{invitation_token}</div>
    </div>
    <div class="body-text" style="font-size: 13px; color: #94a3b8; margin-top: 16px;">
      ⏳ This invitation will expire in 7 days.
    </div>
    <div class="footer">
      If you did not expect this invitation, you can safely ignore this email.
    </div>
  </div>
</body>
</html>"""
    await send_email(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        html_content=html_content,
    )


async def send_ownership_transfer_proposal_email(
    to_email: str,
    project_name: str,
    owner_name: str,
    project_code: str,
    recipient_name: str | None = None,
) -> None:
    """Send project ownership transfer proposal notification email with 48-hour expiration."""
    settings_url = f"{settings.FRONTEND_URL}/workspace/projects/{project_code}/settings"
    subject = f"Action Required: Project Ownership Transfer for {project_name} — {settings.APP_NAME}"
    text_content = (
        f"Hello,\n\n"
        f"{owner_name} has proposed transferring ownership of the project '{project_name}' to you on {settings.APP_NAME}.\n\n"
        f"As Project Owner, you will assume full administrative control of this project.\n\n"
        f"To review and accept or decline this transfer request, visit your project settings:\n"
        f"{settings_url}\n\n"
        f"⏳ This request will automatically expire in 48 hours.\n\n"
        f"Best regards,\nThe {settings.APP_NAME} Team"
    )
    await send_email(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        recipient_name=recipient_name or to_email,
    )


async def send_ownership_transfer_completed_email(
    to_email: str,
    project_name: str,
    new_owner_name: str,
    project_code: str,
    recipient_name: str | None = None,
) -> None:
    """Send project ownership transfer completion notification email."""
    team_url = f"{settings.FRONTEND_URL}/workspace/projects/{project_code}/team"
    subject = f"Ownership Transfer Completed: {project_name} — {settings.APP_NAME}"
    text_content = (
        f"Hello,\n\n"
        f"Project ownership of '{project_name}' has been successfully transferred to {new_owner_name}.\n\n"
        f"Your role has been transitioned to Admin to ensure continued working access without interruption.\n\n"
        f"View project team:\n{team_url}\n\n"
        f"Best regards,\nThe {settings.APP_NAME} Team"
    )
    await send_email(
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        recipient_name=recipient_name or to_email,
    )


