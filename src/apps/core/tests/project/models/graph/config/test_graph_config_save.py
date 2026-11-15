from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.core.models import (
    MicrosoftGraphProviderConfig,
)
from apps.core.tests.project.models.graph.config.test_microsoft_graph_config import (
    OBJECT_ID,
    graph_fields,
    loaded,
    make_graph,
)


class GraphConfigSaveTest(TestCase):
    def test_save_rejects_a_blank_tenant_and_writes_nothing(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(tenant_id=""))

        with self.assertRaises(ValidationError) as error:
            config.save()

        self.assertIn("tenant_id", error.exception.message_dict)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_save_rejects_each_invalid_value_and_writes_nothing(self):
        invalid = (
            {"tenant_id": "common"},
            {"client_id": "not-a-guid"},
            {"mailbox": "garbage"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                MicrosoftGraphProviderConfig(**graph_fields(**overrides)).save()

        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_activating_a_second_config_deactivates_the_first(self):
        first = make_graph(name="First", is_active=True)
        second = make_graph(name="Second", is_active=True)

        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), second)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_rejected_activation_leaves_the_current_active_config_in_place(self):
        current = make_graph(name="Current", is_active=True)

        with self.assertRaises(ValidationError):
            MicrosoftGraphProviderConfig(**graph_fields(name="Next", is_active=True, tenant_id="common")).save()

        current.refresh_from_db()
        self.assertTrue(current.is_active)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)

    def test_resaving_the_active_config_keeps_it_active(self):
        active = make_graph(is_active=True)

        active.name = "Renamed"
        active.save()

        active.refresh_from_db()
        self.assertTrue(active.is_active)
        self.assertEqual(active.name, "Renamed")

    def test_saving_an_inactive_config_leaves_the_active_one_alone(self):
        active = make_graph(name="Active", is_active=True)

        make_graph(name="Standby", certificate=False)

        active.refresh_from_db()
        self.assertTrue(active.is_active)

    def test_validation_does_not_reject_switching_the_active_config(self):
        make_graph(name="Active", is_active=True)
        standby = make_graph(name="Standby")
        standby.is_active = True

        standby.full_clean()

        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_database_rejects_two_active_configs_when_save_is_bypassed(self):
        make_graph(name="Primary", is_active=True)
        standby = make_graph(name="Standby")

        with self.assertRaises(IntegrityError), transaction.atomic():
            MicrosoftGraphProviderConfig.objects.filter(pk=standby.pk).update(is_active=True)

        self.assertEqual(MicrosoftGraphProviderConfig.objects.filter(is_active=True).count(), 1)

    def test_single_active_constraint_has_the_documented_name(self):
        names = {constraint.name for constraint in MicrosoftGraphProviderConfig._meta.constraints}

        self.assertIn("core_one_active_graph_provider_config", names)


class GraphConfigLoadTest(TestCase):
    def test_returns_the_active_config(self):
        make_graph(name="Standby")
        active = make_graph(name="Active", is_active=True)

        self.assertEqual(MicrosoftGraphProviderConfig.load(), active)

    def test_returns_an_unsaved_default_when_nothing_is_active(self):
        config = MicrosoftGraphProviderConfig.load()

        self.assertTrue(config._state.adding)
        self.assertFalse(config.is_configured)
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())

    def test_never_falls_back_to_an_inactive_config(self):
        inactive = make_graph(name="Inactive")

        config = MicrosoftGraphProviderConfig.load()

        self.assertTrue(config._state.adding)
        self.assertNotEqual(config.pk, inactive.pk)
        self.assertEqual((config.tenant_id, config.client_id), ("", ""))
        self.assertIsNone(config.current_certificate)
        self.assertFalse(config.is_configured)
        self.assertEqual(MicrosoftGraphProviderConfig.objects.count(), 1)


class GraphConfigIsConfiguredTest(TestCase):
    def test_requires_an_active_saved_config_with_every_credential(self):
        cases = (
            ("every credential present", {}, True),
            ("blank mailbox falls back to the From address", {"mailbox": ""}, True),
            ("inactive", {"is_active": False}, False),
            ("missing tenant", {"tenant_id": ""}, False),
            ("missing client id", {"client_id": ""}, False),
            ("no installed certificate", {"certificate": False}, False),
            ("expired certificate", {"certificate": {"days_valid": -1, "not_before_days": -30}}, False),
            ("certificate not valid yet", {"certificate": {"not_before_days": 2}}, False),
            ("previous certificate only", {"certificate": {"state": "previous"}}, False),
            ("tenant that is neither a GUID nor a domain", {"tenant_id": "common"}, False),
            ("tenant that adds a path segment", {"tenant_id": "contoso.com/../x"}, False),
            ("client id that is not a GUID", {"client_id": "not-a-guid"}, False),
            ("mailbox that is not an address or GUID", {"mailbox": "not a mailbox"}, False),
            ("object id mailbox", {"mailbox": OBJECT_ID}, True),
            ("domain tenant", {"tenant_id": "contoso.onmicrosoft.com"}, True),
        )
        for label, overrides, expected in cases:
            with self.subTest(label):
                self.assertIs(loaded(**overrides).is_configured, expected)

    def test_a_never_saved_instance_is_not_configured(self):
        config = MicrosoftGraphProviderConfig(**graph_fields(is_active=True))

        self.assertFalse(config.is_configured)


class GraphConfigSavedIsConfiguredTest(TestCase):
    def test_a_saved_active_config_is_configured(self):
        config = make_graph(is_active=True)

        self.assertTrue(config.is_configured)
        self.assertTrue(MicrosoftGraphProviderConfig.load().is_configured)

    def test_a_saved_inactive_config_is_not_configured(self):
        self.assertFalse(make_graph().is_configured)
