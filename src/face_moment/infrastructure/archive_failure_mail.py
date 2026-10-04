"""Configured SMTP adapter; delivery failures never replace the archive outcome."""
from __future__ import annotations

from email.message import EmailMessage
import smtplib
import uuid

from face_moment.infrastructure.settings import Settings

ARCHIVE_FAILURE_ADMIN = 'sergiosandroid2@gmail.com'


class ArchiveFailureMail:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def notify(self, order_id: uuid.UUID) -> None:
        settings = self.settings
        if not settings.archive_mail_host or not settings.archive_mail_from:
            raise RuntimeError('Archive failure mail is not configured')
        message = EmailMessage()
        message['From'] = settings.archive_mail_from
        message['To'] = ARCHIVE_FAILURE_ADMIN
        message['Subject'] = 'Face Moment: archive generation failed'
        message.set_content(f'Archive generation failed for order {order_id}. Manual support is required.')
        with smtplib.SMTP(settings.archive_mail_host, settings.archive_mail_port,
                          timeout=settings.archive_mail_timeout_seconds) as transport:
            if settings.archive_mail_starttls:
                transport.starttls()
            if settings.archive_mail_username:
                transport.login(settings.archive_mail_username, settings.archive_mail_password or '')
            transport.send_message(message)
