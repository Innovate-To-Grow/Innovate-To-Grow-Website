"""The go-live gate: where ``GRAPH_REQUIRE_ACCESS_EVIDENCE`` is on (production), email may switch to Microsoft Graph
only with a recent access check that matched the approval for the current certificate."""

import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import EmailServiceConfig, MicrosoftGraphAccessCheck, MicrosoftGraphCertificate
from apps.core.models.base.service_credentials.microsoft_graph_access_check import go_live_problem
from apps.core.tests.graph_helpers import create_graph_config, install_test_certificate

Verdict = MicrosoftGraphAccessCheck.Verdict
SENDER = "i2g@contoso.com"
DENY = "intruder-test@contoso.com"


def evidence(config, *, certificate=None, age_days=0, **values):
    """An access check row as a compliant run records it, for *config*'s current certificate unless given."""
    certificate = certificate or config.current_certificate
    row = {
        "config": config,
        "certificate": certificate,
        "certificate_sha1": certificate.sha1_thumbprint,
        "tenant_id": config.tenant_id,
        "client_id": config.client_id,
        "deny_mailbox": DENY,
        "source": MicrosoftGraphAccessCheck.Source.COMMAND,
        "granted_roles": ["Mail.Read", "Mail.Send"],
        "approved_roles": ["Mail.Read", "Mail.Send"],
        "mailbox_restriction_passed": True,
        "roles_within_approval": True,
        "complete": True,
        "verdict": Verdict.COMPLIANT,
        **values,
    }
    check = MicrosoftGraphAccessCheck.objects.create(**row)
    if age_days:
        created = timezone.now() - datetime.timedelta(days=age_days)
        MicrosoftGraphAccessCheck.objects.filter(pk=check.pk).update(created_at=created)
    return check


@override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True, GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS=30)
class GoLiveProblemTests(TestCase):
    def setUp(self):
        self.config = create_graph_config(
            scope=(SENDER,), name="Graph", is_active=True, mailbox=SENDER, access_check_deny_mailbox=DENY
        )

    def test_a_recent_compliant_check_for_the_current_certificate_is_evidence(self):
        evidence(self.config, age_days=29)

        self.assertEqual(go_live_problem(self.config), "")

    def test_without_any_check_there_is_no_evidence(self):
        self.assertIn("no access check is recorded for the current certificate", go_live_problem(self.config))

    def test_a_check_of_another_certificate_does_not_count(self):
        previous = install_test_certificate(self.config, state=MicrosoftGraphCertificate.State.PREVIOUS, key_index=1)
        evidence(self.config, certificate=previous)

        self.assertIn("no access check is recorded for the current certificate", go_live_problem(self.config))

    def test_evidence_older_than_the_setting_has_expired(self):
        evidence(self.config, age_days=31)

        self.assertIn("more than 30 days old", go_live_problem(self.config))
        with override_settings(GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS=60):
            self.assertEqual(go_live_problem(self.config), "")

    def test_only_a_run_against_the_designated_deny_mailbox_counts(self):
        evidence(self.config, deny_mailbox="someone-else@contoso.com")
        self.assertIn("did not use the designated deny mailbox", go_live_problem(self.config))

        evidence(self.config)
        self.config.access_check_deny_mailbox = ""
        self.assertIn("did not use the designated deny mailbox", go_live_problem(self.config))

    def test_an_incomplete_or_failing_latest_check_is_not_evidence(self):
        evidence(self.config, age_days=2)
        for verdict, text in ((Verdict.INCOMPLETE, "not a complete validation"), (Verdict.NOT_COMPLIANT, "does not")):
            with self.subTest(verdict=verdict):
                evidence(self.config, verdict=verdict, complete=False)
                self.assertIn(f"the latest access check found: {text}", go_live_problem(self.config))

    def test_extra_roles_need_the_exception_reference_to_still_be_recorded(self):
        extra = {"granted_roles": ["Mail.ReadWrite", "Mail.Send"], "roles_within_approval": False}
        evidence(self.config, permission_exception_reference="RITM0450999", **extra)
        self.config.permission_exception_reference = "RITM0450999"
        self.assertEqual(go_live_problem(self.config), "")

        self.config.permission_exception_reference = ""
        problem = go_live_problem(self.config)

        self.assertIn("claims Mail.ReadWrite beyond the approval", problem)
        self.assertIn("no InfoSec exception reference is recorded", problem)

    @override_settings(GRAPH_APPROVED_APPLICATION_ROLES=("Mail.Send",))
    def test_a_narrowed_approval_withdraws_earlier_evidence(self):
        evidence(self.config)

        self.assertIn("claims Mail.Read beyond the approval", go_live_problem(self.config))

    def test_an_unsaved_config_has_no_evidence(self):
        unsaved = type(self.config)()

        self.assertIn("no access check is recorded", go_live_problem(unsaved))


class ActivationGateTests(TestCase):
    """``EmailServiceConfig.validate_activation`` applies the gate only where the setting is on."""

    def setUp(self):
        self.graph = create_graph_config(
            scope=(SENDER,), name="Graph", is_active=True, mailbox=SENDER, access_check_deny_mailbox=DENY
        )
        self.email = EmailServiceConfig.objects.create(name="Mail", is_active=True, provider="ses", from_email=SENDER)

    def switch_to_graph(self, email=None):
        email = email or self.email
        email.provider = EmailServiceConfig.Provider.GRAPH
        email.validate_activation()

    def test_off_by_default_outside_production(self):
        self.switch_to_graph()

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_on_the_switch_is_refused_without_evidence(self):
        with self.assertRaises(ValidationError) as error:
            self.switch_to_graph()

        message = error.exception.message_dict["provider"][0]
        self.assertTrue(message.startswith("Email cannot switch to Microsoft Graph yet: no access check is recorded"))
        self.assertIn("Run access check", message)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_on_the_switch_is_allowed_with_evidence(self):
        evidence(self.graph)

        self.switch_to_graph()

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_the_sending_readiness_check_still_comes_first(self):
        evidence(self.graph)
        self.email.from_email = "outside@contoso.com"

        with self.assertRaisesMessage(ValidationError, "mailbox scope lets the sender mailbox and the From address"):
            self.switch_to_graph()

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_editing_a_config_that_already_sends_through_graph_is_not_a_switch(self):
        EmailServiceConfig.objects.filter(pk=self.email.pk).update(provider="graph")
        self.email.refresh_from_db()
        self.email.from_name = "Renamed"

        self.email.validate_activation()

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_activating_another_graph_config_is_a_switch(self):
        EmailServiceConfig.objects.filter(pk=self.email.pk).update(provider="graph")
        standby = EmailServiceConfig.objects.create(name="Standby", provider="graph", from_email=SENDER)
        standby.is_active = True

        with self.assertRaisesMessage(ValidationError, "Email cannot switch to Microsoft Graph yet"):
            standby.validate_activation()
