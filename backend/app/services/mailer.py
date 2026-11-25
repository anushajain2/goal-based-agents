"""Sending sign-in codes by email.

Uses any SMTP service. If SMTP isn't configured (typical when running on your own laptop),
the code is printed in the backend's terminal instead so you can still sign in. The code is
never sent back to the browser.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("autopilot.mail")


def _message(to: str, code: str) -> EmailMessage:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = f"{code} is your Autopilot sign-in code"
    msg["From"] = settings.smtp_from or settings.smtp_user or "Autopilot <no-reply@localhost>"
    msg["To"] = to
    msg.set_content(
        f"Your Autopilot sign-in code is {code}\n\n"
        "It expires in 10 minutes. If you didn't try to sign in, you can ignore this email; "
        "nobody can sign in without the code.\n"
    )
    msg.add_alternative(
        f"""<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:420px;margin:auto;padding:24px">
  <p style="font-size:15px;color:#1c2b33">Your Autopilot sign-in code is</p>
  <p style="font-size:32px;font-weight:700;letter-spacing:6px;color:#1d4ed8;margin:12px 0">{code}</p>
  <p style="font-size:13px;color:#65676b">It expires in 10 minutes. If you didn't try to sign in, you can ignore
  this email; nobody can sign in without the code.</p>
</div>""",
        subtype="html",
    )
    return msg


def _send_smtp(msg: EmailMessage) -> None:
    s = get_settings()
    context = ssl.create_default_context()
    if s.smtp_ssl:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=context, timeout=20) as smtp:
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=context)
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)


async def send_login_code(to: str, code: str) -> str:
    """Returns "email" when sent, or "console" when printed for local use."""
    if not get_settings().smtp_enabled:
        log.warning(
            "\n\n    Sign-in code for %s: %s\n    (Email isn't set up, so it's shown here instead. "
            "Set SMTP_HOST in .env to email codes.)\n", to, code,
        )
        print(f"\n>>> Autopilot sign-in code for {to}: {code}  (valid 10 minutes)\n", flush=True)
        return "console"
    await asyncio.to_thread(_send_smtp, _message(to, code))
    return "email"


def _simple(to: str, subject: str, text: str) -> EmailMessage:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user or "Autopilot <no-reply@localhost>"
    msg["To"] = to
    msg.set_content(text)
    return msg


async def _send_or_log(to: str, subject: str, text: str) -> None:
    if not get_settings().smtp_enabled:
        log.info("(email not set up) would email %s: %s", to, subject)
        return
    try:
        await asyncio.to_thread(_send_smtp, _simple(to, subject, text))
    except Exception:
        log.exception("could not email %s", to)


async def send_invitation(to: str, org_name: str, inviter: str) -> None:
    url = get_settings().frontend_origin.rstrip("/") + "/login"
    await _send_or_log(
        to, f"{inviter} invited you to {org_name} on Autopilot",
        f"{inviter} invited you to join {org_name} on Autopilot, where AI employees work toward the "
        f"company's goals and check with the right people before doing anything important.\n\n"
        f"You don't need to know anything about AI. Your AI teammates do the work and show it; "
        f"you approve, edit or say no.\n\n"
        f"Sign in with this email address to join: {url}\n",
    )


async def send_approval_needed(recipients: list[str], agent: str, department: str, title: str, goal_id: str) -> None:
    url = get_settings().frontend_origin.rstrip("/") + f"/goals/{goal_id}?tab=work"
    for to in recipients:
        await _send_or_log(
            to, f"{agent} needs your OK: {title}"[:200],
            f"{agent} ({department}) wants to: {title}\n\nAnyone in {department} can approve, edit or decline it:\n{url}\n",
        )
