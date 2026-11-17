"""Signed reviewed sending-method snapshots for one-address retry campaigns."""

from django.core import signing

from apps.core.models import EmailServiceConfig

from .retry import RetryRefused

RETRY_SNAPSHOT_SALT = "mail.email-retry-delivery-snapshot.v1"


def _delivery_snapshot_payload(config) -> dict:
    # Local import avoids loading the campaign runner during Django model startup.
    from ..send.transport import _get_configuration_set_name

    return {
        "config_id": config.pk,
        "provider": config.provider,
        "from_email": config.from_email,
        "from_name": config.from_name,
        "configuration_set": _get_configuration_set_name(config),
    }


def retry_delivery_snapshot_token(config=None) -> str:
    """Signed expected sending-method fields for the retry confirmation form."""
    config = config or EmailServiceConfig.load()
    if not config.pk or not config.is_active:
        return ""
    return signing.dumps(_delivery_snapshot_payload(config), salt=RETRY_SNAPSHOT_SALT, compress=True)


def retry_delivery_snapshot(*, lock: bool = False, expected_token: str = "") -> dict:
    """Values that pin a new retry to the active sending method and From identity reviewed by staff."""
    configs = EmailServiceConfig.objects.filter(is_active=True)
    config = configs.select_for_update().first() if lock else configs.first()
    if config is None or not config.provider or not config.from_email:
        raise RetryRefused("Email delivery must have an active sending method before a retry draft is created.")
    if not expected_token:
        raise RetryRefused("Reload the retry page to review its sending method before creating the draft.")
    try:
        expected = signing.loads(expected_token, salt=RETRY_SNAPSHOT_SALT)
    except signing.BadSignature as exc:
        raise RetryRefused("The reviewed sending-method snapshot is invalid; reload the retry page.") from exc
    current = _delivery_snapshot_payload(config)
    if expected != current:
        raise RetryRefused("The email sending method changed; reload the retry page and review it again.")
    return {
        "retry_email_config": config,
        "retry_sending_provider": config.provider,
        "retry_from_email": config.from_email,
        "retry_from_name": config.from_name,
        "retry_configuration_set": current["configuration_set"],
    }


def delivery_config_for_campaign(campaign) -> EmailServiceConfig:
    """The global delivery choice for ordinary mail, or the immutable method snapshot for a retry."""
    if not campaign.retry_source_campaign_id:
        return EmailServiceConfig.load()
    if not campaign.retry_email_config_id:
        raise RetryRefused("The retry has no sending-method snapshot.")
    return EmailServiceConfig(
        pk=campaign.retry_email_config_id,
        name="Retry sending-method snapshot",
        is_active=True,
        provider=campaign.retry_sending_provider,
        from_email=campaign.retry_from_email,
        from_name=campaign.retry_from_name,
    )
