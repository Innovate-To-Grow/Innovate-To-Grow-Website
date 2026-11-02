"""The per-scope form of Site Settings → Request Limits: the priority tier, the Smart limit switch, the manual limit
and (Advanced) the period, the Smart floor, the fixed and enabled switches and the deployer ceilings.

Validation is the model's (``RequestRateLimitPolicy`` field validators and ``clean``), so each error lands on its
field: a limit or period of 0, a Smart floor above the baseline (a share above 1) or not above 0, a manual limit
above the per-caller ceiling, a ceiling raised above its ``REQUEST_RATE_LIMITS`` value. The manual limit is always
validated and stored as posted, also while Smart limit is on.
"""

import math
from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget, UnfoldBooleanSwitchWidget

from apps.core.models import RequestRateLimitPolicy

MANUAL_LIMIT_NOTE = _("Not used while Smart limit is on. Kept for when you turn Smart limit off.")
ADVANCED_FIELDS = ("period_seconds", "smart_floor", "fixed", "enabled", "identity_ceiling", "global_cap")
# How the admin history names each field: "auth-code-send: priority P0→P1; Smart limit on→off; manual 10→20".
LOG_NAMES = {
    "tier": "priority",
    "smart_enabled": "Smart limit",
    "manual_requests": "manual",
    "period_seconds": "period (s)",
    "smart_floor": "Smart floor",
    "fixed": "fixed",
    "enabled": "enabled",
    "identity_ceiling": "per-caller ceiling",
    "global_cap": "everyone together",
}
TIER_LABELS = dict(RequestRateLimitPolicy.Tier.choices)


def plain_number(value) -> str:
    """A stored Decimal as typed: ``Decimal("0.500")`` → "0.5", ``Decimal("1.000")`` → "1"."""
    return "" if value is None else f"{Decimal(value).normalize():f}"


def show(name: str, value) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None or value == "":
        return "blank"
    if name == "tier":
        return str(value).upper()
    if isinstance(value, Decimal):
        return plain_number(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _count_input():
    return UnfoldAdminTextInputWidget(attrs={"inputmode": "numeric", "autocomplete": "off"})


class RequestLimitPolicyForm(forms.ModelForm):
    class Meta:
        model = RequestRateLimitPolicy
        fields = ("tier", "smart_enabled", "manual_requests", *ADVANCED_FIELDS)
        widgets = {
            "tier": UnfoldAdminSelectWidget,
            "smart_enabled": UnfoldBooleanSwitchWidget,
            "fixed": UnfoldBooleanSwitchWidget,
            "enabled": UnfoldBooleanSwitchWidget,
            "smart_floor": UnfoldAdminTextInputWidget(attrs={"inputmode": "decimal", "autocomplete": "off"}),
            **{
                name: _count_input() for name in ("manual_requests", "period_seconds", "identity_ceiling", "global_cap")
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = self.instance
        self.spec = policy.scope_settings(policy.scope)
        if "parent" in self.spec:
            # A per-view limit keeps its view's own key: there is no "everyone together" counter to cap.
            del self.fields["global_cap"]
        # What the row held before this form: the history line compares against it after validation.
        self.before = {name: getattr(policy, name) for name in self.fields}
        if not self.is_bound:
            self.initial["smart_floor"] = plain_number(policy.smart_floor)
        unit = f"requests / {policy.period_seconds:,} s"
        for name, suffix in (
            ("manual_requests", unit),
            ("identity_ceiling", unit),
            ("global_cap", unit),
            ("period_seconds", "seconds"),
            ("smart_floor", "share of baseline"),
        ):
            if name in self.fields:
                attrs = self.fields[name].widget.attrs
                attrs["suffix"] = suffix
                # Unfold draws the suffix over the input's right edge: keep the typed value clear of it.
                attrs["style"] = f"padding-right: calc({len(suffix)}ch + 1.5rem)"
        self._add_help()

    def _add_help(self) -> None:
        spec = self.spec
        default_tier = spec["tier"]
        tier = self.fields["tier"]
        tier.help_text = f"{tier.help_text} Default: {TIER_LABELS[default_tier]}."
        if default_tier == RequestRateLimitPolicy.Tier.P0:
            tier.help_text += " In a lower tier Smart limit may tighten it under load."
        floor = self.fields["smart_floor"]
        at_floor = max(1, math.floor(spec["requests"] * self.instance.smart_floor + Decimal("1e-9")))
        floor.help_text = (
            f"{floor.help_text} A share of the baseline ({spec['requests']:,} requests per period, from "
            f"REQUEST_RATE_LIMITS), so at most 1: now {at_floor:,} per period at the floor (never below 1)."
        )
        for name in ("identity_ceiling", "global_cap"):
            if name in self.fields and spec[name] is not None:
                field = self.fields[name]
                field.help_text = f"{field.help_text} At most {spec[name]:,} (deployment): it can be lowered here."

    def advanced_fields(self) -> list:
        return [self[name] for name in ADVANCED_FIELDS if name in self.fields]

    def smart_on(self) -> bool:
        return bool(self["smart_enabled"].value())

    def lock_manual_limit(self) -> bool:
        """Make the manual limit read-only while Smart limit is on, unless it has an error to fix; return whether it
        is locked. Read-only inputs are still posted, so the stored value is always the one shown."""
        locked = self.smart_on() and not self["manual_requests"].errors
        attrs = self.fields["manual_requests"].widget.attrs
        if locked:
            attrs["readonly"] = True
        else:
            attrs.pop("readonly", None)
        return locked

    def change_summary(self) -> str:
        """The admin history line of a validated form (who is the LogEntry's user), or "" when nothing changed."""
        changes = []
        for name in self.fields:
            old, new = self.before[name], getattr(self.instance, name)
            if old != new and not (old in (None, "") and new in (None, "")):
                changes.append(f"{LOG_NAMES[name]} {show(name, old)}→{show(name, new)}")
        return f"{self.instance.scope}: {'; '.join(changes)}" if changes else ""
