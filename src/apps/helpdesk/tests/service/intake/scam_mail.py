"""Mail for the scam-verdict tests: a person locked out of their account, whose words alone score high on the scam
checks (it reads like a phish), with or without proof of the sender's domain, and the technical warnings that keep
such mail spam. Synthetic, like the corpus; the Authentication-Results values are in the shape Exchange Online
stamps on inbound mail."""

from ... import corpus

# The sender proved the From domain with DMARC.
DMARC_PASS = (
    "spf=pass (sender IP is 192.0.2.10) smtp.mailfrom=example.org; dkim=pass (signature was verified) "
    "header.d=example.org;dmarc=pass action=none header.from=example.org"
)
# No DMARC record (Exchange's best guess), but its composite authentication passed it.
COMPAUTH_PASS = (
    "spf=pass (sender IP is 192.0.2.10) smtp.mailfrom=example.org; dkim=none (message not signed) "
    "header.d=none;dmarc=bestguesspass action=none header.from=example.org;compauth=pass reason=109"
)
# Neither proof nor failure: no DMARC result, and only a composite soft pass.
UNPROVEN = (
    "spf=none (sender IP is 192.0.2.10) smtp.mailfrom=example.org; dkim=none (message not signed) "
    "header.d=none;dmarc=none action=none header.from=example.org;compauth=softpass reason=201"
)
# What its words alone score (3 + 2 + 3 = 8, past the detector's high threshold of 7), in the checks' order.
WORD_REASONS = [
    "Subject contains urgency/scam language (2 pattern(s) matched)",
    "Body contains urgency/pressure language (2 pattern(s))",
    "Body requests personal/financial information (1 type(s))",
]
SCAM = "scam: "


def locked_out(auth: str = "", *, headers=None, **overrides) -> bytes:
    """The locked-out person's message; ``auth`` is its Authentication-Results value ("": none)."""
    values = {
        "subject": "Urgent: my account is locked",
        "text": (
            "Hi, my account was locked and I cannot reset my password. Our team has to submit the video "
            "immediately, within 24 hours. Can you help?"
        ),
        "message_id": "<locked-1@mail.example.org>",
        "headers": {**({"Authentication-Results": auth} if auth else {}), **(headers or {})},
    }
    return corpus.message(**{**values, **overrides})


def below_the_server(raw: bytes, forged: str) -> bytes:
    """``raw`` with an Authentication-Results header the sender wrote themselves, below the receiving server's (which
    Exchange adds on top)."""
    head, body = raw.split(b"\r\n\r\n", 1)
    return head + f"\r\nAuthentication-Results: {forged}".encode() + b"\r\n\r\n" + body


def scam_signals(message) -> list[str]:
    """The scam checks' reasons among a stored message's signals, as stored."""
    return [str(item) for item in message.signals if str(item).startswith(SCAM)]
