"""Shared fixtures for the SMS policy tests (opt-outs, quiet hours, links, ticket texts). Nothing here calls AWS."""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings

from apps.authn.models import ContactPhone
from apps.core.models import AWSCredentialConfig
from apps.mail.models import SmsConfig, SmsOptOut

ORIGINATION = "+12065550000"
# 2026-11-11 23:30 Pacific (inside the default 20:00–09:00 quiet hours) and the window's end, 09:00 Pacific next day.
QUIET_MOMENT = datetime(2026, 11, 12, 7, 30, tzinfo=UTC)
QUIET_ENDS = datetime(2026, 11, 12, 17, 0, tzinfo=UTC)
# 2026-11-11 12:00 Pacific: outside quiet hours.
DAYTIME = datetime(2026, 11, 11, 20, 0, tzinfo=UTC)


def sms_aws_config():
    AWSCredentialConfig.objects.all().delete()
    return AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="aws-key",
        secret_access_key="aws-secret",
        default_region="us-west-2",
        sms_from_number=ORIGINATION,
    )


def sms_settings(**values) -> SmsConfig:
    config = SmsConfig.load()
    for name, value in values.items():
        setattr(config, name, value)
    config.save()
    return config


def add_phone(member, national, *, subscribe=True, verified=True):
    return ContactPhone.objects.create(
        member=member, phone_number=national, region="1-US", subscribe=subscribe, verified=verified
    )


def opt_out(number, *, source=SmsOptOut.Source.AWS, **fields):
    fields.setdefault("opted_out_at", datetime(2026, 11, 1, tzinfo=UTC))
    return SmsOptOut.objects.create(phone_number=number, source=source, **fields)


@contextmanager
def at(moment):
    """Quiet hours enforced (they are off for test runs) with the quiet-hours clock reading ``moment``."""
    clock = SimpleNamespace(now=lambda: moment)
    with override_settings(SMS_QUIET_HOURS_ENFORCED=True), patch("apps.mail.services.sms.quiet_hours.timezone", clock):
        yield
