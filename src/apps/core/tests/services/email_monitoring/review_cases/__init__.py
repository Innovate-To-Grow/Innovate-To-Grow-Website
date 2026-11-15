"""Bounce reports modelled on the first reports staff reviewed after the switch to Microsoft Graph (November 2026).

**Synthetic.** The repository is public, so every address, host and Message-ID here is made up and every IP address is
from the documentation ranges: each case keeps the shape and wording of a report, not who it was about. The
diagnostic lines are written the way Exchange Online, Gmail, Yahoo and Proofpoint word them; the real ones are on
Email Monitoring → Bounce Reports, which is where the phrase lists should be checked and tuned.

``CASES`` names each case after what the review found; ``expected`` is the verdict the classifier must give.
"""

import hashlib
from dataclasses import dataclass

CRLF = "\r\n"
EXCHANGE_MTA = "SJ0PR01MB0001.namprd01.prod.outlook.com"


def dsn(
    *,
    recipient: str,
    status: str,
    diagnostic: str,
    action: str = "failed",
    remote_mta: str = "",
    reporting_mta: str = EXCHANGE_MTA,
    sender: str = "postmaster@ucmerced.onmicrosoft.com",
    subject: str = "Spring showcase: judges wanted",
    original_id: str = "<review-1@ucmerced.edu>",
) -> bytes:
    """An RFC 3464 report for one recipient, as Exchange Online returns it (the original's headers attached)."""
    status_lines = [
        f"Original-Recipient: rfc822;{recipient}",
        f"Final-Recipient: rfc822;{recipient}",
        f"Action: {action}",
        f"Status: {status}",
        f"Diagnostic-Code: smtp;{diagnostic}",
    ]
    if remote_mta:
        status_lines.append(f"Remote-MTA: dns;{remote_mta}")
    lines = [
        f"From: {sender}",
        "To: i2g@ucmerced.edu",
        "Date: Tue, 10 Nov 2026 16:02:11 +0000",
        f"Subject: Undeliverable: {subject}",
        f"Message-ID: <ndr-{hashlib.sha256(f'{recipient} {status}'.encode()).hexdigest()[:12]}@{reporting_mta}>",
        f"In-Reply-To: {original_id}",
        'Content-Type: multipart/report; report-type=delivery-status; boundary="r"',
        "",
        "--r",
        "Content-Type: text/plain; charset=us-ascii",
        "",
        f"Delivery has failed to these recipients or groups: {recipient}",
        "",
        "--r",
        "Content-Type: message/delivery-status",
        "",
        f"Reporting-MTA: dns;{reporting_mta}",
        "Arrival-Date: Tue, 10 Nov 2026 15:58:40 +0000",
        "",
        *status_lines,
        "",
        "--r",
        "Content-Type: text/rfc822-headers",
        "",
        f"Message-ID: {original_id}",
        f"Subject: {subject}",
        "From: Innovate to Grow <i2g@ucmerced.edu>",
        f"To: {recipient}",
        "",
        "--r--",
        "",
    ]
    return CRLF.join(lines).encode("utf-8")


@dataclass(frozen=True)
class Expected:
    category: str
    classification: str
    is_permanent: bool | None
    smtp_code: str


@dataclass(frozen=True)
class Case:
    name: str
    recipient: str
    raw: bytes
    expected: Expected


def _case(name, recipient, expected, **report) -> Case:
    return Case(name, recipient, dsn(recipient=recipient, **report), expected)


TIMEOUT = Expected("transient", "soft", False, "550")
CASES = (
    # A Gmail address: Exchange Online gave up after its retries timed out connecting (Winsock 10060). Temporary: the
    # address is fine.
    _case(
        "gmail_connection_timeout",
        "timeout.gmail@example.com",
        TIMEOUT,
        status="5.4.300",
        diagnostic="550 5.4.300 Message expired -> 451 4.4.0 Error encountered while communicating with primary "
        'target IP address: "Failed to connect. Winsock error code: 10060, Win32 error code: 10060." Attempted '
        "failover to alternate host, but that did not succeed. Either there are no alternate hosts, or delivery "
        "failed to all alternate hosts. The last endpoint attempted was 192.0.2.27:25",
        remote_mta="gmail-smtp-in.l.google.com",
    ),
    # A small company's domain: its gateway could not reach the mail server and returned a generic 5.0.0 (a hard
    # bounce before categories). Temporary.
    _case(
        "business_connection_timeout",
        "timeout.business@example.net",
        TIMEOUT,
        status="5.0.0",
        diagnostic="550 5.0.0 connect to mail.example.net[203.0.113.25]:25: Connection timed out",
        reporting_mta="mx1.example.net",
        sender="MAILER-DAEMON@mx1.example.net",
    ),
    # Exchange Online gave up because the server refused connections (a hard bounce before categories).
    _case(
        "connection_refused_expired",
        "refused@example.org",
        TIMEOUT,
        status="5.4.316",
        diagnostic="550 5.4.316 Message expired, connection refused(Socket error code 10061)",
        remote_mta="mx.example.org",
    ),
    # Relay denied by the recipient's gateway: our route or authorisation, not the contact.
    _case(
        "relay_denied",
        "relay.case@example.net",
        Expected("relay_denied", "rejected", False, "554"),
        status="5.7.1",
        diagnostic="554 5.7.1 <relay.case@example.net>: Relay access denied",
        remote_mta="mx1.example.net",
    ),
    # Proofpoint refused the message as spam: our reputation or content, not the contact.
    _case(
        "proofpoint_spam",
        "spam.case@example.com",
        Expected("spam_rejected", "rejected", False, "550"),
        status="5.7.1",
        diagnostic="550 5.7.1 Message rejected as spam by Proofpoint (mx0b-00000000.pphosted.example) - "
        "https://ipcheck.proofpoint.example/?ip=198.51.100.7",
        remote_mta="mx0b-00000000.pphosted.example",
    ),
    # A mailbox with a 0 KB size limit (how servers disable one), reported as "message too large": disabled wins.
    _case(
        "zero_kb_size_limit",
        "size0.case@example.org",
        Expected("mailbox_disabled", "hard", True, "550"),
        status="5.2.3",
        diagnostic="550 5.2.3 RESOLVER.RST.RecipSizeLimit; message too large for this recipient; Message size: "
        "61 KB, Max size allowed: 0 KB",
    ),
    # Yahoo through Exchange Online's generic "remote server returned an error", with no reason: unknown (threshold
    # only), not hard.
    _case(
        "yahoo_generic_554",
        "yahoo.case@example.net",
        Expected("unknown", "unknown", None, "550"),
        status="5.0.350",
        diagnostic="550 5.0.350 Remote server returned an error -> 554 delivery error: dd Requested mail action "
        "aborted - mta4012.mail.gq1.yahoo.example",
        remote_mta="mta7.am0.yahoodns.example",
    ),
    # The same Yahoo route when Yahoo names its policy (content or sending reputation): our sending side.
    _case(
        "yahoo_policy_reasons",
        "yahoo.policy@example.net",
        Expected("spam_rejected", "rejected", False, "554"),
        status="5.7.9",
        diagnostic="554 5.7.9 Message not accepted for policy reasons. See https://postmaster.yahooinc.example/",
        remote_mta="mta7.am0.yahoodns.example",
    ),
    # Google Workspace (a university address): the account does not exist.
    _case(
        "address_not_found",
        "notfound.case@university.example",
        Expected("hard", "hard", True, "550"),
        status="5.1.1",
        diagnostic="550 5.1.1 The email account that you tried to reach does not exist. Please try double-checking "
        "the recipient's email address for typos or unnecessary spaces. For more information, go to "
        "https://support.google.com/mail/?p=NoSuchUser 00000000000000.0 - gsmtp",
        remote_mta="aspmx.l.google.com",
    ),
)
CASES_BY_NAME = {case.name: case for case in CASES}
