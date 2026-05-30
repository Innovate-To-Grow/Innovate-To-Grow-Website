"""Campaign admin custom view mixins."""

from .gmail import CampaignGmailMixin
from .preview import CampaignPreviewMixin
from .send import CampaignSendMixin
from .status import CampaignStatusMixin
from .urls import CampaignUrlsMixin

__all__ = [
    "CampaignGmailMixin",
    "CampaignPreviewMixin",
    "CampaignSendMixin",
    "CampaignStatusMixin",
    "CampaignUrlsMixin",
]
