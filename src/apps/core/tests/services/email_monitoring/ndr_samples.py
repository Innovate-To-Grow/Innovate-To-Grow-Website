"""Bounce reports as they arrive in the sending mailbox, built in the shapes real servers use: an Exchange Online
NDR (returned headers as ``text/rfc822-headers``), a Gmail DSN (the whole original as ``message/rfc822``), a delay
notice, an old-style bounce without a delivery-status part, and a person's email that only looks like one."""

ORIGINAL_ID = "<orig-1@ucmerced.edu>"
CRLF = "\r\n"


def _join(lines) -> bytes:
    return CRLF.join(lines).encode("utf-8")


def exchange_ndr(
    *,
    recipient="nobody@example.com",
    status="5.1.10",
    action="failed",
    original_id=ORIGINAL_ID,
    subject="Your login code - Innovate to Grow",
    report_id="<ndr-1@SJ0PR01MB0001.namprd01.prod.outlook.com>",
    original_recipient=True,
    extra_recipient=None,
) -> bytes:
    recipient_blocks = [_recipient_block(recipient, status, action, original_recipient)]
    if extra_recipient:
        recipient_blocks.append(_recipient_block(*extra_recipient, True))
    return _join(
        [
            "From: postmaster@ucmerced.onmicrosoft.com",
            "To: i2g@ucmerced.edu",
            "Date: Mon, 9 Nov 2026 18:00:05 +0000",
            f"Subject: Undeliverable: {subject}",
            f"Message-ID: {report_id}",
            f"In-Reply-To: {original_id}",
            "Auto-Submitted: auto-replied",
            "MIME-Version: 1.0",
            'Content-Type: multipart/report; report-type=delivery-status; boundary="ndr"',
            "",
            "--ndr",
            'Content-Type: text/plain; charset="us-ascii"',
            "",
            f"Your message to {recipient} couldn't be delivered.",
            "",
            "--ndr",
            "Content-Type: message/delivery-status",
            "",
            "Reporting-MTA: dns;SJ0PR01MB0001.namprd01.prod.outlook.com",
            "Arrival-Date: Mon, 9 Nov 2026 18:00:02 +0000",
            "",
            *[line for block in recipient_blocks for line in (*block, "")],
            "--ndr",
            "Content-Type: text/rfc822-headers",
            "",
            f"Message-ID: {original_id}",
            f"Subject: {subject}",
            "From: Innovate to Grow <i2g@ucmerced.edu>",
            f"To: {recipient}",
            "",
            "--ndr--",
            "",
        ]
    )


def _recipient_block(recipient, status, action, original_recipient):
    lines = [f"Original-Recipient: rfc822;{recipient}"] if original_recipient else []
    lines += [
        f"Final-Recipient: rfc822;{recipient}",
        f"Action: {action}",
        f"Status: {status}",
        f"Diagnostic-Code: smtp;550 {status} RESOLVER.ADR.RecipientNotFound; Recipient {recipient} not found by",
        " SMTP address lookup",
        "Remote-MTA: dns;mx.example.com",
    ]
    if action == "delayed":
        lines.append("Will-Retry-Until: Wed, 11 Nov 2026 18:00:00 +0000")
    return lines


def gmail_dsn(*, recipient="gone@gmail.com", status="5.1.1", original_id=ORIGINAL_ID, subject="Campaign news") -> bytes:
    return _join(
        [
            "From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
            "To: i2g@ucmerced.edu",
            "Subject: Delivery Status Notification (Failure)",
            "Message-ID: <dsn-2@mx.google.com>",
            "MIME-Version: 1.0",
            'Content-Type: multipart/report; report-type=delivery-status; boundary="dsn"',
            "",
            "--dsn",
            "Content-Type: text/plain; charset=UTF-8",
            "",
            "Address not found",
            "",
            "--dsn",
            "Content-Type: message/delivery-status",
            "",
            "Reporting-MTA: dns; googlemail.com",
            "Arrival-Date: Mon, 09 Nov 2026 10:01:02 -0800",
            "",
            f"Final-Recipient: rfc822; {recipient}",
            "Action: failed",
            f"Status: {status}",
            f"Diagnostic-Code: smtp; 550-{status} The email account that you tried to reach does not exist.",
            "Last-Attempt-Date: Mon, 09 Nov 2026 10:01:03 -0800",
            "",
            "--dsn",
            "Content-Type: message/rfc822",
            "",
            f"Message-ID: {original_id}",
            f"Subject: {subject}",
            "From: i2g@ucmerced.edu",
            f"To: {recipient}",
            "Content-Type: text/plain",
            "",
            "The original body, which must never be stored.",
            "",
            "--dsn--",
            "",
        ]
    )


def old_style_bounce(*, recipient="gone@example.org") -> bytes:
    return _join(
        [
            "From: Mail Delivery System <MAILER-DAEMON@mx.example.org>",
            "To: i2g@ucmerced.edu",
            "Subject: Mail delivery failed: returning message to sender",
            "Message-ID: <bounce-3@mx.example.org>",
            f"X-Failed-Recipients: {recipient}",
            "Content-Type: text/plain; charset=us-ascii",
            "",
            "This message was created automatically by mail delivery software.",
            "",
            f"  {recipient}",
            f"    SMTP error from remote mail server after RCPT TO:<{recipient}>:",
            "    550 5.1.1 User unknown",
            "",
        ]
    )


def personal_email() -> bytes:
    return _join(
        [
            "From: Some Person <person@example.com>",
            "To: i2g@ucmerced.edu",
            "Subject: Undeliverable: my question about the event",
            "Message-ID: <human-4@example.com>",
            "Content-Type: text/plain; charset=us-ascii",
            "",
            "Hi, an earlier email came back undeliverable. 5.1.1 was in it. Can you help?",
            "",
        ]
    )
