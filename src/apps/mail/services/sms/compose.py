"""What one text says: the message with its names and links filled in, then the opt-out footer.

A link placeholder is filled only while links in SMS are allowed (Mail → SMS Settings); otherwise rendering raises
``LinksDisabled`` and nothing is sent. ``{{login_link}}`` and ``{{ticket_link}}`` sign the recipient in with one tap
when personal sign-in links are on and the recipient is a member who may sign in that way; any other recipient gets
the campaign's shared link to the sign-in page, which returns to the same page afterwards. ``{{event_link}}`` is the
campaign's shared link to its event's registration page.
"""

import re

from apps.mail.models import SmsCampaign, SmsConfig
from apps.mail.models.sms_campaign import SMS_LINK_PLACEHOLDERS
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH, get_login_link_redirect_path

from ..campaign.personalize import personalize, uses_placeholder
from .errors import LinksDisabled, SmsSendRefused
from .links import Purpose, event_page_path, issue_personal_link, may_sign_in_by_sms, shared_link, sign_in_path

STOP_RE = re.compile(r"\bstop\b", re.IGNORECASE)
# The names a preview or the composer's counter fills in (the same example the send preview shows).
EXAMPLE_NAMES = {"first_name": "Hongzhe", "last_name": "Xie", "full_name": "Hongzhe Xie"}


def links_used(*texts) -> tuple[str, ...]:
    return tuple(name for name in SMS_LINK_PLACEHOLDERS if uses_placeholder(name, *texts))


def apply_footer(text: str, config: SmsConfig) -> str:
    """``text`` with the opt-out footer on a new line, unless it is off or the text already says STOP."""
    footer = (config.footer_text or "").strip()
    if not config.footer_enabled or not footer or STOP_RE.search(text):
        return text
    return f"{text.rstrip()}\n{footer}"


def name_values(recipient) -> dict[str, str]:
    return {key: recipient.get(key) or "" for key in ("first_name", "last_name", "full_name")}


class CampaignLinks:
    """The links one campaign's texts carry: shared ones made once, personal ones issued per recipient."""

    def __init__(self, campaign: SmsCampaign, config: SmsConfig):
        self.campaign = campaign
        self.config = config
        self.used = links_used(campaign.message)
        self._shared: dict[str, str] = {}

    def values(self, recipient) -> dict[str, str]:
        if not self.used:
            return {}
        if not self.config.links_enabled:
            raise LinksDisabled()
        member = self._personal_member(recipient)
        return {name: self._link(name, member) for name in self.used}

    def _personal_member(self, recipient):
        if not self.config.personal_links_enabled or not recipient.get("member_id"):
            return None
        from apps.authn.models import Member

        member = Member.objects.filter(pk=recipient["member_id"]).first()
        return member if may_sign_in_by_sms(member) else None

    def _destination(self, name: str) -> str:
        if name == "ticket_link":
            event = self.campaign.event
            return event_page_path(event) if event is not None else DEFAULT_LOGIN_REDIRECT_PATH
        return get_login_link_redirect_path(self.campaign)

    def _link(self, name: str, member) -> str:
        days = self.campaign.link_validity_days
        if name == "event_link":
            if self.campaign.event is None:
                raise SmsSendRefused("{{event_link}} needs the campaign's event, and it has none.")
            return self._shared_link(Purpose.EVENT, event_page_path(self.campaign.event), days)
        purpose = Purpose.TICKET if name == "ticket_link" else Purpose.LOGIN
        destination = self._destination(name)
        if member is not None:
            return issue_personal_link(
                purpose=purpose, member=member, redirect_path=destination, validity_days=days, campaign=self.campaign
            )
        return self._shared_link(purpose, sign_in_path(destination), days)

    def _shared_link(self, purpose: str, path: str, days: int) -> str:
        if purpose not in self._shared:
            self._shared[purpose] = shared_link(
                campaign=self.campaign, purpose=purpose, redirect_path=path, validity_days=days
            )
        return self._shared[purpose]


def refuse_unsendable(campaign: SmsCampaign, config: SmsConfig | None = None) -> None:
    """Raise why ``campaign`` cannot be sent now: its links are turned off, or ``{{event_link}}`` has no event."""
    used = links_used(campaign.message)
    if used and not (config or SmsConfig.load()).links_enabled:
        raise LinksDisabled()
    if "event_link" in used and campaign.event_id is None:
        raise SmsSendRefused("{{event_link}} needs the campaign's event, and it has none.")


def render_campaign_text(campaign: SmsCampaign, recipient, *, links: CampaignLinks, config: SmsConfig) -> str:
    """The text ``recipient`` gets (issuing their links). Raises ``LinksDisabled``."""
    values = {**name_values(recipient), **links.values(recipient)}
    return apply_footer(personalize(campaign.message, values), config)


def preview_text(message: str, config: SmsConfig, *, link: str) -> str:
    """``message`` as a recipient would see it, with example names and ``link`` for every link placeholder."""
    values = {**EXAMPLE_NAMES, **dict.fromkeys(SMS_LINK_PLACEHOLDERS, link)}
    return apply_footer(personalize(message, values), config)
