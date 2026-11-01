"""Keep the Sent copies of credential mail out of what the admin inbox and the Gmail import read.

Gmail files a copy of everything it sends in the account's Sent folder (the Gmail API cannot turn that off), so
once the site sends through the Gmail API as the account the inbox and the import read, that folder holds sign-in
codes, login links, invitations and tickets. Such messages carry ``X-I2G-Mail-Class: credential``
(``core.services.email.mime``; callers cannot set it). Every Gmail IMAP read of a Sent folder (the inbox's Sent view,
the whole import) searches without them and drops any that still come back, before anything is listed, opened or
cached.

The header is not authenticated: anyone can put it on a message they send to the account. So it is honoured only
in Sent, which holds nothing but the account's own outgoing mail. Received mail is listed as it always was, tagged
or not, so an outside sender cannot hide a message from staff by tagging it.
"""

from imap_tools import NOT, H

from apps.core.models import EmailServiceConfig, GmailAccessAccount, GmailApiSubject
from apps.core.models.base.service_credentials.gmail_api import normalize_subject
from apps.core.services.email.mime import CREDENTIAL_MAIL_CLASS, MAIL_CLASS_HEADER

# IMAP SEARCH that leaves tagged messages out (RFC 3501 HEADER search).
WITHOUT_CREDENTIAL_MAIL = NOT(header=H(MAIL_CLASS_HEADER, CREDENTIAL_MAIL_CLASS))


def is_credential_mail(message) -> bool:
    """Whether a fetched message is tagged as credential mail (``imap_tools`` headers: lower-case names)."""
    headers = getattr(message, "headers", None)
    if not isinstance(headers, dict):
        return False
    values = headers.get(MAIL_CLASS_HEADER.lower()) or ()
    return any(str(value).strip().lower() == CREDENTIAL_MAIL_CLASS for value in values)


def without_credential_mail(messages) -> list:
    return [message for message in messages if not is_credential_mail(message)]


def sent_copies_kept(mailbox: str = "") -> bool:
    """Whether Sent mail of the Gmail IMAP account may hold the site's credential mail: email is sent through the
    Gmail API, or the account (*mailbox*, else the import account's) is on a Gmail API allow-list."""
    email = EmailServiceConfig.load()
    if email.is_active and email.provider == EmailServiceConfig.Provider.GMAIL:
        return True
    address = normalize_subject(mailbox or GmailAccessAccount.load().mailbox)
    return bool(address) and GmailApiSubject.objects.filter(subject=address).exists()
