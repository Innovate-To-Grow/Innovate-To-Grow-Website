from email.message import EmailMessage
from email.policy import SMTP

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


def _join(lines) -> bytes:
    return CRLF.join(lines).encode("utf-8")
