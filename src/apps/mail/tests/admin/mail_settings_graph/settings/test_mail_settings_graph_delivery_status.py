"""The read-only Graph panel on Mail → Notification Delivery: "Message trace delivery status: On/Off · last sync" and
the latest permission check's summary, which link to where they are run."""

import re

from django.utils import timezone

from apps.core.models import EmailDeliveryTraceState, MicrosoftGraphPermissionCheck
from apps.mail.tests.admin.mail_settings_graph.settings.test_mail_settings_admin_graph import GraphSettingsTestCase

BLOCK = re.compile(r"<div[^>]*data-graph-delivery-status>(.*?)</div>", re.S)


class GraphDeliveryStatusPanelTests(GraphSettingsTestCase):
    def setUp(self):
        super().setUp()
        self.use_provider("graph")

    def block(self, url=None) -> str:
        found = BLOCK.search(self.client.get(url or self.edit_url).content.decode())
        self.assertIsNotNone(found)
        return " ".join(found.group(1).split())

    def test_off_and_no_permission_check_yet(self):
        self.make_graph()

        block = self.block()

        self.assertIn('<p class="mt-1">Off</p>', block)
        self.assertIn("Permission check: not run yet.", block)

    def test_on_with_the_last_sync_and_the_latest_check(self):
        graph = self.make_graph(message_trace_enabled=True)
        finished = timezone.now()
        EmailDeliveryTraceState.objects.create(
            sender="admin@example.com", last_run_finished_at=finished, last_success_at=finished
        )
        MicrosoftGraphPermissionCheck.objects.create(
            config=graph,
            token_ok=True,
            granted_roles=["Mail.Send", "Mail.ReadWrite"],
            trace_result=MicrosoftGraphPermissionCheck.TraceResult.NOT_GRANTED,
        )

        for url in (self.edit_url, self.summary_url):
            with self.subTest(url=url):
                block = self.block(url)
                self.assertIn("On &middot; last sync", block)
                self.assertNotIn("last successful", block)
                self.assertIn("Message Trace not granted", block)
                self.assertIn("the token carries Mail.Send, Mail.ReadWrite", block)

    def test_no_saved_graph_config_shows_no_summary(self):
        self.assertIsNone(BLOCK.search(self.client.get(self.edit_url).content.decode()))
