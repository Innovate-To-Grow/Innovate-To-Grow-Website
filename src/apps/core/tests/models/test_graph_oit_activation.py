"""A deployment's explicit OIT-provisioned activation stays bound to one app, config and mailbox.

It allows activation without pretending that an access check passed or that InfoSec changed its approval.
Certificate readiness and the application's mailbox restrictions still apply.
"""

import datetime
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import (
    EmailServiceConfig,
    MicrosoftGraphAccessCheck,
    MicrosoftGraphCertificate,
    MicrosoftGraphMailboxScope,
    MicrosoftGraphProviderConfig,
)
from apps.core.models.base.service_credentials.microsoft_graph_access_check import go_live_problem, takeover_problem
from apps.core.models.base.service_credentials.microsoft_graph_policy import oit_provisioned_policy
from apps.core.services.credential_store import memory
from apps.core.services.email.graph.access import GraphScopeError, require_mailbox
from apps.core.tests.graph_helpers import create_graph_config

MAILBOX = "i2g@contoso.com"
OUTSIDE = "outside@contoso.com"
OTHER_ID = "99999999-8888-7777-6666-555555555555"
Permission = MicrosoftGraphMailboxScope.Permission


@override_settings(
    GRAPH_REQUIRE_ACCESS_EVIDENCE=True,
    GRAPH_OIT_PROVISIONED_ACTIVATION={},
    CREDENTIAL_STORE_BACKEND="memory",
)
class OitProvisionedActivationTests(TestCase):
    def setUp(self):
        cache.clear()
        memory.reset()
        self.addCleanup(memory.reset)
        self.config = create_graph_config(name="Graph", is_active=True, mailbox=MAILBOX, scope=(MAILBOX,))
        self.email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email=MAILBOX)
        self.policy = {
            "config_id": str(self.config.pk),
            "tenant_id": self.config.tenant_id,
            "client_id": self.config.client_id,
            "mailbox": MAILBOX,
            "accepted_roles": ("Mail.ReadWrite", "Mail.Send"),
            "accepted_on": "2026-11-02",
        }
        self.enterContext(override_settings(GRAPH_OIT_PROVISIONED_ACTIVATION=self.policy))

    def activate_email(self):
        self.email.provider = EmailServiceConfig.Provider.GRAPH
        self.email.validate_activation()
        self.email.save()

    def assert_activation_refused(self):
        with self.assertRaises(ValidationError):
            self.activate_email()
        self.email.refresh_from_db()
        self.assertEqual(self.email.provider, EmailServiceConfig.Provider.SES)

    def test_the_exact_provisioned_configuration_can_activate_without_fabricating_evidence(self):
        self.assertTrue(oit_provisioned_policy(self.config))
        self.assertEqual(takeover_problem(self.config), "")

        self.activate_email()

        self.assertEqual(EmailServiceConfig.load().provider, EmailServiceConfig.Provider.GRAPH)
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())
        self.config.refresh_from_db()
        self.assertEqual(self.config.permission_exception_reference, "")
        self.assertEqual(self.config.access_check_deny_mailbox, "")
        self.assertIn("no access check is recorded", go_live_problem(self.config))
        self.assertEqual(set(settings.GRAPH_APPROVED_APPLICATION_ROLES), {"Mail.Read", "Mail.Send"})

    def test_an_absent_policy_retains_the_original_access_evidence_gate(self):
        with override_settings(GRAPH_OIT_PROVISIONED_ACTIVATION={}):
            self.assertFalse(oit_provisioned_policy(self.config))
            self.assertIn("no access check is recorded", takeover_problem(self.config))
            self.assert_activation_refused()

    def test_each_identity_must_match_the_explicit_policy(self):
        for field, value in (
            ("config_id", str(uuid.uuid4())),
            ("tenant_id", OTHER_ID),
            ("client_id", OTHER_ID),
        ):
            with (
                self.subTest(field=field),
                override_settings(GRAPH_OIT_PROVISIONED_ACTIVATION=self.policy | {field: value}),
            ):
                self.assertFalse(oit_provisioned_policy(self.config))
                self.assertIn("no access check is recorded", takeover_problem(self.config))
                self.assert_activation_refused()

    def test_another_config_for_the_same_application_still_needs_its_own_evidence(self):
        other = create_graph_config(name="Other", mailbox=MAILBOX, scope=(MAILBOX,))

        self.assertFalse(oit_provisioned_policy(other))
        self.assertIn("no access check is recorded", takeover_problem(other))

    def test_the_provisioned_config_can_take_over_existing_graph_delivery(self):
        self.config.is_active = False
        self.config.save()
        other = create_graph_config(name="Other", is_active=True, mailbox=MAILBOX, scope=(MAILBOX,))
        EmailServiceConfig.objects.filter(pk=self.email.pk).update(provider=EmailServiceConfig.Provider.GRAPH)

        self.config.is_active = True
        self.config.save()

        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.config)
        other.refresh_from_db()
        self.assertFalse(other.is_active)
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())
        self.assertIn("no access check is recorded", go_live_problem(self.config))

    def test_the_policy_does_not_replace_a_usable_certificate_or_entra_acceptance(self):
        certificate = self.config.current_certificate
        original = {
            field: getattr(certificate, field)
            for field in (
                "state",
                "not_after",
                "not_before",
                "tenant_id",
                "client_id",
                "store_version_id",
                "entra_check",
            )
        }
        changes = {
            "removed": {"state": MicrosoftGraphCertificate.State.REMOVED},
            "expired": {"not_after": timezone.now() - datetime.timedelta(days=1)},
            "not yet valid": {"not_before": timezone.now() + datetime.timedelta(days=1)},
            "different tenant": {"tenant_id": OTHER_ID},
            "different application": {"client_id": OTHER_ID},
            "no stored key": {"store_version_id": ""},
            "not trusted": {"entra_check": MicrosoftGraphCertificate.EntraCheck.NOT_TRUSTED},
            "unreachable": {"entra_check": MicrosoftGraphCertificate.EntraCheck.UNREACHABLE},
        }
        for label, values in changes.items():
            with self.subTest(label=label):
                MicrosoftGraphCertificate.objects.filter(pk=certificate.pk).update(**(original | values))
                self.assertTrue(takeover_problem(self.config))
                self.assert_activation_refused()
        MicrosoftGraphCertificate.objects.filter(pk=certificate.pk).update(**original)

    def test_a_different_sender_or_from_address_cannot_use_the_policy(self):
        self.config.mailbox_scopes.create(mailbox=OUTSIDE, permission=Permission.SEND_AND_READ)
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(mailbox=OUTSIDE)
        self.config.refresh_from_db()

        self.assertTrue(takeover_problem(self.config))
        self.assert_activation_refused()

        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(mailbox=MAILBOX)
        self.config.mailbox_scopes.filter(mailbox=OUTSIDE).delete()
        self.email.from_email = OUTSIDE
        self.assert_activation_refused()

    def test_an_implicit_sender_is_not_an_exact_provisioned_sender(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(mailbox="")
        self.config.refresh_from_db()

        self.assertTrue(takeover_problem(self.config))
        self.assert_activation_refused()

    def test_the_stored_scope_must_be_exactly_the_provisioned_send_and_read_mailbox(self):
        scope = self.config.mailbox_scopes.get()
        for permission in (Permission.SEND, Permission.READ):
            with self.subTest(permission=permission):
                self.config.mailbox_scopes.filter(pk=scope.pk).update(permission=permission)
                self.assertTrue(takeover_problem(self.config))
                self.assert_activation_refused()
        self.config.mailbox_scopes.filter(pk=scope.pk).update(permission=Permission.SEND_AND_READ)
        extra = self.config.mailbox_scopes.create(mailbox=OUTSIDE, permission=Permission.SEND_AND_READ)
        self.assertTrue(takeover_problem(self.config))
        self.assert_activation_refused()
        extra.delete()
        scope.delete()
        self.assertTrue(takeover_problem(self.config))
        self.assert_activation_refused()

    def test_runtime_refuses_an_outside_mailbox_even_if_a_scope_row_is_added(self):
        self.config.mailbox_scopes.create(mailbox=OUTSIDE, permission=Permission.SEND_AND_READ)

        for permission in ("send", "read"):
            with self.subTest(permission=permission):
                self.assertTrue(self.config.allows(MAILBOX, permission))
                self.assertEqual(require_mailbox(self.config, MAILBOX, permission), MAILBOX)
                self.assertFalse(self.config.allows(OUTSIDE, permission))
                with self.assertRaises(GraphScopeError):
                    require_mailbox(self.config, OUTSIDE, permission)
        self.assertFalse(self.config.allows(MAILBOX, "write"))
        self.assertFalse(self.config.allows(MAILBOX, "delete"))

    def test_runtime_also_clamps_proposed_scopes_before_they_are_saved(self):
        proposed = {MAILBOX: Permission.SEND_AND_READ, OUTSIDE: Permission.SEND_AND_READ}

        for permission in ("send", "read"):
            with self.subTest(permission=permission):
                self.assertTrue(self.config.allows(MAILBOX, permission, scopes=proposed))
                self.assertFalse(self.config.allows(OUTSIDE, permission, scopes=proposed))
        self.assertFalse(self.config.allows(MAILBOX, "read", scopes={MAILBOX: Permission.SEND}))
        self.assertFalse(self.config.allows(MAILBOX, "send", scopes={}))

    def test_unmatched_configs_keep_the_existing_runtime_scope_behavior(self):
        other = create_graph_config(name="Other", mailbox=OUTSIDE, scope=(OUTSIDE,))

        self.assertTrue(other.allows(OUTSIDE, "send"))
        self.assertTrue(other.allows(OUTSIDE, "read"))
        self.assertFalse(other.allows(MAILBOX, "send"))
