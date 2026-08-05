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
    """Wrap content in the AutoBrain brand — mirrors the dark futuristic site
    theme (near-black background, electric-blue glow, logo header)."""
    return (
        f'<div style="background:#050505;padding:32px 16px;'
        f'background-image:linear-gradient(rgba(0,183,255,0.04) 1px,transparent 1px),'
        f'linear-gradient(90deg,rgba(0,183,255,0.04) 1px,transparent 1px);'
        f'background-size:44px 44px">'
        f'<div style="max-width:560px;margin:auto">'
        f'<div style="text-align:center;margin-bottom:22px">'
        f'<img src="https://autobrainservice.app/logo.png" alt="AutoBrain logo" '
        f'width="72" height="72" '
        f'style="width:72px;height:72px;border-radius:50%;display:block;margin:0 auto 10px;'
        f'box-shadow:0 0 24px rgba(0,183,255,0.45)">'
        f'<span style="font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:800;'
        f'color:#F5F7FA;letter-spacing:1px">Auto<span style="color:#00B7FF;'
        f'text-shadow:0 0 12px rgba(0,183,255,0.7)">Brain</span></span></div>'
        f'<div style="font-family:Segoe UI,Arial,Helvetica,sans-serif;background:#0B0F16;'
        f'border:1px solid rgba(0,183,255,0.22);border-radius:16px;padding:28px;'
        f'box-shadow:0 0 24px rgba(0,183,255,0.10)">'
        f'{body}'
        f'<p style="color:#9CA3AF;font-size:12px;margin-top:28px;border-top:1px solid rgba(0,183,255,0.18);'
        f'padding-top:14px">Sent by AutoBrain — AI-powered car companion. '
        f'<a href="https://autobrainservice.app" style="color:#00B7FF;text-decoration:none">autobrainservice.app</a></p>'
        f'</div></div></div>'
    )


def _button(link: str, label: str) -> str:
    return (
        f'<a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#00B7FF,#1A4DFF);'
        f'color:#050505;font-weight:700;padding:13px 26px;border-radius:10px;text-decoration:none;'
        f'box-shadow:0 0 20px rgba(0,183,255,0.35)">'
        f'{label}</a>'
    )


async def send_signup_setup(to_email: str, display_name: str, token: str, app_url: str, expiry_days: int = 7) -> None:
    """Self-service signup completion: pick a password + set up MFA."""
    link = f"{app_url}/reset-password?token={token}"
    subject = "Complete your AutoBrain account"
    text = (
        f"Hi {display_name},\n\nYour AutoBrain account has been created on the free tier.\n"
        f"Finish setting it up (choose a password, then add two-factor auth):\n{link}\n\n"
        f"The link expires in {expiry_days} days. If you didn't request this, ignore this email."
    )
    html = _branding(
        f'<p style="color:#F5F7FA"><b>Hi {display_name},</b></p>'
        f'<p style="color:#E5ECF5">Your AutoBrain account has been created on the '
        f'<b style="color:#00B7FF">free tier</b>. Finish setting it up to start tracking your garage:</p>'
        f'<p style="margin:22px 0"><b style="color:#F5F7FA">1.&nbsp;</b> Choose a password<br>'
        f'<b style="color:#F5F7FA">2.&nbsp;</b> Add two-factor authentication (MFA)</p>'
        f'<p>{_button(link, "Create account & set password")}</p>'
        f'<p style="color:#9CA3AF;font-size:12px">Link expires in {expiry_days} days. '
        f"If you didn't request this, you can safely ignore this email.</p>"
    )
    await send_email(to_email, subject, html, text)


async def send_welcome(to_email: str, display_name: str, app_url: str) -> None:
    subject = "Welcome to AutoBrain"
    text = (
        f"Hi {display_name},\n\nYour AutoBrain account has been created.\n"
        f"Log in at {app_url}\n\n"
        "For security, use the password reset option if you were not given credentials."
    )
    html = _branding(
        f'<p style="color:#F5F7FA">Hi <b>{display_name}</b>,</p>'
        f'<p style="color:#E5ECF5">Your AutoBrain account has been created.</p>'
        f'<p>{_button(app_url, "Log in to AutoBrain")}</p>'
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
        f'<p style="color:#F5F7FA">Hi <b>{display_name}</b>,</p>'
        f'<p style="color:#E5ECF5">We received a request to reset your AutoBrain password.</p>'
        f'<p>{_button(link, "Reset password")}</p>'
        f'<p style="color:#9CA3AF;font-size:12px">Link expires in 30 minutes. If you didn\'t request '
        f'this, you can safely ignore this email.</p>'
    )
    await send_email(to_email, subject, html, text)


async def send_account_invite(to_email: str, display_name: str, token: str, app_url: str, expiry_days: int = 7) -> None:
    link = f"{app_url}/reset-password?token={token}"
    subject = "Your AutoBrain account is ready"
    text = (
        f"Hi {display_name},\n\nYour AutoBrain account has been created.\n"
        f"Set your password to activate it:\n{link}\n\n"
        f"The link expires in {expiry_days} days. If you didn't expect this, you can safely ignore this email."
    )
    html = _branding(
        f'<p style="color:#F5F7FA">Hi <b>{display_name}</b>,</p>'
        f'<p style="color:#E5ECF5">An administrator created an AutoBrain account for you.</p>'
        f'<p style="color:#E5ECF5">Set your password to activate it:</p>'
        f'<p>{_button(link, "Create account")}</p>'
        f'<p style="color:#9CA3AF;font-size:12px">Link expires in {expiry_days} days. If you didn\'t '
        f'expect this, you can safely ignore this email.</p>'
    )
    await send_email(to_email, subject, html, text)


async def send_password_changed(to_email: str, display_name: str) -> None:
    subject = "Your AutoBrain password was changed"
    text = f"Hi {display_name},\n\nYour AutoBrain password was successfully changed."
    html = _branding(
        f'<p style="color:#F5F7FA">Hi <b>{display_name}</b>,</p>'
        f'<p style="color:#E5ECF5">Your AutoBrain password was successfully changed.</p>'
    )
    await send_email(to_email, subject, html, text)


async def send_security_alert(to_email: str, display_name: str, event: str) -> None:
    subject = "AutoBrain security update"
    text = f"Hi {display_name},\n\n{event}"
    html = _branding(
        f'<p style="color:#F5F7FA">Hi <b>{display_name}</b>,</p>'
        f'<p style="color:#E5ECF5">{event}</p>'
    )
    await send_email(to_email, subject, html, text)
