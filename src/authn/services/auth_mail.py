"""
SES-backed transactional auth mail helpers.
"""

import html

from authn.models.security import EmailAuthChallenge
from mail.models import SESAccount
from mail.services import SESService, SESServiceError


class AuthEmailError(RuntimeError):
    """Raised when a verification email cannot be sent."""


_PURPOSE_COPY = {
    EmailAuthChallenge.Purpose.REGISTER: {
        "subject": "Verify your Innovate to Grow account",
        "heading": "Verify your email",
        "body": "Use this code to finish creating your Innovate to Grow account.",
    },
    EmailAuthChallenge.Purpose.LOGIN: {
        "subject": "Your Innovate to Grow login code",
        "heading": "Login verification code",
        "body": "Use this code to sign in to your Innovate to Grow account.",
    },
    EmailAuthChallenge.Purpose.PASSWORD_RESET: {
        "subject": "Reset your Innovate to Grow password",
        "heading": "Password reset code",
        "body": "Use this code to continue resetting your Innovate to Grow password.",
    },
    EmailAuthChallenge.Purpose.PASSWORD_CHANGE: {
        "subject": "Change your Innovate to Grow password",
        "heading": "Password change code",
        "body": "Use this code to confirm the password change for your Innovate to Grow account.",
    },
    EmailAuthChallenge.Purpose.CONTACT_EMAIL_VERIFY: {
        "subject": "Verify your connected email address",
        "heading": "Verify connected email",
        "body": "Use this code to verify a new email address linked to your Innovate to Grow account.",
    },
    EmailAuthChallenge.Purpose.ADMIN_LOGIN: {
        "subject": "Your Innovate to Grow Admin login code",
        "heading": "Admin login verification code",
        "body": "Use this code to sign in to the Innovate to Grow admin panel.",
    },
}


def _render_auth_email(purpose: str, code: str, email: str) -> tuple[str, str]:
    copy = _PURPOSE_COPY[purpose]
    safe_email = html.escape(email)
    safe_code = html.escape(code)
    subject = copy["subject"]
    body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #111827; max-width: 640px; margin: 0 auto;">
      <div style="text-align: center; padding: 24px 0 16px;">
        <span style="font-size: 28px; font-weight: 800; color: #1e3a5f; letter-spacing: 0.02em;">Innovate to Grow</span>
        <span style="display: block; font-size: 13px; color: #6b7280; margin-top: 2px;">UC Merced</span>
      </div>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 0 0 24px;">
      <h2 style="margin-bottom: 8px;">{copy["heading"]}</h2>
      <p style="margin-top: 0;">{copy["body"]}</p>
      <div style="margin: 24px 0; padding: 16px; border-radius: 12px; background: #f3f4f6; text-align: center;">
        <div style="font-size: 14px; letter-spacing: 0.08em; color: #6b7280; text-transform: uppercase;">Verification code</div>
        <div style="font-size: 32px; font-weight: 700; letter-spacing: 0.28em; margin-top: 8px;">{safe_code}</div>
      </div>
      <p>This code expires in 10 minutes and can only be used once.</p>
      <p>If you did not request this email for {safe_email}, you can ignore it.</p>
      <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0 16px;">
      <p style="font-size: 12px; color: #9ca3af; text-align: center;">Innovate to Grow &mdash; UC Merced</p>
    </div>
    """
    return subject, body


def send_auth_code_email(*, purpose: str, code: str, email: str):
    account = SESAccount.get_active()
    if account is None:
        raise AuthEmailError("SES sender is not configured.")

    subject, body_html = _render_auth_email(purpose, code, email)

    try:
        result = SESService(account).send_message(to=email, subject=subject, body_html=body_html)
        account.mark_used()
        return result
    except SESServiceError as exc:
        account.mark_used(error=str(exc))
        raise AuthEmailError(str(exc)) from exc
