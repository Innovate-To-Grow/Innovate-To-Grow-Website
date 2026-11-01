"""Gmail API (Google Workspace) email provider: ``messages.send`` through the media upload, as the impersonated user."""

import json
import logging
import re

from django.conf import settings

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.models.base.service_credentials.gmail_api import (
    KEY_ID_RE,
    SERVICE_ACCOUNT_EMAIL_RE,
    VERSION_ID_RE,
    GmailApiProviderConfig,
    is_subject,
)
from apps.core.services.delivery_rates import external_recipients, mailbox_identity, none, uncertain

from ..contracts import DeliveryResult, EmailMessage
from ..exceptions import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
    with_signal,
)
from . import auth, compose, transport
from .errors import error_reason, send_error, shown_reason
from .subject import AllowedSubject, require_issued

logger = logging.getLogger(__name__)

MIME_CONTENT_TYPE = "message/rfc822"
_GMAIL_ID_RE = re.compile(r"[A-Za-z0-9]{1,64}")


class GmailProvider:
    """Deliver messages with the Gmail API as one allow-listed Workspace user, From that same user.

    The caller (the registry) has checked the subject against the allow-list; this class re-checks that every value
    from the database is well formed and that the From address is the subject. The raw MIME is uploaded as
    ``message/rfc822`` (no base64), and Gmail always files a copy in the subject's Sent: messages that carry a
    credential are tagged (``X-I2G-Mail-Class``) so the inbox and the import never show them, or refused when the
    config says so. A 200 is acceptance only: Google notes that mail accepted near a daily limit may still be
    dropped, which is why the delivery-rate budgets stop below the limits.
    """

    name = "gmail"
    rate_channel = DeliveryChannel.GMAIL_API_SEND

    def __init__(
        self,
        *,
        credential: auth.GmailCredential,
        subject: AllowedSubject,
        from_email: str,
        from_name: str = "",
        max_recipients: int | None = None,
        max_message_bytes: int | None = None,
        credential_mail: str = GmailApiProviderConfig.CredentialMail.SEND,
        timeout: float | None = None,
    ):
        require_issued(subject)
        valid = (
            bool(SERVICE_ACCOUNT_EMAIL_RE.fullmatch(credential.service_account_email or ""))
            and bool(KEY_ID_RE.fullmatch(credential.key_id or ""))
            and bool(VERSION_ID_RE.fullmatch(credential.key_version_id or ""))
            and bool(credential.key_ref)
            and is_subject(subject.address)
        )
        if not valid:
            raise PermanentEmailDeliveryError("Gmail API configuration is invalid.")
        self.credential, self.subject = credential, subject
        self.from_email, self.from_name = from_email, from_name
        # The documented limits in settings are ceilings even for a stored value set before they were lowered.
        limits = settings.GMAIL_API
        self.max_recipients = min(
            max_recipients or limits["max_recipients_per_message"], limits["max_recipients_per_message"]
        )
        self.max_message_bytes = min(max_message_bytes or limits["max_message_bytes"], limits["max_message_bytes"])
        self.credential_mail = credential_mail
        # Whether Gmail's answer to the last accepted send listed the SENT label (the access check expects it).
        self.last_sent_label = None
        self.timeout = auth.request_timeout(timeout)

    def rate_identity(self) -> str:
        """Google's limits are per user account: the impersonated subject."""
        return mailbox_identity(self.subject.address)

    def rate_costs(self, message: EmailMessage) -> dict:
        # Google counts recipients outside the Workspace primary domain (only that domain: not its aliases or
        # subdomains) against the external limit; a blank internal domain counts every recipient as external.
        from apps.core.models import DeliveryRatePolicy

        recipients = message.envelope_recipients
        domain = DeliveryRatePolicy.for_channel(self.rate_channel).internal_domain
        return {
            "budget_cost": max(1, len(recipients)),
            "external_cost": external_recipients(recipients, domain, subdomains=False),
            "message_cost": 1,
        }

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        message_id, payload = self._encode(message)
        access_token, fresh = auth.get_access_token(self.credential, self.subject, timeout=self.timeout)
        if before_provider_call is not None:
            before_provider_call()
        return self._submit(access_token, fresh, payload, message_id)

    def send_with_token(self, message: EmailMessage, access_token: str) -> DeliveryResult:
        """Submit with a token the caller requested itself (the access check's fresh, uncached one)."""
        message_id, payload = self._encode(message)
        return self._submit(access_token, True, payload, message_id)

    def _submit(self, access_token: str, fresh: bool, payload: bytes, message_id: str) -> DeliveryResult:
        """POST the message. Everything after the callback is classified; unexpected errors are Uncertain."""
        try:
            response = self._post(access_token, payload)
            if response.status == 200:
                self.last_sent_label = self._log_accepted(response)
                return DeliveryResult(provider=self.name, message_id=message_id)
            self._log_failure(response)
            if response.status in (401, 403):
                # A fresh token also picks up delegation changes made after this one was issued.
                auth.forget_access_token(self.credential, self.subject)
            raise send_error(response, fresh_token=fresh)
        except EmailDeliveryError:
            raise
        except Exception as exc:
            # Only the exception type is logged: messages may echo request values.
            logger.error("Unexpected %s while sending through the Gmail API", type(exc).__name__)
            raise UncertainEmailDeliveryError("Gmail API request outcome could not be confirmed.") from None

    def _encode(self, message: EmailMessage) -> tuple[str, bytes]:
        return compose.encode(
            message,
            from_email=self.from_email,
            from_name=self.from_name,
            subject=self.subject.address,
            credential_mail=self.credential_mail,
            max_recipients=self.max_recipients,
            max_message_bytes=self.max_message_bytes,
        )

    def _post(self, access_token: str, payload: bytes) -> transport.HttpResponse:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": MIME_CONTENT_TYPE,
            "Accept": "application/json",
        }
        try:
            return transport.post(transport.GMAIL_HOST, transport.SEND_PATH, payload, headers, timeout=self.timeout)
        except transport.ConnectFailed as exc:
            if exc.verification_failed:
                raise PermanentEmailDeliveryError("TLS verification of the Gmail API failed.") from None
            error = TransientEmailDeliveryError("The Gmail API could not be reached before sending.")
            raise with_signal(error, none("unreachable")) from None
        except transport.ResponseLost:
            error = UncertainEmailDeliveryError("The Gmail API response was lost after the request began.")
            raise with_signal(error, uncertain("response_lost")) from None

    @staticmethod
    def _log_accepted(response: transport.HttpResponse) -> bool:
        try:
            data = json.loads(response.body)
        except (ValueError, RecursionError):
            data = {}
        data = data if isinstance(data, dict) else {}
        ids = [
            value if isinstance(value, str) and _GMAIL_ID_RE.fullmatch(value) else "-"
            for value in (
                data.get("id"),
                data.get("threadId"),
            )
        ]
        labels = data.get("labelIds")
        sent = isinstance(labels, list) and "SENT" in labels
        logger.info("Gmail API accepted the message: id=%s thread=%s sent_label=%s", ids[0], ids[1], sent)
        return sent

    @staticmethod
    def _log_failure(response: transport.HttpResponse) -> None:
        # Stored delivery errors stay generic; never log bodies, messages or tokens.
        reason = shown_reason(error_reason(response.body)[0])
        logger.warning("Gmail API send was not accepted: status=%s reason=%s", response.status, reason or "-")
