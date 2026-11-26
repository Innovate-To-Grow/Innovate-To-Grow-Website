import re
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.test import Client

from apps.core.models import (
    BackgroundJob,
    MicrosoftGraphProviderConfig,
)
from apps.event.tests.helpers import make_member
from apps.helpdesk.tests.admin.test_intake_admin import IntakeAdminTestCase, posted, to_minute

from ...models import HelpdeskSettings
from ...services.ingest.pipeline import jobs as ingest_jobs
from ...services.intake import jobs as intake_jobs
from ...services.intake import state as intake_state
from .. import corpus
from ..corpus import SITE
from ..helpers import FakeReader, make_admin, queue


class AccessTests(IntakeAdminTestCase):
    def actions(self):
        return (
            {"action": "scan"},
            {"action": "pause"},
            {"action": "rescan", "since": posted(self.now - timedelta(days=1))},
            {"action": "lookback", "lookback_hours": "100"},
        )

    def test_members_who_are_not_admins_can_change_nothing(self):
        self.client.force_login(make_member(email="member@example.com"))

        for data in self.actions():
            with self.subTest(action=data["action"]):
                response = self.client.post(self.url, data)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        self.assertUnchanged()
        self.assertFalse(BackgroundJob.objects.exists())

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        self.client.logout()

        for data in self.actions():
            with self.subTest(action=data["action"]):
                response = self.client.post(self.url, data)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        self.assertUnchanged()

    def test_any_admin_may_use_the_controls(self):
        self.client.force_login(make_admin(email="other-admin@example.com"))

        self.post(action="pause")

        self.assertTrue(self.row().paused)

    def test_a_get_never_changes_anything(self):
        response = self.client.get(self.url, {"action": "pause"})

        self.assertEqual(response.status_code, 405)
        self.assertUnchanged()

    def test_a_post_without_the_csrf_token_is_refused_and_one_with_it_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        data = {"action": "rescan", "since": posted(self.now - timedelta(days=1))}

        self.assertEqual(client.post(self.url, data).status_code, 403)
        self.assertUnchanged()
        page = client.get(self.page).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        self.assertEqual(client.post(self.url, {**data, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(self.row().checkpoint_at, to_minute(self.now - timedelta(days=1)))

    def test_an_unknown_action_is_refused(self):
        response = self.post(action="delete")

        self.assertMessage(response, "Unknown intake action.")
        self.assertUnchanged()


class ScanNowTests(IntakeAdminTestCase):
    def test_scan_now_queues_one_intake_scan(self):
        response = self.post(action="scan")

        self.assertMessage(response, f"An intake scan of {SITE} was queued")
        job = BackgroundJob.objects.get()
        self.assertEqual((job.kind, job.payload), (intake_jobs.INTAKE_JOB_KIND, {"requested": "manual"}))

    def test_nothing_is_queued_while_paused_switched_off_or_unreadable(self):
        intake_state.set_paused(SITE, True)
        paused = self.post(action="scan")
        intake_state.set_paused(SITE, False)
        HelpdeskSettings.objects.update(enabled=False)
        off = self.post(action="scan")
        HelpdeskSettings.objects.update(enabled=True)
        self.send_only_scope()
        unreadable = self.post(action="scan")

        self.assertMessage(paused, "is paused: resume it to scan")
        self.assertMessage(off, "The helpdesk is switched off")
        self.assertMessage(unreadable, f"does not grant read permission on {SITE}")
        self.assertFalse(BackgroundJob.objects.exists())


class PauseTests(IntakeAdminTestCase):
    def test_pause_holds_the_intake_only_and_is_recorded(self):
        response = self.post(action="pause")

        self.assertTrue(self.row().paused)
        self.assertMessage(
            response, f"Intake of {SITE} paused", "Bounce processing (Email Monitoring) is not affected."
        )
        entry = LogEntry.objects.get()
        self.assertEqual(
            (entry.user_id, entry.object_id, entry.change_message),
            (self.staff.pk, str(self.row().pk), "Intake paused."),
        )
        self.assertBounceUntouched()
        self.assertMessage(self.post(action="pause"), f"The intake of {SITE} is already paused; nothing changed.")
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_resume_wakes_the_import_of_mail_that_waited(self):
        intake_state.set_paused(SITE, True)
        queue(corpus.message(), reader=FakeReader())

        response = self.post(action="resume")

        self.assertFalse(self.row().paused)
        self.assertMessage(response, f"Intake of {SITE} resumed: the next scan (within 2 min) continues")
        self.assertTrue(BackgroundJob.objects.filter(kind=ingest_jobs.INGEST_JOB_KIND).exists())
        self.assertMessage(self.post(action="resume"), f"The intake of {SITE} is already running")
        self.assertBounceUntouched()

    def test_like_the_lookback_it_works_while_the_mailbox_cannot_be_read(self):
        self.send_only_scope()

        self.post(action="pause")

        self.assertTrue(self.row().paused)

    def test_without_graph_there_is_no_mailbox_to_pause(self):
        MicrosoftGraphProviderConfig.objects.update(is_active=False)

        response = self.post(action="pause")

        self.assertMessage(response, "Microsoft Graph is not configured")
        self.assertUnchanged()
