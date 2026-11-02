"""Shared setup for the Mail → Delivery Rates admin tests: SES email and AWS SMS configured (no network)."""

from datetime import UTC, datetime

from django.core.cache import cache
from django.forms import BooleanField
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, DeliveryRatePolicy, DeliveryRateState, EmailServiceConfig
from apps.core.services.delivery_rates import cooldown_group, ses_identity
from apps.core.tests.services.delivery_rates.helpers import FakeClock
from apps.event.tests.helpers import make_admin
from apps.mail.admin.settings.rates_forms import DeliveryRatePolicyForm

Channel = DeliveryRatePolicy.Channel
NOW = datetime(2026, 11, 2, 13, 10, tzinfo=UTC)
READ_AT = datetime(2026, 11, 2, 13, 5, tzinfo=UTC)
SMS_IDENTITY = "us-west-2:+12065550000"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class DeliveryRatesTestCase(TestCase):
    """A staff member with only the Mail app, SES as the email provider and an SMS number on the AWS config."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.clock = FakeClock(NOW).install(self)
        self.staff = make_admin(apps=["mail"], email="mailstaff@example.com")
        self.client.force_login(self.staff)
        self.email_config = EmailServiceConfig.objects.create(
            name="Production Mail", is_active=True, provider="ses", from_email="admin@example.com", from_name="I2G"
        )
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )
        self.url = reverse("admin:mail_delivery_rates")
        self.status_url = reverse("admin:mail_delivery_rates_status")

    @property
    def ses_identity(self):
        return ses_identity(self.aws_config.pk, "us-west-2")

    def policy(self, channel):
        return DeliveryRatePolicy.for_channel(channel)

    def set_policy(self, channel, **values):
        DeliveryRatePolicy.objects.filter(pk=self.policy(channel).pk).update(**values)

    def state(self, channel, identity, **values):
        return DeliveryRateState.objects.create(
            channel=channel, identity=identity, cooldown_group=cooldown_group(channel, identity), **values
        )

    def post_data(self, **overrides):
        """The whole page as a browser posts it unchanged, with ``overrides`` (``None`` unticks a switch)."""
        data = {}
        for channel in Channel.values:
            form = DeliveryRatePolicyForm(instance=self.policy(channel), prefix=channel)
            for name, field in form.fields.items():
                value = form[name].value()
                if isinstance(field, BooleanField):
                    if value:
                        data[form.add_prefix(name)] = "on"
                else:
                    data[form.add_prefix(name)] = "" if value is None else str(value)
        for key, value in overrides.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        return data

    def card_html(self, response, channel):
        content = response.content.decode()
        start = content.index(f'id="rate-card-{channel}"')
        return content[start : content.index("</article>", start)]

    def card(self, response, channel):
        return next(card for card in response.context["all_cards"] if card.channel == channel)
