from email.message import EmailMessage
from email.policy import SMTP

from apps.helpdesk.tests.corpus.base import LOGIN_LINK, SITE, message


def own_message(*, internal=True) -> bytes:
    headers = {"X-MS-Exchange-Organization-AuthAs": "Internal"} if internal else {}
    return message(
        sender=f"Innovate to Grow <{SITE}>",
        subject="Your sign-in code",
        text="Your code is 123456.",
        message_id="<own-1@ucmerced.edu>",
        headers=headers,
    )


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
