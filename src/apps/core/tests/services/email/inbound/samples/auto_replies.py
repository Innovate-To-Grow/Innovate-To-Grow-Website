from apps.core.tests.services.email.inbound.samples.base import CAMPAIGN_SUBJECT, CONTOSO_AUTH, message


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
