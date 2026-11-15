from apps.core.tests.services.email_monitoring.ndr_samples import exchange_ndr
from apps.helpdesk.tests.corpus.base import SITE, _join, message


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
