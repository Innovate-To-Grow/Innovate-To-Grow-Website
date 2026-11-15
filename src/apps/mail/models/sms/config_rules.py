"""The rules SMS Settings are validated against, and how the settings read as personal-link state and a time zone."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError

from .personal_links import PersonalLinkState

DEFAULT_REGISTER_PATH = "/login"
REGISTER_PATH = "/register"


def register_path_errors(path: str) -> dict:
    from apps.mail.redirects import is_strict_internal_path

    value = (path or "").strip()
    if not is_strict_internal_path(value):
        return {"register_redirect_path": "Choose a page on this site (a path starting with /)."}
    if value.split("?", 1)[0].rstrip("/") == REGISTER_PATH:
        return {"register_redirect_path": "/register cannot lead to itself."}
    return {}


class SmsConfigRulesMixin:
    """``clean`` and the derived properties of ``SmsConfig``."""

    @property
    def personal_link_state(self) -> PersonalLinkState:
        return PersonalLinkState(self.links_enabled, self.personal_links_enabled, self.personal_links_epoch)

    @property
    def personal_sign_in_on(self) -> bool:
        """Personal sign-in links may sign members in: links in SMS and personal sign-in links both on."""
        return self.personal_link_state.on

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.quiet_hours_timezone)

    def clean(self):
        super().clean()
        errors = {}
        try:
            ZoneInfo(self.quiet_hours_timezone or "")
        except (ZoneInfoNotFoundError, ValueError):
            errors["quiet_hours_timezone"] = "Enter a time zone name such as America/Los_Angeles."
        if self.quiet_hours_start == self.quiet_hours_end:
            errors["quiet_hours_end"] = "Quiet hours must end at a different time than they start."
        if self.footer_enabled and "stop" not in (self.footer_text or "").lower():
            errors["footer_text"] = "The footer must tell people to reply STOP."
        if "{{ticket_link}}" not in (self.ticket_sms_template or ""):
            errors["ticket_sms_template"] = "The ticket text must contain {{ticket_link}}."
        if self.ticket_sms_enabled and not self.links_enabled:
            errors["ticket_sms_enabled"] = "Ticket texts carry a link: allow links in SMS first."
        maximum = settings.SMS_POLICY["link_max_validity_days"]
        if not 1 <= (self.ticket_link_validity_days or 0) <= maximum:
            errors["ticket_link_validity_days"] = f"Choose 1 to {maximum} days."
        errors.update(register_path_errors(self.register_redirect_path))
        if errors:
            raise ValidationError(errors)
