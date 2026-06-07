from ..preview import HTML_MARKER
from .messages import redact_login_link_urls


def import_message_into_campaign(campaign, message_id: str, mailbox: str | None = None) -> str:
    import apps.mail.services.gmail_import as gmail_api

    html_fragment = redact_login_link_urls(gmail_api.fetch_message_html_fragment(message_id, mailbox=mailbox))
    campaign.body = HTML_MARKER + html_fragment
    campaign.save(update_fields=["body", "updated_at"])
    return campaign.body
