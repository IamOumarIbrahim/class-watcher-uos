"""
notifications.py - Notification delivery for UoS seat monitor.

Channels:
  1. ntfy push notification (primary)
  2. Windows desktop toast (always shown)
  3. Audible beep (always played)
  4. Gmail (optional, if configured in .env)

No credentials are ever hardcoded. All secrets come from .env / env vars.
"""

from __future__ import annotations

import logging
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

REGISTRATION_URL = (
    "https://reg-prod.ec.sharjah.ac.ae/StudentRegistrationSsb/ssb/classRegistration/classRegistration"
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def send_alert(title: str, body: str, priority: str = "high") -> None:
    """Send an alert via all configured channels."""
    _send_ntfy(title, body, priority)
    _send_windows_toast(title, body)
    _beep(count=3 if priority == "critical" else 1)
    if os.getenv("GMAIL_ENABLED", "false").lower() == "true":
        _send_gmail(title, body)


def send_test_notification() -> None:
    """Send a test notification across all channels."""
    send_alert(
        title="UOS MONITOR TEST",
        body="Notification system is working. Monitor is active.",
        priority="default",
    )


# ---------------------------------------------------------------------------
# ntfy
# ---------------------------------------------------------------------------

def _send_ntfy(title: str, body: str, priority: str) -> None:
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    topic = os.getenv("NTFY_TOPIC", "")
    if not topic:
        logger.warning("NTFY_TOPIC not set — skipping ntfy notification")
        return
    if topic.startswith("<") or topic == "<long-random-private-topic>":
        logger.warning(
            "NTFY_TOPIC is still the placeholder value. "
            "Edit .env and set NTFY_TOPIC to your real private topic name."
        )
        return

    ntfy_priority_map = {
        "critical": "urgent",
        "high": "high",
        "default": "default",
        "low": "low",
    }
    ntfy_priority = ntfy_priority_map.get(priority, "high")

    full_body = f"{body}\n\n{REGISTRATION_URL}"

    try:
        resp = requests.post(
            f"{server}/{topic}",
            data=full_body.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": ntfy_priority,
                "Tags": "rotating_light,university",
            },
            timeout=10,
        )
        if resp.ok:
            logger.info("ntfy notification sent: %s", title)
        else:
            logger.warning("ntfy returned %s: %s", resp.status_code, resp.text[:120])
    except requests.RequestException as exc:
        logger.warning("ntfy request failed: %s", exc)


# ---------------------------------------------------------------------------
# Windows desktop toast
# ---------------------------------------------------------------------------

def _send_windows_toast(title: str, body: str) -> None:
    if sys.platform != "win32":
        return
    try:
        from winotify import Notification, audio  # type: ignore

        toast = Notification(
            app_id="UoS Seat Monitor",
            title=title,
            msg=body,
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        logger.info("Windows toast sent: %s", title)
    except Exception as exc:
        logger.warning("Windows toast failed: %s", exc)


# ---------------------------------------------------------------------------
# Audible beep
# ---------------------------------------------------------------------------

def _beep(count: int = 1) -> None:
    if sys.platform == "win32":
        import winsound

        for _ in range(count):
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.4)
            except Exception as exc:
                logger.debug("Beep failed: %s", exc)
    else:
        print("\a" * count, end="", flush=True)


# ---------------------------------------------------------------------------
# Gmail backup
# ---------------------------------------------------------------------------

def _send_gmail(title: str, body: str) -> None:
    address = os.getenv("GMAIL_ADDRESS", "")
    app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    recipient = os.getenv("ALERT_RECIPIENT", address)

    if not (address and app_password):
        logger.warning("Gmail not fully configured — skipping email")
        return

    msg = MIMEText(f"{body}\n\n{REGISTRATION_URL}")
    msg["Subject"] = title
    msg["From"] = address
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(address, app_password)
            server.send_message(msg)
        logger.info("Gmail notification sent to %s", recipient)
    except Exception as exc:
        logger.warning("Gmail send failed: %s", exc)
