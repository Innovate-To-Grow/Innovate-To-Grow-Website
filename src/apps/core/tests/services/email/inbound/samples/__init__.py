"""Synthetic replies to a campaign, in the shapes real mail systems send them (the repository is public: every person,
organisation and address here is made up). Each builder returns raw RFC 5322 bytes, as Microsoft Graph's ``$value``
would; ``evidence_of`` reads one the way the helpdesk does, for the pure classifier tests.

The helpdesk tests import these too (helpdesk may import core; core never imports the helpdesk).
"""

from .auto_replies import (
    exchange_oof_english,
    exchange_oof_spanish,
    gmail_vacation_spanish,
    left_by_exchange_rule,
    left_spanish,
    left_with_contact,
    left_with_new_address,
    left_without_contact,
)
from .base import (
    CAMPAIGN_MESSAGE_ID,
    CAMPAIGN_SUBJECT,
    CONTOSO_AUTH,
    QUOTED_CAMPAIGN,
    SITE,
    SITE_AUTO_REPLY_ID,
    evidence_of,
    message,
)
from .replies import (
    CRM_HEADERS,
    STAFF_ANSWER_ID,
    auto_reply_to_auto_reply,
    bulk_by_bcl_only,
    crm_follow_up_about_judging,
    crm_reply_about_judging,
    holiday_closure_notice,
    html_reply_about_judging,
    mailing_list_reply,
    newsletter,
)

__all__ = [
    "auto_reply_to_auto_reply",
    "bulk_by_bcl_only",
    "CAMPAIGN_MESSAGE_ID",
    "CAMPAIGN_SUBJECT",
    "CONTOSO_AUTH",
    "crm_follow_up_about_judging",
    "CRM_HEADERS",
    "crm_reply_about_judging",
    "evidence_of",
    "exchange_oof_english",
    "exchange_oof_spanish",
    "gmail_vacation_spanish",
    "holiday_closure_notice",
    "html_reply_about_judging",
    "left_by_exchange_rule",
    "left_spanish",
    "left_with_contact",
    "left_with_new_address",
    "left_without_contact",
    "mailing_list_reply",
    "message",
    "newsletter",
    "QUOTED_CAMPAIGN",
    "SITE",
    "SITE_AUTO_REPLY_ID",
    "STAFF_ANSWER_ID",
]
