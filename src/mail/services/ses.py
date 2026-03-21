"""
AWS SES service wrapper for admin-triggered outbound email.
"""

import functools
import mimetypes
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses

import boto3
from django.conf import settings
from django.utils.html import strip_tags


class SESServiceError(RuntimeError):
    """Raised when an SES operation fails."""


def _wrap_api_errors(func):
    """Catch boto3/client errors and re-raise as SESServiceError."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SESServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SESServiceError(f"{func.__name__}: {exc}") from exc

    return wrapper


class SESService:
    """Wraps SES raw email sends for the Django Admin compose flow."""

    def __init__(self, account):
        self.account = account
        self._client = None

    def _get_client(self):
        """Build and cache the SES client using SES-specific env settings."""
        if self._client is not None:
            return self._client

        access_key = getattr(settings, "SES_AWS_ACCESS_KEY_ID", "").strip()
        secret_key = getattr(settings, "SES_AWS_SECRET_ACCESS_KEY", "").strip()
        region = getattr(settings, "SES_AWS_REGION", "us-west-2").strip() or "us-west-2"

        if not access_key or not secret_key:
            raise SESServiceError("SES credentials are not configured.")

        self._client = boto3.client(
            "ses",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        return self._client

    @staticmethod
    def _parse_destinations(*recipient_groups):
        """Return a de-duplicated list of email addresses for SES."""
        addresses = []
        seen = set()
        raw_groups = [group for group in recipient_groups if group]

        for _, address in getaddresses(raw_groups):
            normalized = address.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                addresses.append(normalized)

        if not addresses:
            raise SESServiceError("At least one recipient email address is required.")

        return addresses

    def _build_mime(self, to, subject, body_html, cc="", attachments=None, inline_images=None):
        """Construct a MIME message with HTML, optional inline images, and optional attachments.

        ``inline_images`` is a list of ``(cid, filename, content_bytes)`` tuples.
        Referenced in HTML as ``<img src="cid:{cid}">``.
        """
        body_plain = strip_tags(body_html or "")

        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body_plain, "plain", "utf-8"))
        alternative.attach(MIMEText(body_html, "html", "utf-8"))

        if inline_images:
            related = MIMEMultipart("related")
            related.attach(alternative)
            for cid, filename, content_bytes in inline_images:
                mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)
                img_part = MIMEBase(maintype, subtype)
                img_part.set_payload(content_bytes)
                encoders.encode_base64(img_part)
                img_part.add_header("Content-ID", f"<{cid}>")
                img_part.add_header("Content-Disposition", "inline", filename=filename)
                related.attach(img_part)
            body_part = related
        else:
            body_part = alternative

        if attachments:
            msg = MIMEMultipart("mixed")
            msg.attach(body_part)
        else:
            msg = body_part

        from_name = (self.account.display_name or getattr(settings, "SES_FROM_NAME", "")).strip()
        from_email = self.account.email.strip()
        msg["Subject"] = subject
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email

        for filename, content_bytes in attachments or []:
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            maintype, subtype = mime_type.split("/", 1)
            attachment = MIMEBase(maintype, subtype)
            attachment.set_payload(content_bytes)
            encoders.encode_base64(attachment)
            attachment.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(attachment)

        return msg

    @_wrap_api_errors
    def send_message(self, to, subject, body_html, cc="", bcc="", attachments=None, inline_images=None):
        """Send a raw email through SES."""
        client = self._get_client()
        destinations = self._parse_destinations(to, cc, bcc)
        mime_msg = self._build_mime(
            to=to,
            subject=subject,
            body_html=body_html,
            cc=cc,
            attachments=attachments,
            inline_images=inline_images,
        )
        source = (
            formataddr((self.account.display_name, self.account.email))
            if self.account.display_name
            else self.account.email
        )
        send_kwargs = {
            "Source": source,
            "Destinations": destinations,
            "RawMessage": {"Data": mime_msg.as_bytes()},
        }
        config_set = getattr(settings, "SES_CONFIGURATION_SET_NAME", "").strip()
        if config_set:
            send_kwargs["ConfigurationSetName"] = config_set

        response = client.send_raw_email(**send_kwargs)
        message_id = response.get("MessageId", "")
        return {"id": message_id, "message_id": message_id}
