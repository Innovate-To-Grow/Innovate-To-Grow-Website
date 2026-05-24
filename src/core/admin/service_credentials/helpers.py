import logging

from core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

logger = logging.getLogger(__name__)


def _normalize_phone_number(country_code, recipient):
    """Build an E.164 number, stripping a leading '+' the admin may have pasted."""
    recipient = recipient.lstrip("+").strip()
    if not recipient:
        return ""
    return country_code + recipient


def _send_test_email(*, config, recipient):
    """Send a test email using the given EmailServiceConfig. Returns provider name."""
    subject = "Test Email — Innovate to Grow Admin"
    html_body = (
        "<h2>Test Email</h2>"
        "<p>This is a test email sent from the I2G admin panel.</p>"
        "<p>Your email service configuration is working correctly.</p>"
    )

    if config.ses_configured:
        try:
            import boto3

            creds = resolve_aws_credentials("ses")
            client = boto3.client(
                "ses",
                region_name=creds.region,
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
            )
            client.send_email(
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Html": {"Charset": "UTF-8", "Data": html_body}},
                    "Subject": {"Charset": "UTF-8", "Data": subject},
                },
                Source=config.source_address,
            )
            return "SES"
        except AwsCredentialsError:
            logger.warning("SES test send skipped: AWS credentials are not configured")
        except Exception:
            logger.exception("SES test send failed for %s", recipient)

    from django.core.mail import EmailMessage, get_connection

    connection = get_connection(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_username,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        fail_silently=False,
    )
    msg = EmailMessage(
        subject=subject,
        body=html_body,
        from_email=config.source_address,
        to=[recipient],
        connection=connection,
    )
    msg.content_subtype = "html"
    msg.send()
    return "SMTP"


def _send_test_sms(*, phone_number):
    """Send a test SMS using AWS SNS (origination number from active AWSCredentialConfig)."""
    from authn.services.sms import publish_plain_sms

    message_id = publish_plain_sms(
        phone_number=phone_number,
        message="This is a test message from the Innovate to Grow admin panel. Your SMS configuration is working correctly.",
    )
    return f"message (ID: {message_id})"
