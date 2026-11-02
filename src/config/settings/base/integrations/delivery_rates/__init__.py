"""
Delivery rates: the defaults behind Mail → Delivery Rates, and the controller that paces every delivery channel
(Microsoft Graph send and read, Amazon SES, SMTP, Gmail IMAP, the Gmail API and AWS SMS).

Nothing about a channel's rate is hard-coded elsewhere. Each channel's ``DeliveryRatePolicy`` row is seeded from
``DELIVERY_RATES["channels"]`` (``channels.py``, every value with its source) and edited by mail staff, who can
lower a documented provider limit but never raise it above the value here. Smart rate (on by default everywhere)
adjusts within those limits using the controller and runtime sections (``runtime.py``) and the provider answers in
``signals.py``.

A deployment changes any value with the ``DELIVERY_RATES_OVERRIDES`` environment variable, a JSON object
deep-merged into the defaults, for example after an AWS quota increase::

    DELIVERY_RATES_OVERRIDES='{"channels": {"sms_send": {"provider_limit": 20}}}'

Only existing settings can be overridden, and the result is validated here at import: a bad value raises
``ImproperlyConfigured`` before the site starts.
"""

import os

from .channels import CHANNELS
from .runtime import CONTROLLER, DISCOVERY, JOBS, LANES, USAGE, WAITS
from .signals import SIGNALS
from .validation import OVERRIDES_ENV, load_delivery_rates

__all__ = ["DELIVERY_RATES"]

DEFAULTS = {
    "channels": CHANNELS,
    "controller": CONTROLLER,
    "waits": WAITS,
    "lanes": LANES,
    "usage": USAGE,
    "discovery": DISCOVERY,
    "jobs": JOBS,
    "signals": SIGNALS,
}

DELIVERY_RATES = load_delivery_rates(DEFAULTS, os.environ.get(OVERRIDES_ENV, ""))
