"""Standard-library SMTP email provider."""

import smtplib
import ssl
from contextlib import contextmanager, suppress

from .contracts import DeliveryResult, EmailMessage
from .exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError, UncertainEmailDeliveryError
from .mime import build_mime_message


class SMTPProvider:
    """Deliver MIME messages with SMTP, SMTP+STARTTLS, or SMTP-over-SSL."""

    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_email: str,
        from_name: str = "",
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: float = 30,
    ):
        if use_tls and use_ssl:
            raise ValueError("SMTP STARTTLS and SSL cannot both be enabled.")
        self.host, self.port = host, port
        self.from_email, self.from_name = from_email, from_name
        self.username, self.password = username, password
        self.use_tls, self.use_ssl, self.timeout = use_tls, use_ssl, timeout

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        mime = build_mime_message(message, from_email=self.from_email, from_name=self.from_name)
        with _smtp_errors(submitted=False):
            smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
            options = {"timeout": self.timeout}
            if self.use_ssl:
                options["context"] = ssl.create_default_context()
            client = smtp_class(self.host, self.port, **options)

        try:
            with _smtp_errors(submitted=False):
                if self.use_tls:
                    client.starttls(context=ssl.create_default_context())
                if self.username:
                    client.login(self.username, self.password)
            if before_provider_call is not None:
                before_provider_call()
            with _smtp_errors(submitted=True):
                refused = client.send_message(
                    mime,
                    from_addr=self.from_email,
                    to_addrs=list(message.envelope_recipients),
                )
        finally:
            # QUIT and socket cleanup cannot change the already observed send
            # outcome or replace an exception from the caller's callback.
            with suppress(Exception):
                client.quit()
            with suppress(Exception):
                client.close()

        if refused:
            raise UncertainEmailDeliveryError("SMTP accepted the message for only some recipients.")
        return DeliveryResult(provider=self.name, message_id=str(mime["Message-ID"]))


# SMTP reply-code errors with dedicated wording: (types, temporary 4xx message, permanent message), in order.
_SMTP_CODE_MESSAGES = (
    (
        (smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError),
        "SMTP temporarily rejected the sender or authentication.",
        "SMTP rejected the sender or authentication settings.",
    ),
    ((smtplib.SMTPDataError,), "SMTP temporarily rejected the message.", "SMTP rejected the message."),
)


def _connection_lost_error(submitted: bool) -> Exception:
    if submitted:
        return UncertainEmailDeliveryError("SMTP connection was lost after message submission began.")
    return TransientEmailDeliveryError("SMTP server could not be reached.")


def _reply_code_error(exc: smtplib.SMTPResponseException) -> Exception:
    temporary, permanent = next(
        ((temp, perm) for types, temp, perm in _SMTP_CODE_MESSAGES if isinstance(exc, types)),
        ("SMTP temporarily rejected the request.", "SMTP rejected the request."),
    )
    if 400 <= exc.smtp_code < 500:
        return TransientEmailDeliveryError(temporary)
    return PermanentEmailDeliveryError(permanent)


def _classify_smtp_error(exc: OSError, *, submitted: bool) -> Exception:
    """The delivery error for an SMTP or socket failure (every smtplib error is an ``OSError``)."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [response[0] for response in exc.recipients.values()]
        temporary = codes and all(400 <= code < 500 for code in codes)
        error = TransientEmailDeliveryError if temporary else PermanentEmailDeliveryError
        return error("SMTP rejected all recipients.")
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return PermanentEmailDeliveryError("SMTP does not support a required operation.")
    if isinstance(exc, smtplib.SMTPServerDisconnected) or not isinstance(exc, smtplib.SMTPException):
        return _connection_lost_error(submitted)
    if isinstance(exc, smtplib.SMTPResponseException):
        return _reply_code_error(exc)
    if submitted:
        return UncertainEmailDeliveryError("SMTP request outcome could not be confirmed.")
    return PermanentEmailDeliveryError("SMTP request failed.")


@contextmanager
def _smtp_errors(*, submitted: bool):
    """Classify only SMTP operations, leaving caller callbacks untouched."""
    try:
        yield
    except OSError as exc:
        raise _classify_smtp_error(exc, submitted=submitted) from exc
