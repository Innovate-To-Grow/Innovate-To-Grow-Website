"""Microsoft Graph (Outlook / Exchange Online) email provider."""

import base64
import logging
from urllib.parse import quote

from apps.core.models.base.delivery_rates import DeliveryChannel
from apps.core.services.delivery_rates import external_recipients, mailbox_identity
from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from ..contracts import DeliveryResult, EmailMessage
from ..exceptions import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from ..mime import build_mime_message
from . import auth, json_message, transport
from .errors import graph_error_code, request_id, send_mail_error

logger = logging.getLogger(__name__)

GRAPH_HOST = transport.GRAPH_HOST
MIME_CONTENT_TYPE = "text/plain"
SEND_MAIL_PATH = "/v1.0/users/{mailbox}/sendMail"
_TOKEN_REJECTED_STATUSES = (401, 403)


class GraphProvider:
    """Deliver messages with Graph ``sendMail`` using an app-only (client-credentials) token.

    A message is sent as base64 MIME, which keeps every header but always leaves a copy in the sender mailbox's Sent
    Items. A message marked ``keep_sent_copy=False`` (one that carries a credential) is sent as JSON with
    ``saveToSentItems`` false instead; see ``json_message`` for what that form cannot carry.

    The caller (the registry) has already checked that *mailbox* and the From address are inside the configured
    mailbox scope with send permission; this class only re-checks that the values are well formed.

    Graph answers ``202 Accepted`` with an empty body, so it returns no message id; the MIME ``Message-ID`` is
    reported instead (as SMTP does), and a JSON send reports none. A 202 only means the message was queued: later
    transport or recipient failures are delivered as non-delivery reports to the sender mailbox, which this provider
    cannot observe.
    """

    name = "graph"
    rate_channel = DeliveryChannel.GRAPH_SEND

    def __init__(
        self,
        *,
        credential: auth.GraphCredential,
        mailbox: str,
        from_email: str,
        from_name: str = "",
        timeout: float | None = None,
    ):
        # Tenant and mailbox become URL path segments, so rows created outside the validated admin are re-checked.
        valid = (
            is_entra_tenant(credential.tenant_id)
            and is_guid(credential.client_id)
            and is_exchange_mailbox(mailbox)
            and bool(credential.x5t_s256 and credential.key_arn and credential.key_version_id)
        )
        if not valid:
            raise PermanentEmailDeliveryError("Microsoft Graph configuration is invalid.")
        self.credential = credential
        self.mailbox, self.from_email, self.from_name = mailbox, from_email, from_name
        self.timeout = auth.request_timeout(timeout)

    def rate_identity(self) -> str:
        """Exchange limits each sender mailbox (and Outlook each app and mailbox): the URL mailbox."""
        return mailbox_identity(self.mailbox)

    def rate_costs(self, message: EmailMessage) -> dict:
        # Exchange counts every recipient against the mailbox's daily limit; the tenant's outbound spam policy
        # also counts those outside the sender's domain and its subdomains per hour.
        recipients = message.envelope_recipients
        domain = self.from_email.rpartition("@")[2]
        return {
            "budget_cost": max(1, len(recipients)),
            "external_cost": external_recipients(recipients, domain, subdomains=True),
            "message_cost": 1,
        }

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        message_id, payload, content_type = self._encode(message)
        access_token = auth.get_access_token(self.credential, timeout=self.timeout)
        if before_provider_call is not None:
            before_provider_call()
        return self._submit(access_token, payload, content_type, message_id)

    def _submit(self, access_token: str, payload: bytes, content_type: str, message_id: str) -> DeliveryResult:
        """POST the message. Everything after the callback is classified; unexpected errors are Uncertain."""
        try:
            response = self._post(access_token, payload, content_type)
            if response.status == 202:
                return DeliveryResult(provider=self.name, message_id=message_id)
            self._log_failure(response)
            if response.status in _TOKEN_REJECTED_STATUSES:
                # A fresh token also picks up consent or role changes made after this one was issued.
                auth.forget_access_token(self.credential)
            raise send_mail_error(response)
        except EmailDeliveryError:
            raise
        except Exception as exc:
            # Only the exception type is logged: messages may echo request values.
            logger.error("Unexpected %s while sending through Microsoft Graph", type(exc).__name__)
            raise UncertainEmailDeliveryError("Microsoft Graph request outcome could not be confirmed.") from None

    def _encode(self, message: EmailMessage) -> tuple[str, bytes, str]:
        """The reported message id, the request body and its content type; composition problems are definitive."""
        if not message.keep_sent_copy:
            try:
                body = json_message.send_mail_body(message, from_email=self.from_email, from_name=self.from_name)
            except (ValueError, UnicodeError) as exc:
                raise PermanentEmailDeliveryError("The email could not be composed for Microsoft Graph.") from exc
            return "", body, json_message.CONTENT_TYPE
        if message.bcc:
            # build_mime_message never writes a Bcc header and Graph has no separate envelope, so a Bcc
            # recipient would silently receive nothing.
            raise PermanentEmailDeliveryError("Microsoft Graph does not support Bcc recipients.")
        try:
            mime = build_mime_message(message, from_email=self.from_email, from_name=self.from_name)
            return str(mime["Message-ID"]), base64.b64encode(mime.as_bytes()), MIME_CONTENT_TYPE
        except (ValueError, UnicodeError) as exc:
            raise PermanentEmailDeliveryError("The email could not be composed for Microsoft Graph.") from exc

    def _post(self, access_token: str, payload: bytes, content_type: str) -> transport.HttpResponse:
        path = SEND_MAIL_PATH.format(mailbox=quote(self.mailbox, safe="@"))
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type,
            "Accept": "application/json",
        }
        try:
            return transport.post(GRAPH_HOST, path, payload, headers, timeout=self.timeout)
        except transport.ConnectFailed as exc:
            if exc.verification_failed:
                raise PermanentEmailDeliveryError("TLS verification of Microsoft Graph failed.") from exc
            raise TransientEmailDeliveryError("Microsoft Graph could not be reached before sending.") from exc
        except transport.ResponseLost as exc:
            raise UncertainEmailDeliveryError("Microsoft Graph response was lost after the request began.") from exc

    def _log_failure(self, response: transport.HttpResponse) -> None:
        # Stored delivery errors stay generic; operators get the correlation id here. Never log bodies or tokens.
        logger.warning(
            "Microsoft Graph sendMail was not accepted: status=%s code=%s request_id=%s",
            response.status,
            graph_error_code(response.body) or "-",
            request_id(response.headers) or "-",
        )
