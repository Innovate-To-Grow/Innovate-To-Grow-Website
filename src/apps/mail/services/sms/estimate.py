"""The segment and cost estimate of a Broadcast SMS, shown before it is sent (and live in the composer).

AWS bills each message part (segment): 160 GSM-7 characters fit one text, 153 per part once it is split; a single
character outside GSM-7 (an emoji, a curly quote) makes the whole text UCS-2, 70 per text or 67 per part
(``core.services.delivery_rates.rules.sms_parts``). Each recipient's text is measured as it would be sent: their
names, a link as long as a real one, and the footer. The cost is that total times the estimated price per segment
from Mail → SMS Settings, which staff keep in line with AWS's pricing page.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.core.services.delivery_rates.rules.sms_parts import sms_encoding, sms_parts
from apps.mail.models import SmsConfig
from apps.mail.models.sms_campaign import SMS_LINK_PLACEHOLDERS

from ..campaign.personalize import personalize
from .compose import EXAMPLE_NAMES, apply_footer, name_values
from .links import example_link


@dataclass(frozen=True)
class SmsEstimate:
    recipients: int
    encoding: str
    characters: int
    segments_per_text: int
    max_segments_per_text: int
    total_segments: int
    cost: Decimal
    cost_per_segment: Decimal


def measured_text(message: str, recipient, config: SmsConfig, *, link: str) -> str:
    values = {**name_values(recipient), **dict.fromkeys(SMS_LINK_PLACEHOLDERS, link)}
    return apply_footer(personalize(message, values), config)


def estimate(message: str, recipients, config: SmsConfig, *, sample) -> SmsEstimate:
    """The estimate for ``recipients`` (audience rows), with ``sample`` (a row of example names) for the
    per-text figures."""
    link = example_link()
    sample_text = measured_text(message, sample, config, link=link)
    sizes = [sms_parts(measured_text(message, recipient, config, link=link)) for recipient in recipients]
    total = sum(sizes)
    price = Decimal(config.cost_per_segment or 0)
    return SmsEstimate(
        recipients=len(sizes),
        encoding=sms_encoding(sample_text),
        characters=len(sample_text),
        segments_per_text=sms_parts(sample_text),
        max_segments_per_text=max(sizes, default=sms_parts(sample_text)),
        total_segments=total,
        cost=(price * total).quantize(Decimal("0.01")),
        cost_per_segment=price,
    )


def composer_settings(config: SmsConfig | None = None) -> dict:
    """What the composer's live counter (``mail/js/sms-composer.js``) measures a draft with: the same footer, link
    length, example names and price as ``estimate``."""
    config = config or SmsConfig.load()
    return {
        "footer": (config.footer_text or "").strip() if config.footer_enabled else "",
        "linkLength": len(example_link()),
        "linkPlaceholders": list(SMS_LINK_PLACEHOLDERS),
        "linksEnabled": config.links_enabled,
        "names": EXAMPLE_NAMES,
        "costPerSegment": str(config.cost_per_segment),
    }
