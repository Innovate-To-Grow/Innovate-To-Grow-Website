from apps.core.tests.services.inbound.samples.base import (
    CAMPAIGN_MESSAGE_ID,
    CAMPAIGN_SUBJECT,
    QUOTED_CAMPAIGN,
    SITE,
    SITE_AUTO_REPLY_ID,
    message,
)


def newsletter() -> bytes:
    """A vendor's marketing newsletter sent through an email service provider (not a reply to anything)."""
    return message(
        sender="Vendor Weekly <news@mail.vendor.example>",
        subject="Your November product update",
        text="New this month: three webinars and a 20% discount. Unsubscribe: https://mail.vendor.example/u/fake-0000",
        message_id="<news-2026-11@mail.vendor.example>",
        reply=False,
        headers={
            "List-Unsubscribe": "<https://mail.vendor.example/u/fake-0000>, <mailto:leave@mail.vendor.example>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            "List-Id": "Vendor Weekly <weekly.mail.vendor.example>",
            "X-SG-EID": "fake-sendgrid-event-0000",
            "Feedback-ID": "1234:5678:weekly:vendor",
            "Precedence": "bulk",
            "X-Microsoft-Antispam": "BCL:8;ARA:13230040;",
        },
    )


def bulk_by_bcl_only(level: int = 7) -> bytes:
    """Marketing mail with no list or provider header: only Exchange's bulk complaint level gives it away."""
    return message(
        sender="Deals <deals@shop.example>",
        subject="This weekend only",
        text="Our best prices of the year.",
        message_id=f"<deal-bcl{level}@shop.example>",
        reply=False,
        headers={"X-Microsoft-Antispam": f"BCL:{level};"},
    )


def crm_reply_about_judging(*, reply: bool = True) -> bytes:
    """A person answering the campaign from Salesforce: CRM headers, an unsubscribe header and a bulk complaint level,
    and the campaign quoted below the answer."""
    return message(
        sender="Morgan Diaz <morgan.diaz@acme-industries.example>",
        subject=f"RE: {CAMPAIGN_SUBJECT}",
        text="Hello Innovate to Grow team,\n\nI would be glad to serve as a judge at the December showcase. I have "
        "fifteen years of experience in process engineering at Acme Industries. Please send me the judge sign-up "
        "details.\n\nBest regards,\nMorgan Diaz\nSenior Engineer, Acme Industries\n\n" + QUOTED_CAMPAIGN,
        message_id="<crm-morgan-1@acme-industries.example>",
        reply=reply,
        headers=CRM_HEADERS,
    )


CRM_HEADERS = {
    "X-SFDC-LK": "00D5e000000FAKE0",
    "X-SFDC-User": "0055e000000FAKE1",
    "List-Unsubscribe": "<mailto:unsubscribe@acme-industries.example?subject=unsubscribe>",
    "X-Microsoft-Antispam": "BCL:7;",
}


# The Message-ID Exchange gave an answer staff wrote to Morgan from the mailbox in Outlook (the site never records it).
STAFF_ANSWER_ID = "<SA1PR12MB0003AABBCCDDEEFF0011@SA1PR12MB0003.namprd12.prod.outlook.com>"


def crm_follow_up_about_judging() -> bytes:
    """Morgan's next message in the same conversation, from the same CRM: it answers staff's answer from Outlook, and
    its References keep only the last two messages (Morgan's first reply and that answer), not the campaign email."""
    return message(
        sender="Morgan Diaz <morgan.diaz@acme-industries.example>",
        subject=f"RE: RE: {CAMPAIGN_SUBJECT}",
        text="Thank you! December 5 works for me. Do judges need to bring anything?\n\nMorgan",
        message_id="<crm-morgan-2@acme-industries.example>",
        parent=STAFF_ANSWER_ID,
        references=f"<crm-morgan-1@acme-industries.example> {STAFF_ANSWER_ID}",
        headers=CRM_HEADERS,
    )


def html_reply_about_judging() -> bytes:
    """A person's HTML-only answer (no plain-text part), quoting the campaign under Outlook's header block."""
    return message(
        sender="Robin Ellis <robin.ellis@northwind.example>",
        subject=f"RE: {CAMPAIGN_SUBJECT}",
        text="",
        html="<html><body><p>Hi team,</p><p>Count me in as a judge for December.</p><p>Robin</p>"
        '<hr style="display:inline-block;width:98%"><div id="divRplyFwdMsg"><b>From:</b> Innovate to Grow '
        f"&lt;{SITE}&gt;<br>\n<b>Sent:</b> Tuesday, November 10, 2026 9:00 AM<br>\n<b>Subject:</b> "
        f"{CAMPAIGN_SUBJECT}</div><p>We are looking for judges for the December showcase. If you are out of the "
        "office that week, or no longer with your company, just let us know.</p></body></html>",
        message_id="<html-robin-1@northwind.example>",
    )


def holiday_closure_notice() -> bytes:
    """An out-of-office reply for a holiday closure that says nobody reads the mailbox meanwhile: no "until" date, no
    "out of the office", so only the wider absence wording tells it from a left-the-organisation notice."""
    return message(
        sender="Casey Nguyen <casey.nguyen@contoso.example>",
        subject=f"Automatic reply: {CAMPAIGN_SUBJECT}",
        text="Thank you for your email. Our office is closed for the Thanksgiving holiday, and this inbox is not being "
        "monitored. For urgent matters, please write to help@contoso.example.",
        message_id="<oof-casey-1@contoso.example>",
        headers={"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"},
    )


def mailing_list_reply() -> bytes:
    """A faculty member answering the campaign to their department's mailing list, which copied the site."""
    return message(
        sender="Sam Rivera <sam.rivera@university.example>",
        to="engineering-faculty@lists.university.example",
        subject=f"Re: {CAMPAIGN_SUBJECT}",
        text="I'm interested in judging this year; count me in.\n\nSam",
        message_id="<list-sam-1@university.example>",
        headers={
            "Cc": SITE,
            "List-Id": "Engineering Faculty <engineering-faculty.lists.university.example>",
            "List-Post": "<mailto:engineering-faculty@lists.university.example>",
            "List-Unsubscribe": "<mailto:engineering-faculty-leave@lists.university.example>",
            "Precedence": "list",
            "Sender": "engineering-faculty-bounces@lists.university.example",
        },
    )


def auto_reply_to_auto_reply() -> bytes:
    """Alex's responder answering the automatic reply the site's mailbox sent to Alex's own automatic reply: the
    start of a mail loop."""
    return message(
        sender="Alex Kim <alex.kim@contoso.example>",
        subject=f"Automatic reply: Automatic reply: {CAMPAIGN_SUBJECT}",
        text="Thank you for your message. I am out of the office until Monday, November 16.",
        message_id="<oof-alex-2@contoso.example>",
        references=f"{CAMPAIGN_MESSAGE_ID} <oof-alex-1@contoso.example> {SITE_AUTO_REPLY_ID}",
        headers={"Auto-Submitted": "auto-replied", "X-Autoreply": "yes"},
    )
