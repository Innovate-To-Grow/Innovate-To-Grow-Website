"""The shared safe-ORM denylist keeps the delivery-rate policy, its live state and usage, and the legacy rate slot
away from the assistant and the CLI: a write could raise a rate or reopen a provider breaker."""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.models import DeliveryRateLimit, DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, ActionRequestError, is_model_denied, resolve_model

RATE_MODELS = (DeliveryRatePolicy, DeliveryRateState, DeliveryUsageBucket, DeliveryRateLimit)
SAFETY = "apps.core.services.db_tools.safe_orm.safety"


class DeliveryRateModelDenylistTest(SimpleTestCase):
    def test_every_rate_model_is_listed_explicitly(self):
        for model in RATE_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)

    def test_resolve_model_refuses_read_and_write(self):
        for model in RATE_MODELS:
            for write, access in ((False, "Read"), (True, "Write")):
                for model_name in (model._meta.model_name, model.__name__):
                    with self.subTest(write=write, model_name=model_name):
                        self.assertTrue(is_model_denied(model, write=write))
                        with self.assertRaises(ActionRequestError) as error:
                            resolve_model("core", model_name, write=write)

                        self.assertEqual(
                            str(error.exception), f"{access} access is not allowed for core.{model.__name__}."
                        )

    def test_only_the_explicit_label_blocks_them(self):
        # Their names match no denied name part ("config", "token", ...).
        for model in RATE_MODELS:
            with self.subTest(model=model.__name__), patch(f"{SAFETY}.DENIED_MODEL_LABELS", frozenset()):
                self.assertFalse(is_model_denied(model, write=False))
                self.assertFalse(is_model_denied(model, write=True))
