from django.contrib.admin.models import LogEntry
from django.test import override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_panel import CORE_APP_NEEDED
from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check.runner import NO_DENY_MAILBOX
from apps.core.tests.admin.service_credentials.graph_access.test_graph_access_check_admin import (
    EVIDENCE,
    REFERENCE,
    AccessCheckAdminFixture,
)
from apps.core.tests.admin.service_credentials.graph_config.test_graph_provider_guard import change_data


class EvidenceFieldsTests(AccessCheckAdminFixture):
    def test_a_superuser_records_the_deny_mailbox_and_the_infosec_reference(self):
        data = change_data(
            self.config, access_check_deny_mailbox=" Other-Test@Contoso.com ", permission_exception_reference=REFERENCE
        )

        response = self.client.post(self.change_url, data)

        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.access_check_deny_mailbox, "other-test@contoso.com")
        self.assertEqual(self.config.permission_exception_reference, REFERENCE)
        entry = LogEntry.objects.filter(object_id=str(self.config.pk)).latest("action_time")
        self.assertIn("InfoSec Exception Reference", entry.get_change_message())

    def test_the_deny_mailbox_must_be_a_plain_address_other_than_the_sender(self):
        for value in ("i2g@contoso.com", "a/b@contoso.com", "not a mailbox"):
            with self.subTest(value=value):
                response = self.client.post(self.change_url, change_data(self.config, access_check_deny_mailbox=value))
                self.assertEqual(response.status_code, 200)
                self.assertIn("access_check_deny_mailbox", response.context["adminform"].form.errors)

    def test_core_staff_set_the_evidence_fields_like_a_superuser(self):
        self.login_staff("core")

        page = self.client.get(self.change_url)
        response = self.client.post(
            self.change_url,
            change_data(
                self.config,
                access_check_deny_mailbox="other-test@contoso.com",
                permission_exception_reference=REFERENCE,
            ),
        )

        self.assertContains(page, 'name="permission_exception_reference"')
        self.assertContains(page, 'name="access_check_deny_mailbox"')
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(
            (self.config.permission_exception_reference, self.config.access_check_deny_mailbox),
            (REFERENCE, "other-test@contoso.com"),
        )

    def test_staff_without_the_core_app_cannot_change_them(self):
        self.login_staff("mail")

        response = self.client.post(self.change_url, change_data(self.config, permission_exception_reference=REFERENCE))

        self.assertEqual(response.status_code, 403)
        self.config.refresh_from_db()
        self.assertEqual(self.config.permission_exception_reference, "")


class AccessCheckCardTests(AccessCheckAdminFixture):
    def test_before_any_run_the_card_says_so_and_offers_the_button(self):
        page = self.client.get(self.change_url)

        self.assertContains(page, "No access check has been run with this configuration.")
        self.assertContains(page, "Go-live evidence (not required in this environment):")
        self.assertContains(page, self.run_url, count=1)
        self.assertIn(f'href="{self.run_url}"', self.card(page))
        self.assertNotContains(page, CORE_APP_NEEDED)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_in_production_the_missing_evidence_message_sits_next_to_the_button_it_names(self):
        card = self.card(self.client.get(self.change_url))

        self.assertIn("missing: no access check is recorded for the current certificate.", card)
        self.assertIn("Run access check, in the Access check section", card)
        self.assertIn(f'href="{self.run_url}" id="graph-run-access-check"', card)
        self.assertIn("bg-primary-600", card)

    def test_without_a_deny_mailbox_the_card_says_to_set_it_before_running(self):
        ready = self.card(self.client.get(self.change_url))
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(access_check_deny_mailbox="")

        card = self.card(self.client.get(self.change_url))

        self.assertNotIn("graph-access-check-run-problem", ready)
        self.assertIn(f"Before it can run: {NO_DENY_MAILBOX}", card)
        self.assertIn(f'href="{self.run_url}"', card)

    @override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True)
    def test_core_staff_get_every_control_a_superuser_gets(self):
        # The production report: an admin granted the Core app saw "Run access check" in the go-live message but no
        # button (it was superuser-only). The Core app grant now gives full control of the Graph configuration.
        self.login_staff("core", "mail")

        page = self.client.get(self.change_url)

        for label in ("Install certificate", "Download .cer", "Remove (emergency)"):
            self.assertContains(page, label)
        card = self.card(page)
        self.assertIn("missing: no access check is recorded", card)
        self.assertIn(f'href="{self.run_url}" id="graph-run-access-check"', card)
        self.assertNotIn(CORE_APP_NEEDED, card)

    def test_after_a_run_the_card_links_the_result_and_shows_the_evidence(self):
        self.client.post(self.run_url)
        check = MicrosoftGraphAccessCheck.objects.get()

        with override_settings(GRAPH_REQUIRE_ACCESS_EVIDENCE=True):
            page = self.client.get(self.change_url)

        self.assertContains(page, 'data-verdict="compliant"')
        self.assertContains(page, reverse(f"{EVIDENCE}_change", args=[check.pk]))
        self.assertContains(page, "Go-live evidence:</span>")
        self.assertNotContains(page, "missing: ")
        self.assertNotContains(page, "(not the current certificate)")

    def test_a_run_for_an_older_certificate_is_flagged(self):
        self.client.post(self.run_url)
        MicrosoftGraphAccessCheck.objects.update(certificate=None)

        page = self.client.get(self.change_url)

        self.assertContains(page, "(not the current certificate)")
        self.assertContains(page, "missing: no access check is recorded for the current certificate")

    def test_core_staff_see_the_result_and_the_button_to_run_it_again(self):
        self.client.post(self.run_url)
        self.login_staff("core")

        page = self.client.get(self.change_url)

        self.assertContains(page, 'data-verdict="compliant"')
        self.assertIn(f'href="{self.run_url}"', self.card(page))
        self.assertNotContains(page, CORE_APP_NEEDED)
