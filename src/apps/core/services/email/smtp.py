"""Standard-library SMTP email provider."""

import smtplib
import ssl

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
        submitted = False
        accepted_result = None
        try:
            try:
                smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
                with smtp_class(self.host, self.port, timeout=self.timeout) as client:
                    if self.use_tls:
                        client.starttls(context=ssl.create_default_context())
                    if self.username:
                        client.login(self.username, self.password)
                    if before_provider_call is not None:
                        before_provider_call()
                    submitted = True
                    refused = client.send_message(
                        mime,
                        from_addr=self.from_email,
                        to_addrs=list(message.envelope_recipients),
                    )
                    if not refused:
                        accepted_result = DeliveryResult(provider=self.name, message_id=str(mime["Message-ID"]))
            except (smtplib.SMTPException, OSError):
                # send_message returned confirmed acceptance. A failed QUIT
                # must not invalidate that result or authorize another send.
                if accepted_result is not None:
                    return accepted_result
                raise
        except smtplib.SMTPRecipientsRefused as exc:
            codes = [response[0] for response in exc.recipients.values()]
            error = (
                TransientEmailDeliveryError
                if codes and all(400 <= code < 500 for code in codes)
                else PermanentEmailDeliveryError
            )
            raise error("SMTP rejected all recipients.") from exc
        except (smtplib.SMTPSenderRefused, smtplib.SMTPAuthenticationError) as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientEmailDeliveryError("SMTP temporarily rejected the sender or authentication.") from exc
            raise PermanentEmailDeliveryError("SMTP rejected the sender or authentication settings.") from exc
        except smtplib.SMTPNotSupportedError as exc:
            raise PermanentEmailDeliveryError("SMTP does not support a required operation.") from exc
        except smtplib.SMTPDataError as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientEmailDeliveryError("SMTP temporarily rejected the message.") from exc
            raise PermanentEmailDeliveryError("SMTP rejected the message.") from exc
        except smtplib.SMTPServerDisconnected as exc:
            error = UncertainEmailDeliveryError if submitted else TransientEmailDeliveryError
            detail = (
                "SMTP connection was lost after message submission began."
                if submitted
                else "SMTP server could not be reached."
            )
            raise error(detail) from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientEmailDeliveryError("SMTP temporarily rejected the request.") from exc
            raise PermanentEmailDeliveryError("SMTP rejected the request.") from exc
        except smtplib.SMTPException as exc:
            error = UncertainEmailDeliveryError if submitted else PermanentEmailDeliveryError
            raise error(
                "SMTP request outcome could not be confirmed." if submitted else "SMTP request failed."
            ) from exc
        except (TimeoutError, ConnectionError, OSError) as exc:
            error = UncertainEmailDeliveryError if submitted else TransientEmailDeliveryError
            detail = (
                "SMTP connection was lost after message submission began."
                if submitted
                else "SMTP server could not be reached."
            )
            raise error(detail) from exc

        if refused:
            raise UncertainEmailDeliveryError("SMTP accepted the message for only some recipients.")
        return DeliveryResult(provider=self.name, message_id=str(mime["Message-ID"]))
