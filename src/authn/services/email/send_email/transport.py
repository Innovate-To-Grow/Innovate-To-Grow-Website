import logging

from botocore.exceptions import BotoCoreError, ClientError

from core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

logger = logging.getLogger(__name__)


def _load_config():
    from core.models import EmailServiceConfig

    return EmailServiceConfig.load()


def _send_via_ses(*, config, recipient: str, subject: str, html_body: str) -> bool:
    if not config.ses_configured:
        return False
    try:
        import authn.services.email.send_email as email_api

        creds = resolve_aws_credentials("ses")
        client = email_api.boto3.client(
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
        return True
    except AwsCredentialsError:
        logger.warning("SES send skipped: AWS credentials are not configured")
        return False
    except (BotoCoreError, ClientError):
        logger.exception("SES send failed while sending email")
        return False
