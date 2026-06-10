"""Per-view throttle classes for event endpoints.

Per project convention, DEFAULT_THROTTLE_CLASSES is never set globally (it would
throttle every view, including tests at 127.0.0.1); throttle classes are attached
per view and only the *rates* live in settings (DEFAULT_THROTTLE_RATES).

``PhoneCodeRequestThrottle`` is defined canonically in ``apps.authn.throttles``
(it caps SMS verification sends per authenticated user) and re-exported here so
event views can attach it without reaching across apps inline.
"""

from apps.authn.throttles import PhoneCodeRequestThrottle

__all__ = ["PhoneCodeRequestThrottle"]
