"""Operator acceptance is visible in both admin panels without becoming approval or isolation evidence."""

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.tests.admin.service_credentials.test_graph_access_check_admin import AccessCheckAdminFixture
from apps.core.tests.models.test_graph_go_live_gate import evidence
from apps.core.tests.services.graph_access.helpers import DENY, OIT_ROLES


@override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
class OitPolicyPanelTests(AccessCheckAdminFixture):
    client_class = APIClient

    def setUp(self):
        super().setUp()
        self.policy = {
            "config_id": str(self.config.pk),
            "tenant_id": self.config.tenant_id,
            "client_id": self.config.client_id,
            "mailbox": self.config.mailbox,
            "accepted_roles": OIT_ROLES,
            "accepted_on": "2026-11-02",
        }
        self.policy_settings = override_settings(GRAPH_OIT_PROVISIONED_ACTIVATION=self.policy)
        self.policy_settings.enable()
        self.addCleanup(self.policy_settings.disable)

    def test_core_panel_keeps_operator_acceptance_and_missing_evidence_separate(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(access_check_deny_mailbox="")

        page = self.client.get(self.change_url)

        self.assertContains(page, "Operator-accepted OIT configuration")
        self.assertContains(page, "Operator acceptance recorded 2026-11-02")
        self.assertContains(page, "Mail.ReadWrite, Mail.Send")
        self.assertContains(page, self.config.mailbox)
        self.assertContains(page, "Microsoft mailbox isolation: <strong>unverified</strong>")
        self.assertContains(page, "No access check has been run with this configuration.")
        self.assertContains(page, "missing: no access check is recorded for the current certificate")
        self.assertContains(page, "Deny mailbox: not set")
        self.assertContains(page, "InfoSec exception: none recorded")
        self.assertNotContains(page, 'data-verdict="compliant"')
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())
        self.config.refresh_from_db()
        self.assertEqual(self.config.permission_exception_reference, "")
        self.assertEqual(self.probe.calls, [])

    def test_mail_only_staff_see_the_same_policy_and_unverified_state(self):
        self.login_staff("mail")

        page = self.client.get(reverse("admin:mail_settings_edit"))

        self.assertContains(page, 'data-activation-policy="oit-provisioned"')
        self.assertContains(page, "Microsoft mailbox isolation: <strong>unverified</strong>")
        self.assertContains(
            page, "Operator acceptance does not establish mailbox isolation or additional InfoSec approval"
        )
        self.assertNotContains(page, self.run_url)
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())
        self.assertEqual(self.probe.calls, [])

    def test_an_unmatched_configuration_does_not_display_operator_acceptance(self):
        with override_settings(GRAPH_OIT_PROVISIONED_ACTIVATION={**self.policy, "config_id": "another-config"}):
            page = self.client.get(self.change_url)

        self.assertNotContains(page, 'data-activation-policy="oit-provisioned"')
        self.assertContains(page, "Go-live evidence:</span>")
        self.assertContains(page, "missing: no access check is recorded for the current certificate")

    def test_verified_isolation_does_not_relabel_a_roles_failure_as_infosec_approval(self):
        self.use_roles(OIT_ROLES)
        self.client.post(self.run_url)  # The fixture replaces every Microsoft request with ProbeFake.

        page = self.client.get(self.change_url)

        self.assertContains(page, "Microsoft mailbox isolation: <strong>verified by a recent access check</strong>")
        self.assertContains(page, 'data-verdict="not_compliant"')
        self.assertContains(page, "Does not match the approval")
        self.assertContains(page, "(beyond the approval)")
        self.assertContains(page, "InfoSec exception: none recorded")
        self.assertNotContains(page, 'data-verdict="compliant"')

    def test_probes_for_another_mailbox_do_not_verify_the_operator_accepted_mailbox(self):
        self.client.post(self.run_url)
        check = MicrosoftGraphAccessCheck.objects.get()
        results = check.results
        for kind in ("folder", "list", "send"):
            with self.subTest(kind=kind):
                changed = [
                    {**result, "mailbox": "other@contoso.com"}
                    if result["check"] == kind and result["expected"] == "allowed"
                    else result
                    for result in results
                ]
                MicrosoftGraphAccessCheck.objects.filter(pk=check.pk).update(results=changed)

                page = self.client.get(self.change_url)

                self.assertContains(page, "Microsoft mailbox isolation: <strong>unverified</strong>")

    def test_stale_incomplete_or_unrelated_evidence_does_not_verify_isolation(self):
        self.client.post(self.run_url)
        results = MicrosoftGraphAccessCheck.objects.get().results
        cases = (
            {"age_days": 31},
            {"complete": False},
            {"mailbox_restriction_passed": False},
            {"deny_mailbox": "different-test@contoso.com"},
            {"old_certificate": True},
            {"no_designated_mailbox": True},
        )
        for case in cases:
            with self.subTest(case=case):
                MicrosoftGraphAccessCheck.objects.all().delete()
                values = dict(case)
                old_certificate = values.pop("old_certificate", False)
                no_designated_mailbox = values.pop("no_designated_mailbox", False)
                MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(
                    access_check_deny_mailbox="" if no_designated_mailbox else DENY
                )
                check = evidence(self.config, results=results, **values)
                if old_certificate:
                    MicrosoftGraphAccessCheck.objects.filter(pk=check.pk).update(certificate=None)

                page = self.client.get(self.change_url)

                self.assertContains(page, "Microsoft mailbox isolation: <strong>unverified</strong>")
                self.assertContains(page, 'data-activation-policy="oit-provisioned"')
