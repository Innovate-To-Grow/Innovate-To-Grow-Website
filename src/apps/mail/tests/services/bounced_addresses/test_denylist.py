"""The Bounced addresses tables are out of reach of the assistant and the /admin-api/ CLI (the shared safe_orm layer),
so a suppression can only be set or lifted on the page, under its guards."""

from django.test import SimpleTestCase

from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, is_model_denied
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, BouncedAddressCampaign


class DenylistTests(SimpleTestCase):
    def test_every_bounced_address_model_is_denied(self):
        for model in (BouncedAddress, BouncedAddressAction, BouncedAddressCampaign, BounceAggregationState):
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)
                self.assertTrue(is_model_denied(model, write=False))
                self.assertTrue(is_model_denied(model, write=True))
