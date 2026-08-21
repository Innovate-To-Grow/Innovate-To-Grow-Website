def _normalize_phone_number(country_code, recipient):
    """Build an E.164 number, stripping a leading '+' the admin may have pasted."""
    recipient = recipient.lstrip("+").strip()
    if not recipient:
        return ""
    return country_code + recipient


def _send_test_email(*, config, recipient):
    """Send through the central email facade and return its selected provider."""
    from apps.core.services.email import EmailDeliveryError, EmailMessage, deliver_email

    subject = "Test Email — Innovate to Grow Admin"
    html_body = (
        "<h2>Test Email</h2>"
        "<p>This is a test email sent from the I2G admin panel.</p>"
        "<p>Your email service configuration is working correctly.</p>"
    )

    try:
        deliver_email(EmailMessage(subject=subject, to=(recipient,), html_body=html_body), config=config)
    except EmailDeliveryError as exc:
        raise RuntimeError(str(exc)) from exc
    return config.get_provider_display()


def _send_test_sms(*, phone_number):
    """Send a test SMS via AWS End User Messaging (origination number from active AWSCredentialConfig)."""
    from apps.authn.services.sms import publish_plain_sms

    message_id = publish_plain_sms(
        phone_number=phone_number,
        message="This is a test message from the Innovate to Grow admin panel. Your SMS configuration is working correctly.",
    )
    return f"message (ID: {message_id})"
