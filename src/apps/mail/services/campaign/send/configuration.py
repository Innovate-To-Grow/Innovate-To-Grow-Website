"""Resolve the delivery method used by an ordinary campaign or a provenance-bound retry."""

from apps.core.models import EmailServiceConfig
from apps.mail.services.campaign.content.retry_delivery import delivery_config_for_campaign

from .transport import _get_configuration_set_name, _get_ses_client


def load_delivery(campaign=None, config_model=EmailServiceConfig, get_client=_get_ses_client):
    """Delivery now for ordinary mail, or the immutable method/From snapshot retained by a retry."""
    config = delivery_config_for_campaign(campaign) if campaign is not None else config_model.load()
    configuration_set = (
        campaign.retry_configuration_set
        if campaign is not None and campaign.retry_source_campaign_id
        else _get_configuration_set_name(config)
    )
    return config, get_client(config), configuration_set
