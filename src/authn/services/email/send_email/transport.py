import logging

from botocore.exceptions import BotoCoreError, ClientError

from .config import SMTP_MAX_RETRIES, SMTP_TIMEOUT

logger = logging.getLogger(__name__)


def _load_config():
    from core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _send_via_ses(*, config, recipient: str, subject: str, html_body: str) -> bool:
    if not config.ses_configured:
        return False
    try:
        import authn.services.email.send_email as email_api

        client = email_api.boto3.client(
            "ses",
            region_name=config.ses_region,
            aws_access_key_id=config.ses_access_key_id,
            aws_secret_access_key=config.ses_secret_access_key,
        )
        client.send_email(
            Destination={"ToAddresses": [recipient]},
            Message={
                "Body": {"Html": {"Charset": "UTF-8", "Data": html_body}},
                "Subject": {"Charset": "UTF-8", "Data": subject},
            },
            Source=config.source_address,
        )
        return True
    except (BotoCoreError, ClientError):
        logger.exception("SES send failed while sending email")
        return False


def _send_via_smtp(*, config, recipient: str, subject: str, html_body: str):
    from django.core.mail import get_connection

    import authn.services.email.send_email as email_api

    last_exc = None
    for attempt in range(1, SMTP_MAX_RETRIES + 1):
        try:
            connection = get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend",
                host=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_username,
                password=config.smtp_password,
                use_tls=config.smtp_use_tls,
                fail_silently=False,
                timeout=SMTP_TIMEOUT,
            )
            msg = email_api.EmailMessage(
                subject=subject,
                body=html_body,
                from_email=config.source_address,
                to=[recipient],
                connection=connection,
            )
            msg.content_subtype = "html"
            msg.send()
            return
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SMTP attempt %d/%d failed.",
                attempt,
                SMTP_MAX_RETRIES,
                exc_info=True,
            )
            if attempt < SMTP_MAX_RETRIES:
                email_api.time.sleep(1)
    raise last_exc
