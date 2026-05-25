import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.models import EmailServiceConfig
from core.services.aws.credentials import AwsCredentialsError, resolve_aws_credentials

logger = logging.getLogger(__name__)
REPLY_SEND_FAILURE_MESSAGE = "Failed to send reply. Please check server logs for details."
REPLY_DELIVERY_NOT_CONFIGURED = "Email delivery is not configured. Check Notification Delivery in admin."


def render_reply_html(body_text, original_from="", original_date="", quoted_text=""):
    import re

    from django.conf import settings
    from django.template.loader import render_to_string
    from django.utils.html import escape

    escaped = escape(body_text)

    def _linkify(match):
        url = match.group(1)
        safe = escape(url)
        return f'<a href="{safe}" style="color:#0f2d52;">{safe}</a>'

    escaped = re.sub(r"(https?://[^\s<>&]+)", _linkify, escaped)
    body_html = escaped.replace("\n", "<br>\n")
    safe_quoted = escape(quoted_text).replace("\n", "<br>\n") if quoted_text else ""

    return render_to_string(
        "mail/email/reply_wrapper.html",
        {
            "body": body_html,
            "logo_url": f"{settings.STATIC_URL}images/i2glogo.png",
            "original_from": escape(original_from),
            "original_date": escape(original_date),
            "quoted_text": safe_quoted,
        },
    )


def send_reply(
    *,
    to_email: str,
    subject: str,
    reply_body: str,
    in_reply_to: str = "",
    references: str = "",
    original_from: str = "",
    original_date: str = "",
    quoted_text: str = "",
    cc_email: str = "",
) -> str:
    config = EmailServiceConfig.load()
    cc_list = [email.strip() for email in cc_email.split(",") if email.strip()] if cc_email else []
    html = render_reply_html(reply_body, original_from, original_date, quoted_text)
    message = _build_reply_message(
        config=config,
        to_email=to_email,
        subject=subject,
        html=html,
        cc_list=cc_list,
        in_reply_to=in_reply_to,
        references=references,
    )

    if not config.ses_configured:
        return REPLY_DELIVERY_NOT_CONFIGURED

    return _send_reply_via_ses(config=config, to_email=to_email, cc_list=cc_list, message=message)


def _send_reply_via_ses(*, config, to_email, cc_list, message) -> str:
    try:
        import boto3

        creds = resolve_aws_credentials("ses")
        client = boto3.client(
            "ses",
            region_name=creds.region,
            aws_access_key_id=creds.access_key_id,
            aws_secret_access_key=creds.secret_access_key,
        )
        client.send_raw_email(
            Source=config.source_address,
            Destinations=[to_email] + cc_list,
            RawMessage={"Data": message.as_string()},
        )
        return ""
    except AwsCredentialsError:
        logger.warning("Reply send skipped: AWS credentials are not configured")
        return "AWS IAM is not configured. Cannot send reply."
    except Exception:
        logger.exception("Failed to send reply to %s.", to_email)
        return REPLY_SEND_FAILURE_MESSAGE


def _build_reply_message(
    *,
    config,
    to_email: str,
    subject: str,
    html: str,
    cc_list: list[str],
    in_reply_to: str,
    references: str,
):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = config.source_address
    message["To"] = to_email
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    message.attach(MIMEText(html, "html", "utf-8"))
    return message
