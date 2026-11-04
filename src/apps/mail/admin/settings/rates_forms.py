"""The per-channel form of Mail → Delivery Rates: the Smart rate switch, the manual rate and the channel's provider
limits (Advanced).

Validation is the model's (``DeliveryRatePolicy.clean``), so each error lands on its field: a manual rate above the
provider limit, a documented limit raised above its ``DELIVERY_RATES`` value. The manual rate is always validated
and stored as posted, also while Smart rate is on.
"""

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminTextInputWidget, UnfoldBooleanSwitchWidget

from apps.core.models import DeliveryRatePolicy
from apps.core.models.base.delivery_rates import (
    CEILING_FIELDS,
    DECIMAL_FIELDS,
    display_number,
    limits_from_configuration,
)
from apps.core.services.delivery_rates import channel_info

MANUAL_RATE_NOTE = _("Not used while Smart rate is on. Kept for when you turn Smart rate off.")
CARRIED_OVER_NOTE = (
    "Carried over from the old campaign send rate: it applies only until {provider} reports the account's limit. "
    "Enter another value to make it your own limit, or clear it to use only what {provider} reports."
)

# The Advanced fields, in display order. Every channel has ``provider_limit``; the others only where the channel's
# DELIVERY_RATES seed lists them (the model refuses them elsewhere).
ADVANCED_FIELDS = (
    "provider_limit",
    "parts_limit",
    "daily_limit",
    "daily_message_limit",
    "daily_external_limit",
    "hourly_external_limit",
    "hourly_internal_limit",
    "limits_confirmed",
    "internal_domain",
    "budget_headroom",
    "transactional_reserve",
)
_COUNT_FIELDS = frozenset(
    {"daily_limit", "daily_message_limit", "daily_external_limit", "hourly_external_limit", "hourly_internal_limit"}
)
# How the admin history names each field: "sms_send: Smart rate on→off; manual 1→2".
LOG_NAMES = {
    "smart_enabled": "Smart rate",
    "manual_rate": "manual",
    "provider_limit": "provider limit",
    "parts_limit": "MPS",
    "daily_limit": "daily limit",
    "daily_message_limit": "daily messages",
    "daily_external_limit": "daily external",
    "hourly_external_limit": "hourly external",
    "hourly_internal_limit": "hourly internal",
    "limits_confirmed": "tenant limits confirmed",
    "internal_domain": "internal domain",
    "budget_headroom": "budget headroom",
    "transactional_reserve": "transactional reserve",
}
_PERIODS = {"sec": "second", "min": "minute"}


def unit_suffix(label: str) -> str:
    """A rate unit spelled out for an input suffix: "messages/sec" → "messages / second"."""
    counted, _, period = label.partition("/")
    return f"{counted} / {_PERIODS.get(period, period)}"


def plain_number(value) -> str:
    """A stored Decimal as typed: ``Decimal("24.000")`` → "24", ``Decimal("0.250")`` → "0.25"."""
    return "" if value is None else f"{Decimal(value).normalize():f}"


def _show(value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None or value == "":
        return "blank"
    if isinstance(value, Decimal | int):
        return display_number(Decimal(value))
    return str(value)


def _rate_input():
    return UnfoldAdminTextInputWidget(attrs={"inputmode": "decimal", "autocomplete": "off"})


def _count_input():
    return UnfoldAdminTextInputWidget(attrs={"inputmode": "numeric", "autocomplete": "off"})


class DeliveryRatePolicyForm(forms.ModelForm):
    class Meta:
        model = DeliveryRatePolicy
        fields = ("smart_enabled", "manual_rate", *ADVANCED_FIELDS)
        widgets = {
            "smart_enabled": UnfoldBooleanSwitchWidget,
            "limits_confirmed": UnfoldBooleanSwitchWidget,
            "internal_domain": UnfoldAdminTextInputWidget(attrs={"autocomplete": "off", "spellcheck": "false"}),
            **{name: _rate_input() for name in DECIMAL_FIELDS},
            **{name: _count_input() for name in _COUNT_FIELDS},
        }

    def __init__(self, *args, placeholders=None, **kwargs):
        super().__init__(*args, **kwargs)
        policy = self.instance
        spec = policy.channel_settings(policy.channel)
        for name in ADVANCED_FIELDS:
            if name != "provider_limit" and name not in spec:
                del self.fields[name]
        # What the row held before this form: the history line compares against it after validation.
        self.before = {name: getattr(policy, name) for name in self.fields}
        suffixes = self._suffixes()
        for name, field in self.fields.items():
            attrs = field.widget.attrs
            if name in suffixes:
                attrs["suffix"] = suffixes[name]
                # Unfold draws the suffix over the input's right edge: keep the typed value clear of it.
                attrs["style"] = f"padding-right: calc({len(suffixes[name])}ch + 1.5rem)"
            if (placeholders or {}).get(name):
                attrs["placeholder"] = placeholders[name]
            if name in DECIMAL_FIELDS and not self.is_bound:
                self.initial[name] = plain_number(getattr(policy, name))
        self._add_ceiling_help(spec)
        if policy.provider_limit_carried_over:
            field = self.fields["provider_limit"]
            note = CARRIED_OVER_NOTE.format(provider=channel_info(policy.channel).provider)
            field.help_text = f"{field.help_text} {note}"

    def clean(self):
        cleaned = super().clean()
        if "provider_limit" in self.changed_data:
            # A limit staff enter (or clear) is theirs: it no longer gives way to the one the provider reports.
            self.instance.provider_limit_carried_over = False
        return cleaned

    def _suffixes(self) -> dict:
        unit = self.instance.unit
        rate = unit_suffix(unit.label)
        return {
            "manual_rate": rate,
            "provider_limit": rate,
            "parts_limit": "parts / second",
            "daily_limit": f"{unit.budget} / 24 h",
            "daily_message_limit": "messages / 24 h",
            "daily_external_limit": "external recipients / 24 h",
            "hourly_external_limit": "external recipients / hour",
            "hourly_internal_limit": "internal recipients / hour",
            "budget_headroom": "share",
            "transactional_reserve": "share",
        }

    def _add_ceiling_help(self, spec) -> None:
        source = "on the Microsoft Graph configuration" if limits_from_configuration(spec) else "documented"
        for name in CEILING_FIELDS:
            ceiling = spec.get(name)
            if name in self.fields and ceiling is not None:
                suffix = self.fields[name].widget.attrs.get("suffix", "")
                field = self.fields[name]
                field.help_text = (
                    f"{field.help_text} At most {display_number(Decimal(str(ceiling)))} {suffix} ({source}): "
                    "it can be lowered here, not raised."
                )

    def advanced_fields(self) -> list:
        return [self[name] for name in ADVANCED_FIELDS if name in self.fields]

    def smart_on(self) -> bool:
        return bool(self["smart_enabled"].value())

    def lock_manual_rate(self) -> bool:
        """Make the manual rate read-only while Smart rate is on, unless it has an error to fix; return whether it
        is locked. Read-only inputs are still posted, so the stored value is always the one shown."""
        locked = self.smart_on() and not self["manual_rate"].errors
        attrs = self.fields["manual_rate"].widget.attrs
        if locked:
            attrs["readonly"] = True
        else:
            attrs.pop("readonly", None)
        return locked

    def change_summary(self) -> str:
        """The admin history line of a validated form, or "" when nothing changed."""
        changes = []
        for name in self.fields:
            old, new = self.before[name], getattr(self.instance, name)
            if old != new and not (old in (None, "") and new in (None, "")):
                changes.append(f"{LOG_NAMES[name]} {_show(old)}→{_show(new)}")
        return f"{self.instance.channel}: {'; '.join(changes)}" if changes else ""
