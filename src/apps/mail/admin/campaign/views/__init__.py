"""Campaign admin custom view mixins."""

from .duplicate import CampaignDuplicateMixin
from .gmail import CampaignGmailMixin
from .preview import CampaignPreviewMixin
from .send import CampaignSendMixin
from .status import CampaignStatusMixin
from .urls import CampaignUrlsMixin

__all__ = [
    "CampaignDuplicateMixin",
    "CampaignGmailMixin",
    "CampaignPreviewMixin",
    "CampaignSendMixin",
    "CampaignStatusMixin",
    "CampaignUrlsMixin",
]
