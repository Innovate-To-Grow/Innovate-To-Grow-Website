import html
import logging

from django.utils import timezone

from mail.models import SESAccount, SESEmailLog
from mail.services import SESService, SESServiceError

from .ticket_assets import (
    build_frontend_absolute_url,
    generate_ticket_barcode_png_bytes,
)

logger = logging.getLogger(__name__)


class EventTicketEmailError(RuntimeError):
    """Raised when the event ticket email cannot be sent."""


def _log_ses_email(account, status, *, message_id="", subject="", recipients="", error="", performed_by=None):
    SESEmailLog.objects.create(
        account=account,
        action=SESEmailLog.Action.SEND,
        status=status,
        ses_message_id=message_id,
        subject=subject[:500] if subject else "",
        recipients=recipients,
        error_message=error,
        performed_by=performed_by,
    )


def _render_ticket_email(registration, request=None):
    subject = f"Your {registration.event.name} ticket"
    event_name = html.escape(registration.event.name)
    attendee_name = html.escape(registration.attendee_name)
    ticket_name = html.escape(registration.ticket.name)
    location = html.escape(registration.event.location)
    ticket_code = html.escape(registration.ticket_code)
    event_date = registration.event.date.strftime("%B %d, %Y").replace(" 0", " ")
    event_time = (
        timezone.localtime(
            timezone.make_aware(
                timezone.datetime.combine(
                    registration.event.date,
                    registration.event.time,
                )
            )
        )
        .strftime("%I:%M %p")
        .lstrip("0")
    )
    account_url = build_frontend_absolute_url("/account", request=request)

    body_html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:640px;margin:0 auto;">
      <div style="text-align:center;padding:24px 0 16px;">
        <span style="font-size:28px;font-weight:800;color:#1e3a5f;letter-spacing:0.02em;">i2g</span>
        <span style="display:block;font-size:13px;color:#6b7280;margin-top:2px;">Innovate to Grow</span>
      </div>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;">
      <h2 style="margin-bottom:8px;">Your event ticket is ready</h2>
      <p style="margin-top:0;">Hi {attendee_name}, you're registered for <strong>{event_name}</strong>.</p>
      <div style="margin:24px 0;padding:16px;border-radius:14px;background:#f8fafc;border:1px solid #dbe3ef;">
        <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#6b7280;">Ticket Code</div>
        <div style="font-size:28px;font-weight:700;color:#003366;margin-top:6px;">{ticket_code}</div>
        <p style="margin:16px 0 0;"><strong>Ticket:</strong> {ticket_name}</p>
        <p style="margin:6px 0 0;"><strong>Date:</strong> {html.escape(event_date)}</p>
        <p style="margin:6px 0 0;"><strong>Time:</strong> {html.escape(event_time)}</p>
        <p style="margin:6px 0 0;"><strong>Location:</strong> {location}</p>
      </div>
      <p>Your PDF417 ticket barcode is attached to this email as a PNG file, and you can always see all of your tickets from your account.</p>
      <div style="margin:24px 0;">
        <a href="{html.escape(account_url)}"
           style="display:inline-block;padding:12px 18px;background:#daa520;color:#111827;text-decoration:none;border-radius:10px;font-weight:700;">
          View Tickets in My Account
        </a>
      </div>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">
      <p style="font-size:12px;color:#9ca3af;text-align:center;">Innovate to Grow (i2g) - UC Merced</p>
    </div>
    """

    attachments = [
        (f"{registration.event.slug}-{registration.ticket_code}.png", generate_ticket_barcode_png_bytes(registration)),
    ]

    return subject, body_html, attachments


def send_event_ticket_email(registration, request=None, performed_by=None):
    account = SESAccount.get_active()
    if account is None:
        registration.ticket_email_error = "SES sender is not configured."
        registration.save(update_fields=["ticket_email_error", "updated_at"])
        raise EventTicketEmailError("SES sender is not configured.")

    subject, body_html, attachments = _render_ticket_email(registration, request=request)

    try:
        result = SESService(account).send_message(
            to=registration.attendee_email,
            subject=subject,
            body_html=body_html,
            attachments=attachments,
        )
        _log_ses_email(
            account,
            SESEmailLog.Status.SUCCESS,
            message_id=result["id"],
            subject=subject,
            recipients=registration.attendee_email,
            performed_by=performed_by or registration.member,
        )
        account.mark_used()
        registration.ticket_email_sent_at = timezone.now()
        registration.ticket_email_error = ""
        registration.save(update_fields=["ticket_email_sent_at", "ticket_email_error", "updated_at"])
        return result
    except SESServiceError as exc:
        error_message = str(exc)
        _log_ses_email(
            account,
            SESEmailLog.Status.FAILED,
            subject=subject,
            recipients=registration.attendee_email,
            error=error_message,
            performed_by=performed_by or registration.member,
        )
        account.mark_used(error=error_message)
        registration.ticket_email_error = error_message
        registration.save(update_fields=["ticket_email_error", "updated_at"])
        raise EventTicketEmailError(error_message) from exc
