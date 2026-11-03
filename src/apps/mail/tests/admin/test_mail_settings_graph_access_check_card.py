"""The Graph access check card on Mail → Notification Delivery, where the certificate panel has no actions: it points
superusers to the button on the Graph configuration's page and tells everyone else that a superuser has to run it."""

from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_panel import SUPERUSER_NEEDED
from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.test_mail_settings_admin_graph import GRAPH_CONFIG_URL_NAME, GraphSettingsTestCase


class NotificationDeliveryAccessCheckCardTests(GraphSettingsTestCase):
    def setUp(self):
        super().setUp()
        self.graph = self.make_graph()
        self.use_provider("graph")
        self.run_url = reverse("admin:core_microsoftgraphproviderconfig_run_access_check", args=[self.graph.pk])

    def test_superusers_are_linked_to_the_button_on_the_graph_configuration_page(self):
        response = self.client.get(self.edit_url)

        config_url = reverse(GRAPH_CONFIG_URL_NAME, args=[self.graph.pk])
        self.assertContains(response, f'href="{config_url}#graph-access-check" id="graph-run-access-check"')
        self.assertContains(response, 'id="graph-access-check"')
        self.assertNotContains(response, self.run_url)
        self.assertNotContains(response, SUPERUSER_NEEDED)

    def test_staff_who_are_not_superusers_are_told_a_superuser_has_to_run_it(self):
        for apps in (["mail"], ["mail", "core"]):
            with self.subTest(apps=apps):
                self.client.force_login(make_admin(apps=apps, email=f"staff-{'-'.join(apps)}@example.com"))

                response = self.client.get(self.edit_url)

                self.assertContains(response, SUPERUSER_NEEDED)
                self.assertNotContains(response, 'id="graph-run-access-check"')
                self.assertNotContains(response, self.run_url)
