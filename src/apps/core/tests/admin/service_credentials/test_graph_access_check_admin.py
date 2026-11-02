"""The access check in the admin: the superuser-only "Run access check" page, the read-only evidence list, the
superuser-only evidence fields on the Graph config, and the access-check card on the certificate panel."""

from django.contrib.admin.models import LogEntry
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check.runner import NO_DENY_MAILBOX
from apps.core.tests.admin.service_credentials.test_graph_provider_guard import change_data
from apps.core.tests.services.graph_access.helpers import DENY, OIT_ROLES, ProbeFixtureMixin, Verdict
from apps.event.tests.helpers import make_admin, make_superuser

PREFIX = "admin:core_microsoftgraphproviderconfig"
EVIDENCE = "admin:core_microsoftgraphaccesscheck"
REFERENCE = "RITM0450999"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class AccessCheckAdminFixture(ProbeFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        self.run_url = reverse(f"{PREFIX}_run_access_check", args=[self.config.pk])
        self.change_url = reverse(f"{PREFIX}_change", args=[self.config.pk])

    def login_staff(self, *apps):
        self.client.force_login(make_admin(apps=list(apps), email=f"staff-{'-'.join(apps) or 'none'}@example.com"))


class RunAccessCheckPageTests(AccessCheckAdminFixture):
    def test_the_confirmation_page_explains_the_run_and_makes_no_request(self):
        response = self.client.get(self.run_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, DENY)
        self.assertContains(response, self.config.current_certificate.sha1_thumbprint)
        self.assertContains(response, "keep no Sent Items copy")
        self.assertNotContains(response, " disabled>")
        self.assertEqual(self.probe.calls, [])

    def test_running_it_records_the_evidence_and_shows_the_result(self):
        response = self.client.post(self.run_url)

        check = MicrosoftGraphAccessCheck.objects.get()
        self.assertRedirects(response, reverse(f"{EVIDENCE}_change", args=[check.pk]))
        self.assertEqual((check.source, check.run_by, check.verdict), ("admin", self.superuser, Verdict.COMPLIANT))
        self.assertEqual(check.deny_mailbox, DENY)
        [message] = list(get_messages(response.wsgi_request))
        self.assertIn("Verdict: MATCHES THE APPROVAL", message.message)
        self.assertEqual(message.level_tag, "success")
        page = self.client.get(response.url)
        self.assertContains(page, "Matches the approval")
        self.assertContains(page, "ErrorAccessDenied")
        self.assertContains(page, "Mail.Read, Mail.Send")

    def test_a_run_that_does_not_match_is_reported_as_an_error(self):
        self.use_roles(OIT_ROLES)

        response = self.client.post(self.run_url, follow=True)

        [message] = list(response.context["messages"])
        self.assertEqual(message.level_tag, "error")
        self.assertIn("BEYOND the approval (Mail.ReadWrite)", message.message)
        self.assertContains(response, "Mail.ReadWrite, Mail.Send")

    def test_without_a_designated_deny_mailbox_the_check_does_not_run(self):
        MicrosoftGraphProviderConfig.objects.filter(pk=self.config.pk).update(access_check_deny_mailbox="")

        page = self.client.get(self.run_url)
        response = self.client.post(self.run_url)

        self.assertContains(page, NO_DENY_MAILBOX)
        self.assertContains(page, " disabled>")
        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.assertEqual([m.message for m in get_messages(response.wsgi_request)], [NO_DENY_MAILBOX])
        self.assertEqual(self.probe.calls, [])
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_only_superusers_may_open_or_run_it(self):
        for apps in (("core",), ("mail",), ()):
            with self.subTest(apps=apps):
                self.login_staff(*apps)
                self.assertEqual(self.client.get(self.run_url).status_code, 403)
                self.assertEqual(self.client.post(self.run_url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.run_url).status_code, 302)
        self.assertEqual(self.probe.calls, [])
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_an_unknown_config_is_a_404(self):
        url = reverse(f"{PREFIX}_run_access_check", args=["00000000-0000-0000-0000-000000000000"])

        self.assertEqual(self.client.post(url).status_code, 404)


class EvidenceListTests(AccessCheckAdminFixture):
    def setUp(self):
        super().setUp()
        self.client.post(self.run_url)
        self.check = MicrosoftGraphAccessCheck.objects.get()

    def test_core_staff_can_read_the_evidence_but_nobody_can_change_or_delete_it(self):
        detail = reverse(f"{EVIDENCE}_change", args=[self.check.pk])
        for login in (lambda: self.client.force_login(self.superuser), lambda: self.login_staff("core")):
            login()
            with self.subTest(user=self.client.session.get("_auth_user_id")):
                self.assertContains(self.client.get(reverse(f"{EVIDENCE}_changelist")), DENY)
                self.assertContains(self.client.get(detail), self.check.certificate_sha1)
                self.assertEqual(self.client.get(reverse(f"{EVIDENCE}_add")).status_code, 403)
                self.assertEqual(self.client.post(detail, {"verdict": "compliant"}).status_code, 403)
                delete = reverse(f"{EVIDENCE}_delete", args=[self.check.pk])
                self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get(), self.check)

    def test_mail_only_staff_cannot_see_the_evidence(self):
        self.login_staff("mail")

        self.assertEqual(self.client.get(reverse(f"{EVIDENCE}_changelist")).status_code, 403)

    def test_the_results_table_escapes_what_it_shows(self):
        self.check.results = [{**self.check.results[0], "note": "<script>alert(1)</script>"}]
        self.check.save()

        page = self.client.get(reverse(f"{EVIDENCE}_change", args=[self.check.pk]))

        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")


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

    def test_core_staff_see_the_evidence_fields_read_only_and_cannot_change_them(self):
        self.login_staff("core")

        page = self.client.get(self.change_url)
        self.client.post(self.change_url, change_data(self.config, permission_exception_reference=REFERENCE))

        self.assertContains(page, DENY)
        self.assertNotContains(page, 'name="permission_exception_reference"')
        self.assertNotContains(page, 'name="access_check_deny_mailbox"')
        self.config.refresh_from_db()
        self.assertEqual(
            (self.config.permission_exception_reference, self.config.access_check_deny_mailbox), ("", DENY)
        )


class AccessCheckCardTests(AccessCheckAdminFixture):
    def test_before_any_run_the_card_says_so_and_superusers_get_the_button(self):
        page = self.client.get(self.change_url)

        self.assertContains(page, "No access check has been run with this configuration.")
        self.assertContains(page, "Go-live evidence (not required in this environment):")
        self.assertContains(page, self.run_url)

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

    def test_core_staff_see_the_card_without_the_run_button(self):
        self.client.post(self.run_url)
        self.login_staff("core")

        page = self.client.get(self.change_url)

        self.assertContains(page, 'data-verdict="compliant"')
        self.assertNotContains(page, self.run_url)
