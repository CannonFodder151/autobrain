"""Email delivery via SMTP (stdlib smtplib).

Sending is best-effort and never blocks the request — failures are logged and
swallowed so the API still succeeds even if mail is down.
"""

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _enabled() -> bool:
    return bool(settings.SMTP_HOST)


def _send_sync(to_email: str, subject: str, html: str, text: str) -> None:
    from_name = settings.SMTP_FROM_NAME
    from_email = settings.SMTP_FROM_EMAIL
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    if settings.SMTP_USE_TLS:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
        server.starttls(context=ssl.create_default_context())
    else:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20)
    try:
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(from_email, [to_email], msg.as_string())
    finally:
        server.quit()


async def send_email(to_email: str, subject: str, html: str, text: str) -> bool:
    if not _enabled():
        logger.info("smtp_disabled_email_skipped", to=to_email, subject=subject)
        return False
    try:
        await asyncio.to_thread(_send_sync, to_email, subject, html, text)
        logger.info("email_sent", to=to_email, subject=subject)
        return True
    except Exception as exc:
        logger.warning("email_send_failed", to=to_email, subject=subject, error=str(exc))
        return False


def _branding(body: str) -> str:
    return (
        f"<div style=\"font-family:Arial,Helvetica,sans-serif;color:#111;max-width:560px;margin:auto;"
        f"padding:24px\"><div style=\"font-size:22px;font-weight:800;color:#0B6B6A;margin-bottom:16px\">"
        f"AutoBrain</div>{body}"
        f"<p style=\"color:#888;font-size:12px;margin-top:32px\">Sent by AutoBrain — AI-powered car companion.</p></div>"
    )


async def send_welcome(to_email: str, display_name: str, app_url: str) -> None:
    subject = "Welcome to AutoBrain"
    text = (
        f"Hi {display_name},\n\nYour AutoBrain account has been created.\n"
        f"Log in at {app_url}\n\n"
        "For security, use the password reset option if you were not given credentials."
    )
    html = _branding(
        f"<p>Hi <b>{display_name}</b>,</p><p>Your AutoBrain account has been created.</p>"
        f"<p><a href=\"{app_url}\" style=\"color:#0B6B6A\">Log in to AutoBrain</a></p>"
    )
    await send_email(to_email, subject, html, text)


async def send_password_reset(to_email: str, display_name: str, token: str, app_url: str) -> None:
    link = f"{app_url}/reset-password?token={token}"
    subject = "Reset your AutoBrain password"
    text = (
        f"Hi {display_name},\n\nWe received a request to reset your AutoBrain password.\n"
        f"Open this link within 30 minutes to set a new one:\n{link}\n\n"
        "If you didn't request this, you can safely ignore this email."
    )
    html = _branding(
        f"<p>Hi <b>{display_name}</b>,</p>"
        f"<p>We received a request to reset your AutoBrain password.</p>"
        f"<p><a href=\"{link}\" style=\"display:inline-block;background:#0B6B6A;color:#fff;"
        f"padding:12px 20px;border-radius:10px;text-decoration:none\">Reset password</a></p>"
        f"<p style=\"color:#888;font-size:12px\">Link expires in 30 minutes. If you didn't request "
        f"this, you can safely ignore this email.</p>"
    )
    await send_email(to_email, subject, html, text)


async def send_password_changed(to_email: str, display_name: str) -> None:
    subject = "Your AutoBrain password was changed"
    text = f"Hi {display_name},\n\nYour AutoBrain password was successfully changed."
    html = _branding(f"<p>Hi <b>{display_name}</b>,</p><p>Your AutoBrain password was successfully changed.</p>")
    await send_email(to_email, subject, html, text)


async def send_security_alert(to_email: str, display_name: str, event: str) -> None:
    subject = "AutoBrain security update"
    text = f"Hi {display_name},\n\n{event}"
    html = _branding(f"<p>Hi <b>{display_name}</b>,</p><p>{event}</p>")
    await send_email(to_email, subject, html, text)
