"""
SES-backed invitation email for admin registration.
"""

import html

from mail.models import EmailLog, SESAccount, SESEmailLog
from mail.services import SESService, SESServiceError


class InvitationEmailError(RuntimeError):
    """Raised when an invitation email cannot be sent."""


def _render_invitation_email(*, email, role, acceptance_url, inviter_name="", message=""):
    safe_email = html.escape(email)
    safe_url = html.escape(acceptance_url)
    role_label = "administrator" if role == "staff" else "super-administrator"

    message_block = ""
    if message:
        safe_message = html.escape(message).replace("\n", "<br>")
        message_block = f"""
      <div style="margin: 16px 0; padding: 12px 16px; border-left: 3px solid #1e3a5f; background: #f8fafc;">
        <p style="margin: 0; font-size: 14px; color: #6b7280;">Message from {html.escape(inviter_name or "the team")}:</p>
        <p style="margin: 8px 0 0; color: #374151;">{safe_message}</p>
      </div>"""

    subject = "You're invited to join Innovate to Grow as an admin"
    body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827; max-width: 640px; margin: 0 auto;">
      <div style="text-align: center; padding: 24px 0 16px;">
        <span style="font-size: 28px; font-weight: 800; color: #1e3a5f; letter-spacing: 0.02em;">Innovate to Grow</span>
        <span style="display: block; font-size: 13px; color: #6b7280; margin-top: 2px;">UC Merced</span>
      </div>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 0 0 24px;">
      <h2 style="margin-bottom: 8px;">Admin Invitation</h2>
      <p style="margin-top: 0;">
        You've been invited to join <strong>Innovate to Grow</strong> as a <strong>{role_label}</strong>.
      </p>
      {message_block}
      <div style="margin: 24px 0; text-align: center;">
        <a href="{safe_url}"
           style="display: inline-block; padding: 12px 32px; background: #1e3a5f; color: #ffffff;
                  text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px;">
          Accept Invitation
        </a>
      </div>
      <p style="font-size: 13px; color: #6b7280;">
        Or copy this link into your browser:<br>
        <a href="{safe_url}" style="color: #1e3a5f; word-break: break-all;">{safe_url}</a>
      </p>
      <p>This invitation expires in 7 days. If you did not expect this email for {safe_email}, you can ignore it.</p>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0 16px;">
      <p style="font-size: 12px; color: #9ca3af; text-align: center;">Innovate to Grow &mdash; UC Merced</p>
    </div>
    """
    return subject, body


def _log_ses_email(account, status, *, message_id="", subject="", recipients="", error="", performed_by=None):
    """Create both SESEmailLog and EmailLog entries (mirrors admin compose pattern)."""
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
    EmailLog.objects.create(
        account=None,
        action=EmailLog.Action.SEND,
        status=status,
        gmail_message_id=message_id,
        subject=subject[:500] if subject else "",
        recipients=recipients,
        error_message=error,
        performed_by=performed_by,
    )


def send_admin_invitation_email(invitation, request=None):
    account = SESAccount.get_active()
    if account is None:
        raise InvitationEmailError("SES sender is not configured.")

    inviter_name = ""
    if invitation.invited_by:
        inviter_name = invitation.invited_by.get_full_name() or invitation.invited_by.username

    performed_by = invitation.invited_by
    acceptance_url = invitation.get_acceptance_url(request)
    subject, body_html = _render_invitation_email(
        email=invitation.email,
        role=invitation.role,
        acceptance_url=acceptance_url,
        inviter_name=inviter_name,
        message=invitation.message,
    )

    try:
        result = SESService(account).send_message(to=invitation.email, subject=subject, body_html=body_html)
        _log_ses_email(
            account,
            SESEmailLog.Status.SUCCESS,
            message_id=result["id"],
            subject=subject,
            recipients=invitation.email,
            performed_by=performed_by,
        )
        account.mark_used()
        return result
    except SESServiceError as exc:
        error_msg = str(exc)
        _log_ses_email(
            account,
            SESEmailLog.Status.FAILED,
            subject=subject,
            recipients=invitation.email,
            error=error_msg,
            performed_by=performed_by,
        )
        account.mark_used(error=error_msg)
        raise InvitationEmailError(error_msg) from exc
