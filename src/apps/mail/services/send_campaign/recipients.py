"""What one campaign recipient's message is personalized with: their names, the login link issued for them and
their one-click unsubscribe URL (shared by the in-process runner and the background email job)."""

from apps.mail.services.tokens.login_links import issue_login_link, sign_in_page_url

from ..tokens.unsubscribe import build_oneclick_unsubscribe_url


class RecipientContext(dict):
    """One recipient's personalization values, plus the login link issued for them (``""`` when none was).

    ``{{login_link}}`` is that issued link for a member, and the sign-in page for a recipient with no member account
    (a Manual Emails address no active member owns), so the tag never renders as nothing.
    """

    def __init__(self, values, *, issued_login_link=""):
        super().__init__(values)
        self.issued_login_link = issued_login_link


def _recipient_context(recipient, campaign):
    issued_login_link = _build_login_link(recipient["member_id"], campaign)
    return RecipientContext(
        {
            "first_name": recipient["first_name"],
            "last_name": recipient["last_name"],
            "full_name": recipient["full_name"],
            "login_link": issued_login_link or sign_in_page_url(),
        },
        issued_login_link=issued_login_link,
    )


def carries_login_link(context, *texts) -> bool:
    """Whether the personalized message holds the login link issued to the recipient, a credential
    (``keep_sent_copy=False``). The sign-in page that stands in for it when none was issued is not one."""
    link = getattr(context, "issued_login_link", "")
    return bool(link) and any(link in text for text in texts)


def _build_login_link(member_id, campaign):
    if not member_id:
        return ""
    return issue_login_link(
        member_id=member_id,
        campaign=campaign,
        validity_days=campaign.login_link_validity_days,
    )


def _unsubscribe_url_for(campaign, recipient):
    if not campaign.include_unsubscribe_header or not recipient["member_id"]:
        return ""
    return build_oneclick_unsubscribe_url(recipient["member_id"])
