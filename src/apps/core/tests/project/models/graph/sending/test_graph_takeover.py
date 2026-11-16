from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.core.models import (
    EmailServiceConfig,
    MicrosoftGraphCertificate,
    MicrosoftGraphProviderConfig,
)
from apps.core.tests.graph_helpers import TENANT_ID, create_graph_config
from apps.core.tests.project.models.graph.test_graph_go_live_gate import DENY, OTHER_APP, SENDER, evidence


class GraphTakeoverTests(TestCase):
    """While email is on Graph, moving it to another config or Entra app needs what switching to Graph needs."""

    def setUp(self):
        self.active = create_graph_config(
            scope=(SENDER,), name="Graph", is_active=True, mailbox=SENDER, access_check_deny_mailbox=DENY
        )
        self.email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="graph", from_email=SENDER)
        self.standby = create_graph_config(
            scope=(SENDER,), name="Standby", mailbox=SENDER, access_check_deny_mailbox=DENY, client_id=OTHER_APP
        )

    def activate(self, config):
        config.is_active = True
        config.save()

    def assert_refused(self, config, field, text):
        with self.assertRaises(ValidationError) as error:
            config.save()
        self.assertIn(text, error.exception.message_dict[field][0])
        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.active)

    def test_with_the_gate_off_a_standby_that_entra_trusts_may_take_over(self):
        self.activate(self.standby)

        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.standby)

    def test_a_standby_whose_certificate_entra_has_not_trusted_cannot_take_over(self):
        MicrosoftGraphCertificate.objects.filter(config=self.standby).update(entra_check="not_trusted")
        self.standby.is_active = True

        self.assert_refused(self.standby, "is_active", "Microsoft Entra has not issued a token")

    def test_a_standby_without_a_certificate_and_a_new_active_config_cannot_take_over(self):
        empty = create_graph_config(name="Empty", certificate=False, scope=(SENDER,))
        empty.is_active = True
        new = MicrosoftGraphProviderConfig(name="New", is_active=True, tenant_id=TENANT_ID, client_id=OTHER_APP)

        for config in (empty, new):
            with self.subTest(config=config.name):
                self.assert_refused(config, "is_active", "has no current certificate")

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_with_the_gate_on_a_standby_needs_evidence_of_its_own(self):
        evidence(self.active)
        self.standby.is_active = True

        self.assert_refused(self.standby, "is_active", "no access check is recorded for the current certificate")

        evidence(self.standby)
        self.activate(self.standby)
        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.standby)

    def test_the_active_configs_app_cannot_change_while_email_is_on_graph(self):
        MicrosoftGraphCertificate.objects.filter(config=self.active).update(state="removed")
        for field, value in (("client_id", OTHER_APP), ("tenant_id", "contoso.onmicrosoft.com")):
            with self.subTest(field=field):
                self.active.refresh_from_db()
                setattr(self.active, field, value)
                self.assert_refused(self.active, field, "its Entra application cannot change")

    def test_other_edits_of_the_active_config_are_not_a_takeover(self):
        MicrosoftGraphCertificate.objects.filter(config=self.active).update(entra_check="not_trusted")
        self.active.name = "Renamed"

        self.active.save()

    def test_with_email_on_another_provider_configs_switch_freely(self):
        EmailServiceConfig.objects.filter(pk=self.email.pk).update(provider="ses")
        MicrosoftGraphCertificate.objects.filter(config=self.standby).update(entra_check="not_trusted")

        self.activate(self.standby)
        MicrosoftGraphCertificate.objects.filter(config=self.active).update(state="removed")
        self.active.refresh_from_db()
        self.active.client_id = OTHER_APP
        self.active.save()

        self.assertEqual(MicrosoftGraphProviderConfig.load(), self.standby)
