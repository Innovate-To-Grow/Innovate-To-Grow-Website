"""Microsoft Graph (Outlook / Exchange Online) email provider."""

import base64
import logging
from urllib.parse import quote

from apps.core.utils.security import is_entra_tenant, is_exchange_mailbox, is_guid

from ..contracts import DeliveryResult, EmailMessage
from ..exceptions import (
    EmailDeliveryError,
    PermanentEmailDeliveryError,
    TransientEmailDeliveryError,
    UncertainEmailDeliveryError,
)
from ..mime import build_mime_message
from . import auth, transport
from .errors import graph_error_code, request_id, send_mail_error

logger = logging.getLogger(__name__)

GRAPH_HOST = "graph.microsoft.com"
SEND_MAIL_PATH = "/v1.0/users/{mailbox}/sendMail"
_TOKEN_REJECTED_STATUSES = (401, 403)


class GraphProvider:
    """Deliver base64 MIME messages with Graph ``sendMail`` using an app-only (client-credentials) token.

    Graph answers ``202 Accepted`` with an empty body, so it returns no message id; the MIME ``Message-ID`` is
    reported instead (as SMTP does). A 202 only means the message was queued: later transport or recipient failures
    are delivered as non-delivery reports to the sender mailbox, which this provider cannot observe.
    """

    name = "graph"

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox: str,
        from_email: str,
        from_name: str = "",
        timeout: float = auth.REQUEST_TIMEOUT,
    ):
        # Tenant and mailbox become URL path segments, so rows created outside the validated admin are re-checked.
        valid = is_entra_tenant(tenant_id) and is_guid(client_id) and is_exchange_mailbox(mailbox) and client_secret
        if not valid:
            raise PermanentEmailDeliveryError("Microsoft Graph configuration is invalid.")
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.mailbox, self.from_email, self.from_name, self.timeout = mailbox, from_email, from_name, timeout

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        mime_id, payload = self._encode(message)
        access_token = auth.get_access_token(self.tenant_id, self.client_id, self.client_secret, timeout=self.timeout)
        if before_provider_call is not None:
            before_provider_call()
        return self._submit(access_token, payload, mime_id)

    def _submit(self, access_token: str, payload: bytes, mime_id: str) -> DeliveryResult:
        """POST the message. Everything after the callback is classified; unexpected errors are Uncertain."""
        try:
            response = self._post(access_token, payload)
            if response.status == 202:
                return DeliveryResult(provider=self.name, message_id=mime_id)
            self._log_failure(response)
            if response.status in _TOKEN_REJECTED_STATUSES:
                # A fresh token also picks up consent or role changes made after this one was issued.
                auth.forget_access_token(self.tenant_id, self.client_id, self.client_secret)
            raise send_mail_error(response)
        except EmailDeliveryError:
            raise
        except Exception as exc:
            # Only the exception type is logged: messages may echo request values.
            logger.error("Unexpected %s while sending through Microsoft Graph", type(exc).__name__)
            raise UncertainEmailDeliveryError("Microsoft Graph request outcome could not be confirmed.") from None

    def _encode(self, message: EmailMessage) -> tuple[str, bytes]:
        """The MIME ``Message-ID`` and the base64 request body; composition problems are definitive."""
        if message.bcc:
            # build_mime_message never writes a Bcc header and Graph has no separate envelope, so a Bcc
            # recipient would silently receive nothing.
            raise PermanentEmailDeliveryError("Microsoft Graph does not support Bcc recipients.")
        try:
            mime = build_mime_message(message, from_email=self.from_email, from_name=self.from_name)
            return str(mime["Message-ID"]), base64.b64encode(mime.as_bytes())
        except (ValueError, UnicodeError) as exc:
            raise PermanentEmailDeliveryError("The email could not be composed for Microsoft Graph.") from exc

    def _post(self, access_token: str, payload: bytes) -> transport.HttpResponse:
        path = SEND_MAIL_PATH.format(mailbox=quote(self.mailbox, safe="@"))
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/plain",
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
