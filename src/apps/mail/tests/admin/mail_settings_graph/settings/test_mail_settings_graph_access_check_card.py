"""The Graph access check card on Mail → Notification Delivery, where the certificate panel has no actions: it points
to the button on the Graph configuration's page."""

from django.urls import reverse

from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.mail_settings_graph.settings.test_mail_settings_admin_graph import (
    GRAPH_CONFIG_URL_NAME,
    GraphSettingsTestCase,
)


class NotificationDeliveryAccessCheckCardTests(GraphSettingsTestCase):
    def setUp(self):
        super().setUp()
        self.graph = self.make_graph()
        self.use_provider("graph")
        self.run_url = reverse("admin:core_microsoftgraphproviderconfig_run_access_check", args=[self.graph.pk])

    def test_admins_are_linked_to_the_button_on_the_graph_configuration_page(self):
        config_url = reverse(GRAPH_CONFIG_URL_NAME, args=[self.graph.pk])
        self.client.force_login(make_admin(email="any-admin@example.com"))

        response = self.client.get(self.edit_url)

        self.assertContains(response, f'href="{config_url}#graph-access-check" id="graph-run-access-check"')
        self.assertNotContains(response, self.run_url)
        self.assertNotContains(response, "needs the Core app")
