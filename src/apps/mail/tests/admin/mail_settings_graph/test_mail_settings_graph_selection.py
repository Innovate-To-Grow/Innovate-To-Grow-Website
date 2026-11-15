from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.mail_settings_graph.test_mail_settings_admin_graph import (
    GRAPH_CONFIG_URL_NAME,
    GRAPH_INPUTS,
    PROVIDER_ERROR,
    GraphSettingsTestCase,
    snapshot,
)


class SelectingGraphTests(GraphSettingsTestCase):
    def test_graph_cannot_be_selected_without_a_graph_config(self):
        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertFalse(MicrosoftGraphProviderConfig.objects.exists())
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")

    def test_selecting_graph_activates_the_provider_and_leaves_the_graph_config_untouched(self):
        graph = self.make_graph()
        before = snapshot(graph)

        response = self.client.post(self.edit_url, self.post_data("graph"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.assertEqual((self.config.provider, self.config.from_email), ("graph", "updated@example.com"))
        self.assertTrue(self.config.delivery_configured)
        self.assertEqual(snapshot(graph), before)
        self.assertEqual(EmailServiceConfig.objects.count(), 1)

    def test_saving_reports_success_and_the_summary_names_the_graph_mailbox(self):
        self.make_graph()
        response = self.client.post(self.edit_url, self.post_data("graph"), follow=True)

        self.assertContains(response, "Notification delivery settings saved.")
        self.assert_chip(response, "Microsoft Graph (mailer@example.com)", "success")

    def test_graph_inputs_posted_here_change_nothing(self):
        graph = self.make_graph()
        before = snapshot(graph)
        certificate = graph.current_certificate

        for provider in ("graph", "ses", "smtp"):
            with self.subTest(provider=provider):
                response = self.client.post(self.edit_url, self.post_data(provider, **GRAPH_INPUTS))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.assertEqual(snapshot(graph), before)
                self.assertEqual(graph.current_certificate, certificate)

    def test_graph_without_a_mailbox_falls_back_to_the_from_email(self):
        self.make_graph(mailbox="")
        response = self.client.post(self.edit_url, self.post_data("graph"), follow=True)

        self.assert_chip(response, "Microsoft Graph (updated@example.com)", "success")

    def test_selecting_graph_retains_the_aws_credentials_used_for_sms(self):
        self.make_graph()
        before = snapshot(self.aws_config)

        self.client.post(self.edit_url, self.post_data("graph"))

        after = snapshot(self.aws_config)
        for row in (before, after):
            row.pop("updated_at")
        self.assertEqual(after, before)
        self.assertTrue(AWSCredentialConfig.load().sns_configured)

    def test_round_trip_through_every_provider_keeps_the_graph_config(self):
        graph = self.make_graph()
        before = snapshot(graph)
        for provider in ("graph", "ses", "smtp", "graph"):
            with self.subTest(provider=provider):
                response = self.client.post(self.edit_url, self.post_data(provider))

                self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
                self.config.refresh_from_db()
                self.assertEqual(self.config.provider, provider)
                self.assertEqual(snapshot(graph), before)

    def test_selecting_smtp_still_saves_the_smtp_config(self):
        self.make_graph()

        response = self.client.post(self.edit_url, self.post_data("smtp"))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.smtp_config.refresh_from_db()
        self.assertEqual((self.smtp_config.name, self.smtp_config.host), ("Updated SMTP", "mail.example.com"))
        self.assertEqual(self.smtp_config.password, "existing-secret")


class RejectedGraphSelectionTests(GraphSettingsTestCase):
    def assert_rejected(self, response, before):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["email_form"].errors["provider"], [PROVIDER_ERROR])
        self.assertContains(response, PROVIDER_ERROR)
        self.assertTrue(response.context["graph_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertEqual(self.state(), before)
        self.assert_no_key_material(response.content)

    def test_an_inactive_graph_config_cannot_be_selected(self):
        self.make_graph(is_active=False)
        before = self.state()

        self.assert_rejected(self.client.post(self.edit_url, self.post_data("graph")), before)

    def test_a_graph_config_without_a_certificate_cannot_be_selected(self):
        self.make_graph(certificate=False)
        before = self.state()

        self.assert_rejected(self.client.post(self.edit_url, self.post_data("graph")), before)

    def test_a_from_address_outside_the_scope_cannot_be_selected(self):
        self.make_graph()
        before = self.state()

        data = self.post_data("graph") | {"email-from_email": "outside@example.com"}

        self.assert_rejected(self.client.post(self.edit_url, data), before)


class AccessControlTests(GraphSettingsTestCase):
    def test_staff_without_mail_access_cannot_read_or_change_the_graph_settings(self):
        self.make_graph()
        self.client.force_login(make_admin(apps=["event"], email="outsider@example.com"))
        before = self.state()

        self.assertEqual(self.client.get(self.edit_url).status_code, 403)
        self.assertEqual(self.client.post(self.edit_url, self.post_data("graph")).status_code, 403)
        self.assertEqual(self.client.get(self.summary_url).status_code, 403)
        self.assertEqual(self.state(), before)

    def test_mail_only_staff_can_select_a_ready_graph_config_but_not_change_it(self):
        graph = self.make_graph()
        before = snapshot(graph)
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))

        response = self.client.post(self.edit_url, self.post_data("graph", **GRAPH_INPUTS))

        self.assertRedirects(response, self.summary_url, fetch_redirect_response=False)
        self.assertEqual(snapshot(graph), before)
        self.config.refresh_from_db()
        self.assertEqual(self.config.provider, "graph")
        self.assertEqual(self.client.get(reverse(GRAPH_CONFIG_URL_NAME, args=[graph.pk])).status_code, 403)


class SummaryGraphPanelTests(GraphSettingsTestCase):
    def test_the_summary_shows_the_graph_panel_while_graph_is_selected(self):
        graph = self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.summary_url)

        self.assertContains(response, 'id="graph-provider-summary"')
        self.assertContains(response, graph.current_certificate.sha1_thumbprint)
        self.assertContains(response, "mailer@example.com &mdash; Send and read")
        self.assert_no_key_material(response.content)

    def test_the_summary_leaves_the_graph_panel_out_for_other_providers(self):
        self.make_graph()

        self.assertNotContains(self.client.get(self.summary_url), 'id="graph-provider-summary"')
