"""
Gmail API service wrapper.

Uses a Google Service Account with Domain-Wide Delegation to access
a Gmail mailbox. Credentials are loaded from the database (GoogleAccount model).

For programmatic email sending from other Django apps, use the convenience
function ``send_email()``::

    from mail.services import send_email

    send_email(
        to="user@example.com",
        subject="Your OTP Code",
        body_html="<p>Your code is <b>123456</b></p>",
    )
"""

import base64
import functools
import json
import logging
import mimetypes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import bleach
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Tags and attributes allowed when sanitizing HTML emails for display
ALLOWED_TAGS = [
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target"],
    "img": ["src", "alt", "width", "height", "style"],
    "div": ["style", "class"],
    "span": ["style", "class"],
    "p": ["style", "class"],
    "td": ["style", "colspan", "rowspan"],
    "th": ["style", "colspan", "rowspan"],
    "table": ["style", "class", "cellpadding", "cellspacing", "border", "width"],
    "tr": ["style"],
    "h1": ["style"],
    "h2": ["style"],
    "h3": ["style"],
    "blockquote": ["style", "class"],
}


class GmailServiceError(RuntimeError):
    """Raised when a Gmail API operation fails."""


def _wrap_api_errors(func):
    """Catch any Google API / auth error and re-raise as GmailServiceError."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except GmailServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GmailServiceError(f"{func.__name__}: {exc}") from exc

    return wrapper


class GmailService:
    """Wraps the Gmail API for inbox, send, reply, forward, and label operations."""

    def __init__(self, account):
        self.account = account
        self._service = None

    def _get_service(self):
        """Build and cache the Gmail API service client."""
        if self._service is not None:
            return self._service

        try:
            credentials_info = json.loads(self.account.service_account_json)
            credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
            delegated_credentials = credentials.with_subject(self.account.email)
            self._service = build("gmail", "v1", credentials=delegated_credentials, cache_discovery=False)
        except Exception as exc:  # noqa: BLE001
            raise GmailServiceError(f"Failed to build Gmail service: {exc}") from exc

        return self._service

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @_wrap_api_errors
    def test_connection(self):
        """Test connectivity by fetching the user's Gmail profile."""
        service = self._get_service()
        profile = service.users().getProfile(userId="me").execute()
        return {
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
            "threads_total": profile.get("threadsTotal"),
            "history_id": profile.get("historyId"),
        }

    @_wrap_api_errors
    def list_messages(self, q="", label_ids=None, max_results=25, page_token=None):
        """
        List messages with optional search query and label filter.

        Returns dict with 'messages' (list of message summaries) and
        'next_page_token' for pagination.
        """
        service = self._get_service()
        kwargs = {"userId": "me", "maxResults": max_results}
        if q:
            kwargs["q"] = q
        if label_ids:
            kwargs["labelIds"] = label_ids
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        messages = response.get("messages", [])
        next_page_token = response.get("nextPageToken")

        # Fetch summary data for each message
        summaries = []
        for msg_stub in messages:
            msg = service.users().messages().get(userId="me", id=msg_stub["id"], format="metadata").execute()
            headers = self._parse_headers(msg)
            summaries.append(
                {
                    "id": msg["id"],
                    "thread_id": msg.get("threadId", ""),
                    "snippet": msg.get("snippet", ""),
                    "label_ids": msg.get("labelIds", []),
                    "is_unread": "UNREAD" in msg.get("labelIds", []),
                    **headers,
                }
            )

        return {"messages": summaries, "next_page_token": next_page_token}

    @_wrap_api_errors
    def get_message(self, message_id):
        """
        Fetch a full message by ID.

        Returns dict with parsed headers, body (HTML and plain text),
        and attachments list.
        """
        service = self._get_service()
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

        headers = self._parse_headers(msg)
        body_html, body_plain = self._get_body(msg.get("payload", {}))
        attachments = self._get_attachments(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "label_ids": msg.get("labelIds", []),
            "is_unread": "UNREAD" in msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
            "body_html": self._sanitize_html(body_html) if body_html else "",
            "body_plain": body_plain or "",
            "attachments": attachments,
            **headers,
        }

    @_wrap_api_errors
    def get_attachment(self, message_id, attachment_id):
        """
        Download an attachment.

        Returns tuple of (filename, bytes_data).
        """
        service = self._get_service()
        # Get the message to find the filename
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        filename = "attachment"
        for att in self._get_attachments(msg.get("payload", {})):
            if att["attachment_id"] == attachment_id:
                filename = att["filename"]
                break

        att_data = (
            service.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id).execute()
        )
        data = base64.urlsafe_b64decode(att_data["data"])
        return filename, data

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    @_wrap_api_errors
    def send_message(
        self,
        to,
        subject,
        body_html,
        cc="",
        bcc="",
        attachments=None,
        thread_id=None,
        in_reply_to=None,
        references=None,
    ):
        """
        Send an email message.

        Args:
            to: Comma-separated recipients
            subject: Email subject
            body_html: HTML body content
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            attachments: Optional list of (filename, content_bytes) tuples
            thread_id: Optional thread ID for threading (reply/forward)
            in_reply_to: Optional Message-ID for In-Reply-To header
            references: Optional References header value

        Returns dict with sent message ID and thread ID.
        """
        service = self._get_service()
        mime_msg = self._build_mime(to, subject, body_html, cc, bcc, attachments, in_reply_to, references)

        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
        body = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id

        sent = service.users().messages().send(userId="me", body=body).execute()
        return {
            "id": sent["id"],
            "thread_id": sent.get("threadId", ""),
        }

    @_wrap_api_errors
    def modify_labels(self, message_id, add_labels=None, remove_labels=None):
        """Add or remove labels from a message."""
        service = self._get_service()
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        return service.users().messages().modify(userId="me", id=message_id, body=body).execute()

    @_wrap_api_errors
    def trash_message(self, message_id):
        """Move a message to trash."""
        service = self._get_service()
        return service.users().messages().trash(userId="me", id=message_id).execute()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_headers(msg):
        """Extract common headers from a Gmail message."""
        headers = msg.get("payload", {}).get("headers", [])
        result = {
            "from": "",
            "to": "",
            "cc": "",
            "subject": "",
            "date": "",
            "message_id": "",
        }
        header_map = {
            "From": "from",
            "To": "to",
            "Cc": "cc",
            "Subject": "subject",
            "Date": "date",
            "Message-ID": "message_id",
            "Message-Id": "message_id",
        }
        for header in headers:
            key = header_map.get(header["name"])
            if key:
                result[key] = header["value"]
        return result

    @staticmethod
    def _get_body(payload):
        """
        Recursively extract text/html and text/plain from MIME parts.

        Returns (html_body, plain_body).
        """
        html_body = ""
        plain_body = ""

        mime_type = payload.get("mimeType", "")

        if mime_type == "text/html":
            data = payload.get("body", {}).get("data", "")
            if data:
                html_body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        elif mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                plain_body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        elif "parts" in payload:
            for part in payload["parts"]:
                h, p = GmailService._get_body(part)
                if h:
                    html_body = h
                if p:
                    plain_body = p

        return html_body, plain_body

    @staticmethod
    def _get_attachments(payload):
        """Extract attachment metadata from MIME parts."""
        attachments = []

        if "parts" not in payload:
            return attachments

        for part in payload["parts"]:
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if filename and attachment_id:
                attachments.append(
                    {
                        "filename": filename,
                        "attachment_id": attachment_id,
                        "mime_type": part.get("mimeType", "application/octet-stream"),
                        "size": body.get("size", 0),
                    }
                )

            # Check nested parts
            if "parts" in part:
                attachments.extend(GmailService._get_attachments(part))

        return attachments

    @staticmethod
    def _sanitize_html(html):
        """Sanitize HTML content for safe display using bleach."""
        return bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        )

    def _build_mime(self, to, subject, body_html, cc="", bcc="", attachments=None, in_reply_to=None, references=None):
        """Construct a MIME message for sending."""
        if attachments:
            msg = MIMEMultipart("mixed")
            html_part = MIMEText(body_html, "html")
            msg.attach(html_part)

            for filename, content_bytes in attachments:
                mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                maintype, subtype = mime_type.split("/", 1)
                attachment = MIMEBase(maintype, subtype)
                attachment.set_payload(content_bytes)
                from email import encoders

                encoders.encode_base64(attachment)
                attachment.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(attachment)
        else:
            msg = MIMEMultipart("alternative")
            html_part = MIMEText(body_html, "html")
            msg.attach(html_part)

        msg["to"] = to
        msg["subject"] = subject
        if self.account.display_name:
            msg["from"] = f"{self.account.display_name} <{self.account.email}>"
        else:
            msg["from"] = self.account.email
        if cc:
            msg["cc"] = cc
        if bcc:
            msg["bcc"] = bcc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        return msg


# ======================================================================
# Public convenience function
# ======================================================================


def send_email(to, subject, body_html, cc="", bcc="", attachments=None, user=None, fail_silently=False):
    """
    Send an email via the active Gmail API account.

    This is the primary entry point for other Django apps to send emails
    (OTP codes, verification links, notifications, etc.).

    Args:
        to: Recipient email address (or comma-separated list).
        subject: Email subject line.
        body_html: HTML body content.
        cc: Optional CC recipients (comma-separated).
        bcc: Optional BCC recipients (comma-separated).
        attachments: Optional list of ``(filename, bytes)`` tuples.
        user: Optional Django user performing the action (for audit log).
        fail_silently: If ``True``, suppress exceptions and return ``None``
                       on failure instead of raising.

    Returns:
        dict with ``id`` and ``thread_id`` of the sent message, or
        ``None`` when ``fail_silently=True`` and sending failed.

    Raises:
        GmailServiceError: When no active account is configured or the
                           Gmail API call fails (unless ``fail_silently``).

    Example::

        from mail.services import send_email

        # Simple OTP email
        send_email(
            to="student@ucmerced.edu",
            subject="Your verification code",
            body_html="<p>Your code is <b>482910</b></p>",
        )
    """
    from mail.models import EmailLog, GoogleAccount  # deferred to avoid circular import

    account = GoogleAccount.get_active()
    if account is None:
        if fail_silently:
            logger.warning("send_email: no active GoogleAccount configured")
            return None
        raise GmailServiceError("No active Gmail API account configured.")

    service = GmailService(account)
    try:
        result = service.send_message(
            to=to,
            subject=subject,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        account.mark_used()
        EmailLog.objects.create(
            account=account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
            gmail_message_id=result.get("id", ""),
            subject=subject[:500],
            recipients=to,
            performed_by=user,
        )
        return result

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        account.mark_used(error=error_msg)
        EmailLog.objects.create(
            account=account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.FAILED,
            subject=subject[:500],
            recipients=to,
            error_message=error_msg,
            performed_by=user,
        )
        if fail_silently:
            logger.exception("send_email failed for %s", to)
            return None
        raise GmailServiceError(f"Failed to send email: {error_msg}") from exc
