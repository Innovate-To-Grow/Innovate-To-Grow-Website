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
