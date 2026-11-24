"""The access check in the admin: the "Run access check" page, the read-only evidence list, the evidence fields on the
Graph config (every Admin, like the rest of the config), and the access-check card on the certificate panel."""

from unittest.mock import patch

from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph.config import MicrosoftGraphProviderConfigAdmin
from apps.core.models import MicrosoftGraphAccessCheck, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.access_check.runner import NO_DENY_MAILBOX
from apps.core.tests.services.graph_access.helpers import DENY, EXTRA_ROLES, ProbeFixtureMixin, Verdict
from apps.event.tests.helpers import make_admin, make_member, make_superuser

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

    def login_other_admin(self):
        """Sign in as a second Admin (not the fixture's): every Admin has the same controls."""
        self.client.force_login(make_admin(email="other-admin@example.com"))

    def login_member(self):
        """Sign in as a member who is not an Admin."""
        self.client.force_login(make_member(email="member@example.com"))

    def card(self, page) -> str:
        """The access check card: it closes the certificate panel, so it runs up to the panel's end."""
        html = page.content.decode()
        start = html.index('id="graph-access-check"')
        return html[start : html.index("</section>", start)]


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
        self.assertContains(page, "Mail.ReadWrite, Mail.Send")
        self.assertContains(page, "Mail.Read, Mail.ReadWrite, Mail.Send")

    def test_a_run_that_does_not_match_is_reported_as_an_error(self):
        self.use_roles(EXTRA_ROLES)

        response = self.client.post(self.run_url, follow=True)

        [message] = list(response.context["messages"])
        self.assertEqual(message.level_tag, "error")
        self.assertIn("BEYOND the approval (User.Read.All)", message.message)
        self.assertContains(response, "Mail.Send, User.Read.All")

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

    def test_any_admin_runs_it(self):
        staff = make_admin(email="other-admin@example.com")
        self.client.force_login(staff)

        self.assertEqual(self.client.get(self.run_url).status_code, 200)
        response = self.client.post(self.run_url)

        check = MicrosoftGraphAccessCheck.objects.get()
        self.assertRedirects(response, reverse(f"{EVIDENCE}_change", args=[check.pk]))
        self.assertEqual((check.run_by, check.verdict), (staff, Verdict.COMPLIANT))

    def test_members_who_are_not_admins_may_not_open_or_run_it(self):
        self.login_member()
        for response in (self.client.get(self.run_url), self.client.post(self.run_url)):
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/", response["Location"])
        self.client.logout()
        self.assertEqual(self.client.post(self.run_url).status_code, 302)
        self.assertEqual(self.probe.calls, [])
        self.assertFalse(MicrosoftGraphAccessCheck.objects.exists())

    def test_it_follows_the_change_permission(self):
        with patch.object(MicrosoftGraphProviderConfigAdmin, "has_change_permission", return_value=False):
            response = self.client.post(self.run_url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.probe.calls, [])

    def test_an_unknown_config_is_a_404(self):
        url = reverse(f"{PREFIX}_run_access_check", args=["00000000-0000-0000-0000-000000000000"])

        self.assertEqual(self.client.post(url).status_code, 404)


class EvidenceListTests(AccessCheckAdminFixture):
    def setUp(self):
        super().setUp()
        self.client.post(self.run_url)
        self.check = MicrosoftGraphAccessCheck.objects.get()

    def test_admins_can_read_the_evidence_but_nobody_can_change_or_delete_it(self):
        detail = reverse(f"{EVIDENCE}_change", args=[self.check.pk])
        for login in (lambda: self.client.force_login(self.superuser), self.login_other_admin):
            login()
            with self.subTest(user=self.client.session.get("_auth_user_id")):
                self.assertContains(self.client.get(reverse(f"{EVIDENCE}_changelist")), DENY)
                self.assertContains(self.client.get(detail), self.check.certificate_sha1)
                self.assertEqual(self.client.get(reverse(f"{EVIDENCE}_add")).status_code, 403)
                self.assertEqual(self.client.post(detail, {"verdict": "compliant"}).status_code, 403)
                delete = reverse(f"{EVIDENCE}_delete", args=[self.check.pk])
                self.assertEqual(self.client.post(delete, {"post": "yes"}).status_code, 403)
        self.assertEqual(MicrosoftGraphAccessCheck.objects.get(), self.check)

    def test_members_who_are_not_admins_cannot_see_the_evidence(self):
        self.login_member()

        response = self.client.get(reverse(f"{EVIDENCE}_changelist"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_the_results_table_escapes_what_it_shows(self):
        self.check.results = [{**self.check.results[0], "note": "<script>alert(1)</script>"}]
        self.check.save()

        page = self.client.get(reverse(f"{EVIDENCE}_change", args=[self.check.pk]))

        self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;")
