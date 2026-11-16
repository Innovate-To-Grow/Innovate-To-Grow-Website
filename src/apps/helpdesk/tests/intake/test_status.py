from datetime import timedelta
from unittest.mock import patch

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import InboxReader
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.helpdesk.tests.intake.test_intake_scan import STATUS_READER, IntakeTestCase, Status

from ...models import HelpdeskSettings, IntakeState
from ...services.intake import jobs, status
from ...services.intake import state as intake_state
from ..corpus import SITE


class StatusTests(IntakeTestCase):
    def describe(self, reader=True):
        with patch(STATUS_READER, return_value=(self.reader if reader else None, SITE, "")):
            return status.describe()

    def card(self, reader=True, problem=""):
        with patch(STATUS_READER, return_value=(self.reader if reader else None, SITE, problem)):
            return status.card(now=self.now)

    def test_the_email_monitoring_card_sees_the_intake_as_it_is(self):
        url = "/admin/helpdesk/helpdesksettings/#helpdesk-intake"
        self.assertEqual(self.describe(), InboxReader("Helpdesk intake", "running", 120, url))
        intake_state.set_paused(SITE, True)
        self.assertEqual(self.describe().state, "paused")
        self.assertEqual(self.describe(reader=False).state, "inactive")
        HelpdeskSettings.objects.create(enabled=False)
        self.assertEqual(self.describe().state, "off")

    def test_the_card_level_follows_the_state(self):
        self.assertEqual(self.card()["level"], "waiting")
        intake_state.set_paused(SITE, True)
        self.assertEqual(self.card()["level"], "paused")  # paused before its first scan reads as paused
        intake_state.set_paused(SITE, False)
        IntakeState.objects.filter(mailbox=SITE).update(
            last_run_finished_at=self.ago(minutes=1), last_success_at=self.ago(minutes=1)
        )
        self.assertEqual(self.card()["level"], "ok")
        IntakeState.objects.filter(mailbox=SITE).update(last_success_at=self.ago(minutes=7))
        self.assertEqual(self.card()["level"], "warning")
        IntakeState.objects.filter(mailbox=SITE).update(consecutive_failures=2)
        self.assertEqual(self.card()["level"], "error")
        self.assertEqual(self.card(reader=False, problem="No read scope.")["level"], "inactive")
        HelpdeskSettings.objects.create(enabled=False)
        self.assertEqual(self.card()["level"], "off")

    def test_the_card_counts_waiting_mail_and_shows_the_next_scan_and_cadence(self):
        self.scan()
        InboundMessage.objects.filter(graph_id="ndr-1").update(status=Status.DONE)
        jobs.ensure_scheduled(now=self.now + timedelta(minutes=2))

        card = self.card()

        self.assertEqual((card["waiting"], card["every"], card["catch_up"]), (2, "2 min", "30 s"))
        self.assertEqual(card["next_scan_at"], self.now + timedelta(minutes=2))
        self.assertFalse(card["scan_running"])
        self.assertEqual(card["url"], "/admin/helpdesk/helpdesksettings/intake/")
        with monitoring_settings(inbox_scan_interval_seconds=30):
            self.assertEqual(status.cadence(), {"every": "1 min", "catch_up": "30 s"})
        with patch(STATUS_READER, return_value=(None, "", "Microsoft Graph is not configured.")):
            self.assertEqual((status.card()["waiting"], status.card()["state"]), (0, None))
