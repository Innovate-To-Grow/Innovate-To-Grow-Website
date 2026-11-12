"""Synthetic inbound mail for the helpdesk tests, built in the shapes real systems send (the repo is public: no real
person's mail). Each builder returns raw RFC 5322 bytes, as Microsoft Graph's ``$value`` would."""

from email.message import EmailMessage
from email.policy import SMTP

from apps.core.tests.services.email_monitoring.ndr_samples import exchange_ndr

SITE = "i2g@ucmerced.edu"
LOGIN_LINK = "https://i2g.ucmerced.edu/login-link#token=fake-test-token-0000000000"
UNSUBSCRIBE_LINK = "https://api.i2g.ucmerced.edu/mail/unsubscribe/fake-unsubscribe-0000/"
IMPERSONATE_LINK = "https://i2g.ucmerced.edu/impersonate-login#token=fake-test-token-0000000000"
CRLF = "\r\n"


def message(
    *,
    sender="Pat Doe <pat@example.org>",
    to=SITE,
    cc=None,
    subject="Question about the showcase",
    text="Hello, when does the showcase start?",
    html=None,
    message_id="<m1@mail.example.org>",
    in_reply_to=None,
    references=None,
    date="Wed, 11 Nov 2026 10:00:00 +0000",
    headers=None,
    attachments=(),
) -> bytes:
    mail = EmailMessage(policy=SMTP)
    mail["From"] = sender
    mail["To"] = to
    if cc:
        mail["Cc"] = cc
    mail["Subject"] = subject
    mail["Date"] = date
    if message_id:
        mail["Message-ID"] = message_id
    if in_reply_to:
        mail["In-Reply-To"] = in_reply_to
    if references:
        mail["References"] = references
    for name, value in (headers or {}).items():
        mail[name] = value
    mail.set_content(text)
    if html is not None:
        mail.add_alternative(html, subtype="html")
    for filename, data, content_type in attachments:
        maintype, subtype = content_type.split("/")
        mail.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return mail.as_bytes()


def out_of_office(**overrides) -> bytes:
    """An Exchange Online automatic reply to a campaign."""
    values = {
        "sender": "Alex Kim <alex.kim@contoso.example>",
        "subject": "Automatic reply: Innovate to Grow 2026",
        "text": "I am out of the office until Monday, November 16, with limited access to email.",
        "message_id": "<oof-1@contoso.example>",
        "headers": {"Auto-Submitted": "auto-generated", "X-Auto-Response-Suppress": "All"},
    }
    return message(**{**values, **overrides})


def gmail_vacation(**overrides) -> bytes:
    values = {
        "sender": "Sam Lee <sam.lee@gmail.example>",
        "subject": "Re: Innovate to Grow 2026",
        "text": "Thanks for your email. I am on vacation and will return on November 20.",
        "message_id": "<vacation-1@gmail.example>",
        "headers": {"Auto-Submitted": "auto-replied", "Precedence": "bulk"},
    }
    return message(**{**values, **overrides})


def left_organisation(**overrides) -> bytes:
    values = {
        "sender": "Jordan Park <jordan.park@contoso.example>",
        "subject": "Automatic reply: Innovate to Grow 2026",
        "text": "Jordan no longer works at Contoso. Please contact info@contoso.example instead.",
        "message_id": "<left-1@contoso.example>",
        "headers": {"Auto-Submitted": "auto-replied"},
    }
    return message(**{**values, **overrides})


def german_auto_reply() -> bytes:
    return message(
        sender="Kai Bauer <kai.bauer@firma.example>",
        subject="Abwesenheitsnotiz: Innovate to Grow 2026",
        text="Ich bin bis 20. November nicht im Büro.",
        message_id="<abw-1@firma.example>",
    )


def list_mail() -> bytes:
    return message(
        sender="Campus News <news@lists.example.edu>",
        subject="This week on campus",
        text="Events this week ...",
        message_id="<list-1@lists.example.edu>",
        headers={"List-Id": "Campus News <news.lists.example.edu>", "List-Unsubscribe": "<mailto:leave@lists.example>"},
    )


def esp_newsletter() -> bytes:
    return message(
        sender="Vendor <hello@vendor.example>",
        subject="Our November offers",
        message_id="<esp-1@vendor.example>",
        headers={"X-SG-EID": "abc123"},
    )


def spam(scl="9") -> bytes:
    return message(
        sender="Prize Office <winner@lottery.example>",
        subject="You have won",
        text="Claim your prize now.",
        message_id="<spam-1@lottery.example>",
        headers={"X-MS-Exchange-Organization-SCL": scl},
    )


def own_message(*, internal=True) -> bytes:
    headers = {"X-MS-Exchange-Organization-AuthAs": "Internal"} if internal else {}
    return message(
        sender=f"Innovate to Grow <{SITE}>",
        subject="Your sign-in code",
        text="Your code is 123456.",
        message_id="<own-1@ucmerced.edu>",
        headers=headers,
    )


def _join(lines) -> bytes:
    return CRLF.join(lines).encode("utf-8")


def read_receipt() -> bytes:
    return _join(
        [
            "From: Riley Chen <riley.chen@example.org>",
            f"To: {SITE}",
            "Subject: Read: Innovate to Grow 2026",
            "Message-ID: <mdn-1@example.org>",
            "MIME-Version: 1.0",
            'Content-Type: multipart/report; report-type=disposition-notification; boundary="mdn"',
            "",
            "--mdn",
            "Content-Type: text/plain",
            "",
            "Your message was read on Wednesday.",
            "--mdn",
            "Content-Type: message/disposition-notification",
            "",
            "Final-Recipient: rfc822;riley.chen@example.org",
            "Disposition: manual-action/MDN-sent-manually; displayed",
            "--mdn--",
            "",
        ]
    )


def calendar_reply() -> bytes:
    return _join(
        [
            "From: Morgan Diaz <morgan.diaz@example.org>",
            f"To: {SITE}",
            "Subject: Accepted: Judges' briefing",
            "Message-ID: <cal-1@example.org>",
            "MIME-Version: 1.0",
            'Content-Type: multipart/alternative; boundary="cal"',
            "",
            "--cal",
            "Content-Type: text/plain",
            "",
            "Morgan has accepted.",
            "--cal",
            "Content-Type: text/calendar; method=REPLY; charset=utf-8",
            "",
            "BEGIN:VCALENDAR",
            "METHOD:REPLY",
            "END:VCALENDAR",
            "--cal--",
            "",
        ]
    )


def bounce_report(**kwargs) -> bytes:
    return exchange_ndr(**kwargs)


def forwarded(*, inner_text=f"Sign in here: {LOGIN_LINK}") -> bytes:
    """A person forwarding one of the site's emails, which quotes their personal sign-in link."""
    inner = message(
        sender=f"Innovate to Grow <{SITE}>",
        to="pat@example.org",
        subject="Your ticket",
        text=inner_text,
        message_id="<inner-1@ucmerced.edu>",
    )
    outer = EmailMessage(policy=SMTP)
    outer["From"] = "Pat Doe <pat@example.org>"
    outer["To"] = SITE
    outer["Subject"] = "Fwd: Your ticket"
    outer["Message-ID"] = "<fwd-1@mail.example.org>"
    outer["Date"] = "Wed, 11 Nov 2026 10:05:00 +0000"
    outer.set_content("Please see below; my link does not work.")
    from email import message_from_bytes

    outer.add_attachment(message_from_bytes(inner, policy=SMTP))
    return outer.as_bytes()
