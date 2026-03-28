"""
Gmail API service wrapper and public send helper.
"""

import base64
import functools
import logging

from .gmail_support import (
    build_mime_message,
    build_service,
    extract_attachments,
    extract_body,
    list_message_summaries,
    parse_headers,
    sanitize_html,
)

logger = logging.getLogger(__name__)


class GmailServiceError(RuntimeError):
    """Raised when a Gmail API operation fails."""


def _wrap_api_errors(func):
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
        if self._service is not None:
            return self._service
        try:
            self._service = build_service(self.account)
        except Exception as exc:  # noqa: BLE001
            raise GmailServiceError(f"Failed to build Gmail service: {exc}") from exc
        return self._service

    @_wrap_api_errors
    def test_connection(self):
        profile = self._get_service().users().getProfile(userId="me").execute()
        return {
            "email": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal"),
            "threads_total": profile.get("threadsTotal"),
            "history_id": profile.get("historyId"),
        }

    @_wrap_api_errors
    def list_messages(self, q="", label_ids=None, max_results=25, page_token=None):
        return list_message_summaries(
            self._get_service(),
            q=q,
            label_ids=label_ids,
            max_results=max_results,
            page_token=page_token,
            logger=logger,
        )

    @_wrap_api_errors
    def get_message(self, message_id):
        msg = self._get_service().users().messages().get(userId="me", id=message_id, format="full").execute()
        body_html, body_plain = extract_body(msg.get("payload", {}))
        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "label_ids": msg.get("labelIds", []),
            "is_unread": "UNREAD" in msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
            "body_html": sanitize_html(body_html) if body_html else "",
            "body_plain": body_plain or "",
            "attachments": extract_attachments(msg.get("payload", {})),
            **parse_headers(msg),
        }

    @_wrap_api_errors
    def get_attachment(self, message_id, attachment_id):
        service = self._get_service()
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        filename = next(
            (
                attachment["filename"]
                for attachment in extract_attachments(msg.get("payload", {}))
                if attachment["attachment_id"] == attachment_id
            ),
            "attachment",
        )
        data = (
            service.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id).execute()
        )
        return filename, base64.urlsafe_b64decode(data["data"])

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
        mime_msg = build_mime_message(
            self.account,
            to=to,
            subject=subject,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            in_reply_to=in_reply_to,
            references=references,
        )
        body = {"raw": base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()}
        if thread_id:
            body["threadId"] = thread_id
        sent = self._get_service().users().messages().send(userId="me", body=body).execute()
        return {"id": sent["id"], "thread_id": sent.get("threadId", "")}

    @_wrap_api_errors
    def modify_labels(self, message_id, add_labels=None, remove_labels=None):
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        return self._get_service().users().messages().modify(userId="me", id=message_id, body=body).execute()

    @_wrap_api_errors
    def trash_message(self, message_id):
        return self._get_service().users().messages().trash(userId="me", id=message_id).execute()


def send_email(to, subject, body_html, cc="", bcc="", attachments=None, user=None, fail_silently=False):
    from mail.models import EmailLog, GoogleAccount

    account = GoogleAccount.get_active()
    if account is None:
        if fail_silently:
            logger.warning("send_email: no active GoogleAccount configured")
            return None
        raise GmailServiceError("No active Gmail API account configured.")

    try:
        result = GmailService(account).send_message(
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
