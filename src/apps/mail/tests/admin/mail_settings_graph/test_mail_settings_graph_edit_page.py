from django.urls import reverse

from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.mail_settings_graph.test_mail_settings_admin_graph import (
    CLIENT_ID,
    GRAPH_CONFIG_URL_NAME,
    TENANT_ID,
    GraphSettingsTestCase,
)


class EditPageRenderingTests(GraphSettingsTestCase):
    def test_graph_provider_opens_the_read_only_graph_panel_and_hides_the_smtp_panel(self):
        graph = self.make_graph()
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["graph_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertContains(response, "Microsoft Graph Provider")
        self.assertNotContains(response, 'name="graph-')
        certificate = graph.current_certificate
        for value in (TENANT_ID, CLIENT_ID, "mailer@example.com", certificate.sha1_thumbprint, "Expires in "):
            self.assertContains(response, value)
        self.assertContains(response, "Thumbprint (SHA-1, as shown in Entra)")
        self.assertContains(response, '<option value="graph" selected>Microsoft Graph</option>', html=True)
        self.assertTrue(all(field.disabled for field in response.context["smtp_form"].fields.values()))
        self.assert_no_key_material(response.content)

    def test_ses_provider_hides_both_provider_panels(self):
        self.make_graph()

        response = self.client.get(self.edit_url)

        self.assertFalse(response.context["graph_enabled"])
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertContains(response, '<option value="ses" selected>AWS SES</option>', html=True)
        self.assertContains(response, '<option value="graph">Microsoft Graph</option>', html=True)

    def test_smtp_provider_opens_the_smtp_panel_and_hides_the_graph_panel(self):
        self.make_graph()
        self.use_provider("smtp")

        response = self.client.get(self.edit_url)

        self.assertTrue(response.context["smtp_enabled"])
        self.assertNotIn("hidden", self.panel_attrs(response, "smtp-provider-settings"))
        self.assertIn("hidden", self.panel_attrs(response, "graph-provider-settings"))
        self.assertNotContains(response, "existing-secret")

    def test_superusers_and_core_staff_get_a_link_to_the_graph_config_but_no_certificate_actions(self):
        graph = self.make_graph()
        config_url = reverse(GRAPH_CONFIG_URL_NAME, args=[graph.pk])
        for user in (self.admin_user, make_admin(apps=["mail", "core"], email="core-mail@example.com")):
            with self.subTest(superuser=user.is_superuser):
                self.client.force_login(user)

                response = self.client.get(self.edit_url)

                self.assertContains(response, config_url)
                self.assertNotContains(response, f"{config_url.removesuffix('change/')}certificate/install/")

    def test_mail_only_staff_see_the_graph_config_without_any_link_to_change_it(self):
        graph = self.make_graph()
        self.use_provider("graph")
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, graph.current_certificate.sha1_thumbprint)
        self.assertNotContains(response, "/admin/core/microsoftgraphproviderconfig/")
        self.assertContains(
            response,
            "Changing the Microsoft Graph configuration, its certificate or running its access check needs the Core app",
        )

    def test_without_a_graph_config_the_panel_says_so_and_links_to_the_add_page(self):
        self.use_provider("graph")

        response = self.client.get(self.edit_url)

        self.assertContains(response, "No Microsoft Graph configuration is active.")
        self.assertContains(response, reverse("admin:core_microsoftgraphproviderconfig_add"))
        self.assertNotContains(response, 'id="graph-certificate-panel"')
