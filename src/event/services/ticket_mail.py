import html
import logging

from django.utils import timezone

from mail.models import SESAccount, SESEmailLog
from mail.services import SESService, SESServiceError

from .ticket_assets import (
    build_frontend_absolute_url,
    build_ticket_login_token,
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
    login_token = build_ticket_login_token(registration.member)
    account_url = build_frontend_absolute_url(f"/ticket-login?token={login_token}", request=request)

    body_html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;max-width:640px;margin:0 auto;">
      <div style="text-align:center;padding:24px 0 16px;">
        <span style="font-size:28px;font-weight:800;color:#1e3a5f;letter-spacing:0.02em;">Innovate to Grow</span>
        <span style="display:block;font-size:13px;color:#6b7280;margin-top:2px;">UC Merced</span>
      </div>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;">
      <h2 style="margin-bottom:8px;">Your event ticket is ready</h2>
      <p style="margin-top:0;">Hi {attendee_name}, you're registered for <strong>{event_name}</strong>.</p>
      <div style="margin:24px 0;padding:16px;border-radius:14px;background:#f8fafc;border:1px solid #dbe3ef;">
        <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#6b7280;">Ticket Code</div>
        <div style="font-size:28px;font-weight:700;color:#003366;margin-top:6px;">{ticket_code}</div>
        <p style="margin:16px 0 0;"><strong>Ticket:</strong> {ticket_name}</p>
        <p style="margin:6px 0 0;"><strong>Date:</strong> {html.escape(event_date)}</p>
        <p style="margin:6px 0 0;"><strong>Location:</strong> {location}</p>
      </div>
      <div style="text-align:center;margin:20px 0;">
        <img src="cid:ticket-barcode" alt="Ticket Barcode" style="max-width:100%;height:auto;">
      </div>
      <p>Present this barcode at the event. A copy is also attached as a PNG file for easy saving or printing.</p>
      <div style="margin:24px 0;">
        <a href="{html.escape(account_url)}"
           style="display:inline-block;padding:12px 18px;background:#daa520;color:#111827;text-decoration:none;border-radius:10px;font-weight:700;">
          View Tickets in My Account
        </a>
        <p style="font-size:12px;color:#6b7280;margin-top:8px;">This link will expire in 30 days. After that, please log in manually.</p>
      </div>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0 16px;">
      <p style="font-size:12px;color:#9ca3af;text-align:center;">Innovate to Grow - UC Merced</p>
    </div>
    """

    barcode_filename = f"{registration.event.slug}-{registration.ticket_code}.png"
    barcode_bytes = generate_ticket_barcode_png_bytes(registration)

    inline_images = [("ticket-barcode", barcode_filename, barcode_bytes)]
    attachments = [(barcode_filename, barcode_bytes)]

    return subject, body_html, attachments, inline_images


def send_event_ticket_email(registration, request=None, performed_by=None):
    account = SESAccount.get_active()
    if account is None:
        registration.ticket_email_error = "SES sender is not configured."
        registration.save(update_fields=["ticket_email_error", "updated_at"])
        raise EventTicketEmailError("SES sender is not configured.")

    subject, body_html, attachments, inline_images = _render_ticket_email(registration, request=request)

    try:
        result = SESService(account).send_message(
            to=registration.attendee_email,
            subject=subject,
            body_html=body_html,
            attachments=attachments,
            inline_images=inline_images,
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
