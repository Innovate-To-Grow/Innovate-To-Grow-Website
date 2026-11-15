"""Validating a delivery-rate policy: which fields apply to its channel, the provider ceilings, the manual rate,
the daily limits and the internal domain."""

from django.core.exceptions import ValidationError

from .fields import (
    CEILING_FIELDS,
    DOMAIN_VALIDATOR,
    INTERNAL_DOMAIN_REFUSED,
    NO_INTERNAL_DOMAIN,
    OPTIONAL_FIELDS,
    _as_number,
    allow_list_domains,
    display_number,
    limits_from_configuration,
)


class DeliveryRatePolicyChecksMixin:
    """The ``clean`` checks of ``DeliveryRatePolicy``."""

    def _check_applicable(self, spec, errors):
        for name in OPTIONAL_FIELDS:
            if name not in spec and getattr(self, name) != self._meta.get_field(name).get_default():
                errors[name] = f"{self.get_channel_display()} has no such limit; leave it empty."

    def _limit_unit(self, name: str) -> str:
        budget = self.unit.budget
        return {
            "provider_limit": self.unit.label,
            "parts_limit": "parts/sec",
            "daily_limit": f"{budget} per 24 h",
            "hourly_external_limit": "external recipients per hour",
            "hourly_internal_limit": "internal recipients per hour",
            "daily_message_limit": "messages per 24 h",
            "daily_external_limit": "external recipients per 24 h",
        }[name]

    def _check_ceilings(self, spec, errors):
        source = (
            "The limit on the Microsoft Graph configuration"
            if limits_from_configuration(spec)
            else "The documented limit"
        )
        for name in CEILING_FIELDS:
            ceiling, value = _as_number(spec.get(name)), _as_number(getattr(self, name))
            if ceiling is not None and value is not None and value > ceiling:
                errors.setdefault(
                    name,
                    f"{source} is {display_number(ceiling)} {self._limit_unit(name)}. It can be lowered here, not raised.",
                )

    def _check_manual_rate(self, spec, errors):
        manual = _as_number(self.manual_rate)
        bound = _as_number(self.provider_limit)
        if bound is None:
            bound = _as_number(spec["provider_limit"])
        if manual is not None and bound is not None and manual > bound:
            errors.setdefault(
                "manual_rate",
                f"It cannot be set above the provider limit of {display_number(bound)} {self.unit.label} (Advanced).",
            )

    def _check_daily_limits(self, spec, errors):
        daily = _as_number(self.daily_limit)
        if daily is None:
            daily = _as_number(spec.get("daily_limit"))
        if daily is None:
            return
        for name in ("hourly_external_limit", "hourly_internal_limit", "daily_external_limit"):
            value = _as_number(getattr(self, name))
            if value is not None and value > daily:
                errors.setdefault(
                    name, f"It cannot be above the daily limit of {display_number(daily)} {self.unit.budget}."
                )

    def _check_internal_domain(self, spec, errors):
        """Recipients in the internal domain do not count against Google's external limit, so naming one raises that
        limit: only the deployer's seed, or the domain of an allow-listed account (or a parent of it), may be named."""
        domain = self.internal_domain
        if not domain or "internal_domain" in errors or domain == str(spec.get("internal_domain") or "").lower():
            return
        try:
            DOMAIN_VALIDATOR(domain)
        except ValidationError:
            return  # the field's own validation reports it
        allowed = allow_list_domains()
        if domain not in allowed:
            listed = ", ".join(sorted(allowed))
            errors["internal_domain"] = (
                INTERNAL_DOMAIN_REFUSED.format(allowed=listed) if allowed else NO_INTERNAL_DOMAIN
            )
