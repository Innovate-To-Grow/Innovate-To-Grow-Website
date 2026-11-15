"""Synthetic replies to a campaign, in the shapes real mail systems send them (the repository is public: every person,
organisation and address here is made up). Each builder returns raw RFC 5322 bytes, as Microsoft Graph's ``$value``
would; ``evidence_of`` reads one the way the helpdesk does, for the pure classifier tests.

The helpdesk tests import these too (helpdesk may import core; core never imports the helpdesk).
"""

from email.message import EmailMessage
from email.policy import SMTP

from apps.core.services.email.inbound import Evidence
from apps.core.services.email.inbound import headers as mime

SITE = "i2g@ucmerced.edu"
CAMPAIGN_SUBJECT = "Innovate to Grow 2026: judges wanted"
# The Message-ID Microsoft Graph gave the campaign email the replies answer (the site's OutboundEmail in the tests).
CAMPAIGN_MESSAGE_ID = "<SA1PR12MB0001A2B3C4D5E6F7A8B9@SA1PR12MB0001.namprd12.prod.outlook.com>"
# An automatic reply the site's own mailbox sent (Exchange, when staff switched Automatic Replies on).
SITE_AUTO_REPLY_ID = "<SA1PR12MB0002FEDCBA9876543210@SA1PR12MB0002.namprd12.prod.outlook.com>"
CONTOSO_AUTH = "spf=pass smtp.mailfrom=contoso.example; dkim=pass header.d=contoso.example; dmarc=pass action=none"
QUOTED_CAMPAIGN = (
    "-----Original Message-----\n"
    f"From: Innovate to Grow <{SITE}>\n"
    "Sent: Tuesday, November 10, 2026 9:00 AM\n"
    f"Subject: {CAMPAIGN_SUBJECT}\n\n"
    "We are looking for judges for the December showcase. If you are out of the office that week, or no longer "
    "with your company, just let us know."
)


def message(
    *, sender, subject, text, message_id, to=SITE, reply=True, references=None, headers=None, html=None, parent=None
) -> bytes:
    """``html``: an HTML-only message instead of ``text`` (as some CRM tools send); ``parent``: the Message-ID it
    answers (the campaign email's by default)."""
    mail = EmailMessage(policy=SMTP)
    mail["From"] = sender
    mail["To"] = to
    mail["Subject"] = subject
    mail["Date"] = "Wed, 11 Nov 2026 16:20:00 +0000"
    if message_id:
        mail["Message-ID"] = message_id
    if reply:
        mail["In-Reply-To"] = parent or CAMPAIGN_MESSAGE_ID
        mail["References"] = references or parent or CAMPAIGN_MESSAGE_ID
    for name, value in (headers or {}).items():
        mail[name] = value
    if html is not None:
        mail.set_content(html, subtype="html")
    else:
        mail.set_content(text)
    return mail.as_bytes()


def exchange_oof_english(**overrides) -> bytes:
    """Exchange Online's automatic reply ("Automatic Replies" in Outlook), with an alternate contact."""
    values = {
        "sender": "Alex Kim <alex.kim@contoso.example>",
        "subject": f"Automatic reply: {CAMPAIGN_SUBJECT}",
        "text": "Thank you for your message. I am out of the office until Monday, November 16, with limited access to "
        "email.\n\nFor urgent matters, please contact Jordan Lee at jordan.lee@contoso.example.\n\nAlex",
        "message_id": "<oof-alex-1@contoso.example>",
        "headers": {
            "Auto-Submitted": "auto-generated",
            "X-Auto-Response-Suppress": "All",
            "Thread-Topic": CAMPAIGN_SUBJECT,
            "Content-Language": "en-US",
            "Authentication-Results": CONTOSO_AUTH,
            "X-Microsoft-Antispam": "BCL:0;",
        },
    }
    return message(**{**values, **overrides})


def exchange_oof_spanish() -> bytes:
    return message(
        sender="María López <maria.lopez@empresa.example>",
        subject="Respuesta automática: Innovate to Grow 2026: se buscan jueces",
        text="Gracias por su mensaje. Me encuentro fuera de la oficina hasta el lunes 16 de noviembre, con acceso "
        "limitado a mi correo.\n\nPara asuntos urgentes, comuníquese con Carlos Ruiz: carlos.ruiz@empresa.example."
        "\n\nSaludos,\nMaría",
        message_id="<oof-maria-1@empresa.example>",
        headers={"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All", "Content-Language": "es-MX"},
    )


def gmail_vacation_spanish() -> bytes:
    """Gmail's vacation responder: the subject is the person's own, so only the headers and the words tell."""
    return message(
        sender="Luis Herrera <luis.herrera@gmail.example>",
        subject="Re: Innovate to Grow 2026: se buscan jueces",
        text="Hola: estoy de vacaciones y regreso el 20 de noviembre. Responderé su correo a mi regreso.",
        message_id="<vacation-luis-1@gmail.example>",
        headers={"Auto-Submitted": "auto-replied", "Precedence": "bulk"},
    )


def left_with_contact() -> bytes:
    """IT set an automatic reply on a departed employee's mailbox, naming who to contact instead."""
    return message(
        sender="Jordan Park <jordan.park@contoso.example>",
        subject=f"Automatic reply: {CAMPAIGN_SUBJECT}",
        text="Thank you for your email. Jordan Park is no longer with Contoso Engineering.\n\nFor anything related to "
        "university partnerships, please contact Riley Chen at riley.chen@contoso.example.\n\nThis mailbox is not "
        "monitored.",
        message_id="<left-jordan-1@contoso.example>",
        headers={"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"},
    )


def left_with_new_address() -> bytes:
    return message(
        sender="Jordan Park <jordan.park@contoso.example>",
        subject=f"Automatic reply: {CAMPAIGN_SUBJECT}",
        text="Hello, I have left Contoso. My new email address is jordan.park@newco.example; please update your "
        "records.\n\nJordan",
        message_id="<left-jordan-2@contoso.example>",
        headers={"Auto-Submitted": "auto-replied"},
    )


def left_without_contact() -> bytes:
    return message(
        sender="Taylor Brooks <taylor.brooks@fabrikam.example>",
        subject=f"Automatic reply: {CAMPAIGN_SUBJECT}",
        text="Thank you for your email. Taylor Brooks no longer works at Fabrikam, and this mailbox is no longer "
        "monitored.",
        message_id="<left-taylor-1@fabrikam.example>",
        headers={"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"},
    )


def left_spanish() -> bytes:
    return message(
        sender="Ana Torres <ana.torres@constructora.example>",
        subject="Respuesta automática: Innovate to Grow 2026: se buscan jueces",
        text="Gracias por su mensaje. Ana Torres ya no trabaja en Constructora Ejemplo. Por favor, escriba a "
        "contacto@constructora.example para cualquier asunto.",
        message_id="<left-ana-1@constructora.example>",
        headers={"Auto-Submitted": "auto-generated"},
    )


def left_by_exchange_rule() -> bytes:
    """A reply an Exchange Inbox rule sends ("have server reply using a specific message"): its own subject, and no
    Auto-Submitted header, only Exchange's rule marker."""
    return message(
        sender="Jordan Park <jordan.park@contoso.example>",
        subject="Jordan Park has left Contoso",
        text="Jordan Park has left the company. Please send future correspondence to partnerships@contoso.example.",
        message_id="<rule-jordan-1@contoso.example>",
        headers={"X-MS-Exchange-Inbox-Rules-Loop": "jordan.park@contoso.example"},
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


def evidence_of(raw: bytes, *, replies_to_site_mail: bool = False) -> Evidence:
    """What the classifier reads of ``raw``, as the helpdesk's parser gives it (a single text part here)."""
    parsed = mime.parse(raw)
    headers = mime.header_map(parsed)
    sender = mime.addresses(mime.first(headers, "from"), limit=1)
    payload = parsed.get_payload(decode=True) or b""
    return Evidence(
        headers=headers,
        from_address=sender[0][1] if sender else "",
        from_name=sender[0][0] if sender else "",
        subject=mime.decoded(mime.first(headers, "subject")),
        text_head=payload.decode(parsed.get_content_charset() or "utf-8")[:4096],
        replies_to_site_mail=replies_to_site_mail,
    )
