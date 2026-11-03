"""The Graph access check card on Mail → Notification Delivery, where the certificate panel has no actions: it points
whoever has the Core app to the button on the Graph configuration's page and tells Mail-only staff that the Core app
is needed."""

from django.urls import reverse

from apps.core.admin.service_credentials.microsoft_graph_panel import CORE_APP_NEEDED
from apps.event.tests.helpers import make_admin
from apps.mail.tests.admin.test_mail_settings_admin_graph import GRAPH_CONFIG_URL_NAME, GraphSettingsTestCase


class NotificationDeliveryAccessCheckCardTests(GraphSettingsTestCase):
    def setUp(self):
        super().setUp()
        self.graph = self.make_graph()
        self.use_provider("graph")
        self.run_url = reverse("admin:core_microsoftgraphproviderconfig_run_access_check", args=[self.graph.pk])

    def test_superusers_and_core_staff_are_linked_to_the_button_on_the_graph_configuration_page(self):
        config_url = reverse(GRAPH_CONFIG_URL_NAME, args=[self.graph.pk])
        for user in (self.admin_user, make_admin(apps=["mail", "core"], email="core-mail@example.com")):
            with self.subTest(superuser=user.is_superuser):
                self.client.force_login(user)

                response = self.client.get(self.edit_url)

                self.assertContains(response, f'href="{config_url}#graph-access-check" id="graph-run-access-check"')
                self.assertNotContains(response, self.run_url)
                self.assertNotContains(response, CORE_APP_NEEDED)

    def test_mail_only_staff_are_told_the_core_app_is_needed(self):
        self.client.force_login(make_admin(apps=["mail"], email="mail-only@example.com"))

        response = self.client.get(self.edit_url)

        self.assertContains(response, CORE_APP_NEEDED)
        self.assertNotContains(response, 'id="graph-run-access-check"')
        self.assertNotContains(response, "/admin/core/microsoftgraphproviderconfig/")
