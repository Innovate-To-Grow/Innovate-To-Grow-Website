from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import DeliveryRatePolicy
from apps.core.tests.models.delivery_rates.test_delivery_rate_policy import Channel


class PolicyManualRateTests(TestCase):
    def setUp(self):
        cache.clear()
        DeliveryRatePolicy.objects.all().delete()

    def test_switching_smart_rate_keeps_the_manual_rate(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal("12.5")
        policy.save()
        for smart in (False, True, False, True):
            policy.smart_enabled = smart
            policy.save()
            policy.refresh_from_db()
            self.assertEqual(policy.manual_rate, Decimal("12.500"))

    def test_the_manual_rate_can_be_edited_while_smart_rate_is_on(self):
        policy = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        self.assertTrue(policy.smart_enabled)
        policy.manual_rate = Decimal("2.25")
        policy.save()
        policy.refresh_from_db()
        self.assertEqual((policy.smart_enabled, policy.manual_rate), (True, Decimal("2.250")))

    def test_the_manual_rate_cannot_exceed_the_provider_limit(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal("30.001")
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertEqual(
            error.exception.message_dict["manual_rate"],
            ["It cannot be set above the provider limit of 30 messages/min (Advanced)."],
        )

        policy.manual_rate = Decimal(30)
        policy.provider_limit = Decimal(20)
        with self.assertRaisesMessage(ValidationError, "provider limit of 20 messages/min"):
            policy.full_clean()
        policy.provider_limit = None  # blank: the documented 30 applies
        policy.full_clean()

    def test_without_a_provider_limit_the_manual_rate_is_unbounded(self):
        smtp = DeliveryRatePolicy.for_channel(Channel.SMTP_SEND)
        smtp.manual_rate = Decimal(5_000)
        smtp.full_clean()
        ses = DeliveryRatePolicy.for_channel(Channel.SES_SEND)
        ses.manual_rate = Decimal(200)
        ses.full_clean()
        ses.provider_limit = Decimal(100)
        with self.assertRaisesMessage(ValidationError, "provider limit of 100 recipients/sec"):
            ses.full_clean()

    def test_the_slowest_rate_is_one_thousandth(self):
        policy = DeliveryRatePolicy.for_channel(Channel.SMS_SEND)
        policy.manual_rate = Decimal("0.001")
        policy.full_clean()
        policy.manual_rate = Decimal(0)
        with self.assertRaises(ValidationError) as error:
            policy.full_clean()
        self.assertIn("manual_rate", error.exception.message_dict)

    def test_save_validates(self):
        policy = DeliveryRatePolicy.for_channel(Channel.GRAPH_SEND)
        policy.manual_rate = Decimal(31)
        with self.assertRaises(ValidationError):
            policy.save()
        policy.refresh_from_db()
        self.assertEqual(policy.manual_rate, Decimal(24))
