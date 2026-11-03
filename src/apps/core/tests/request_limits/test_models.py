"""The request-limit models: the seed migration, self-healing rows, the deployer ceilings and the CLI denylist."""

import importlib
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.core.models import RequestLimitProcess, RequestRateLimitPolicy, RequestRateLimitState
from apps.core.models.base.request_limits import SEED_FIELDS, scope_seed
from apps.core.services.db_tools.safe_orm import DENIED_MODEL_LABELS, is_model_denied

MIGRATION = importlib.import_module("apps.core.migrations.0039_request_rate_limits")
SCOPES = settings.REQUEST_RATE_LIMITS["scopes"]


class SeedMigrationTests(TestCase):
    def test_every_scope_has_a_policy_and_a_full_factor(self):
        self.assertEqual(set(RequestRateLimitPolicy.objects.values_list("scope", flat=True)), set(SCOPES))
        self.assertEqual(set(RequestRateLimitState.objects.values_list("factor", flat=True)), {1.0})
        self.assertEqual(RequestRateLimitState.objects.count(), len(SCOPES))

    def test_the_seed_matches_the_model_seed(self):
        for scope, spec in SCOPES.items():
            with self.subTest(scope=scope):
                row = RequestRateLimitPolicy.objects.get(scope=scope)
                self.assertEqual({field: getattr(row, field) for field in SEED_FIELDS}, scope_seed(scope, spec))
                self.assertTrue(row.smart_enabled)

    def test_tier_floors_fill_a_missing_smart_floor(self):
        self.assertEqual(RequestRateLimitPolicy.objects.get(scope="public-heavy").smart_floor, Decimal("0.100"))
        self.assertEqual(RequestRateLimitPolicy.objects.get(scope="public-read").smart_floor, Decimal("0.500"))
        self.assertEqual(RequestRateLimitPolicy.objects.get(scope="auth-sign-in").smart_floor, Decimal("1.000"))

    def test_seeding_again_keeps_rows_and_reverse_removes_them(self):
        RequestRateLimitPolicy.objects.filter(scope="cli").update(manual_requests=7)
        MIGRATION.seed_request_limit_policies(django_apps, None)
        self.assertEqual(RequestRateLimitPolicy.objects.get(scope="cli").manual_requests, 7)
        MIGRATION.remove_request_limit_policies(django_apps, None)
        self.assertFalse(RequestRateLimitPolicy.objects.exists())
        self.assertFalse(RequestRateLimitState.objects.exists())

    def test_frozen_fields_are_policy_columns(self):
        columns = {field.name for field in RequestRateLimitPolicy._meta.get_fields()}
        self.assertLessEqual(set(MIGRATION.COPIED_FIELDS) | {"manual_requests", "smart_floor"}, columns)
        self.assertEqual(set(MIGRATION.COPIED_FIELDS) | {"manual_requests", "smart_floor"}, set(SEED_FIELDS))

    def test_explicit_floor_wins_and_missing_settings_are_skipped(self):
        spec = {**SCOPES["cli"], "smart_floor": 0.3}
        self.assertEqual(MIGRATION._seed(spec, {})["smart_floor"], Decimal("0.300"))
        self.assertEqual(MIGRATION._seed({**SCOPES["cli"], "smart_floor": None}, {})["smart_floor"], Decimal("1.000"))
        MIGRATION.remove_request_limit_policies(django_apps, None)
        with self.settings(REQUEST_RATE_LIMITS={}):
            MIGRATION.seed_request_limit_policies(django_apps, None)
        self.assertFalse(RequestRateLimitPolicy.objects.exists())


class PolicyTests(TestCase):
    def test_for_scope_heals_a_deleted_row_and_refuses_unknown_scopes(self):
        RequestRateLimitPolicy.objects.filter(scope="cli").delete()
        healed = RequestRateLimitPolicy.for_scope("cli")
        self.assertEqual(healed.manual_requests, SCOPES["cli"]["requests"])
        self.assertEqual(RequestRateLimitPolicy.for_scope("cli").pk, healed.pk)
        with self.assertRaisesMessage(ValueError, "Unknown request-limit scope: 'nope'"):
            RequestRateLimitPolicy.for_scope("nope")

    def test_ceilings_can_be_lowered_not_raised_or_removed(self):
        policy = RequestRateLimitPolicy.objects.get(scope="public-read")
        policy.global_cap = 100
        policy.save()
        for value in (12_001, None):
            policy.global_cap = value
            with self.subTest(value=value), self.assertRaises(ValidationError) as error:
                policy.save()
            self.assertIn("It can be lowered here, not raised", str(error.exception.message_dict["global_cap"]))

    def test_manual_limit_stays_within_the_per_caller_ceiling(self):
        policy = RequestRateLimitPolicy.objects.get(scope="cli")
        policy.identity_ceiling = 50
        policy.manual_requests = 51
        with self.assertRaises(ValidationError) as error:
            policy.save()
        self.assertEqual(
            error.exception.message_dict["manual_requests"], ["It cannot be set above the per-caller ceiling of 50."]
        )

    def test_a_policy_for_a_scope_the_settings_do_not_know_is_refused(self):
        policy = RequestRateLimitPolicy(scope="gone", label="Gone", manual_requests=1)
        with self.assertRaises(ValidationError) as error:
            policy.save()
        self.assertIn("not in REQUEST_RATE_LIMITS", str(error.exception))

    def test_str(self):
        policy = RequestRateLimitPolicy.objects.get(scope="cli")
        self.assertEqual(str(policy), "i2g-admin CLI (P1 interactive): Smart limit")
        policy.smart_enabled = False
        self.assertEqual(str(policy), "i2g-admin CLI (P1 interactive): 300/60s")
        self.assertEqual(str(RequestRateLimitState(scope="cli", factor=0.5)), "cli: × 0.50")
        self.assertEqual(str(RequestLimitProcess(host="web", pid=7)), "web:7")
        self.assertEqual(str(RequestLimitProcess(pid=7)), "?:7")


class DenylistTests(SimpleTestCase):
    def test_the_cli_and_the_assistant_cannot_touch_request_limits(self):
        for model in (RequestRateLimitPolicy, RequestRateLimitState, RequestLimitProcess):
            with self.subTest(model=model.__name__):
                self.assertIn(model._meta.label_lower, DENIED_MODEL_LABELS)
                self.assertTrue(is_model_denied(model, write=False))
                self.assertTrue(is_model_denied(model, write=True))

    def test_seed_uses_the_tier_floor(self):
        with patch.object(settings, "REQUEST_RATE_LIMITS", {"tiers": {"p3": {"floor": 0.2}}}):
            values = scope_seed("x", {**SCOPES["ai"], "smart_floor": None})
        self.assertEqual(values["smart_floor"], Decimal("0.200"))
