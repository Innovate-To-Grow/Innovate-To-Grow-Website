"""The intake pages: the intake card's next scan and last-scan line say only what holds (no next scan while switched
off, not active or paused), and Ingest Problems' "Dismiss (handled)" takes a problem that can never be imported out of
the Problems view, audited, without a column of its own (Retry undoes it). Retry is audited too and says why it left
rows as they were; the Classification filter names classifications as the list's column does, with no blank choice."""

from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import dateformat, timezone

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import LABELS
from apps.helpdesk.tests.admin.test_intake_admin import IntakeAdminTestCase

from ....models import HelpdeskSettings, IntakeState
from ....services.intake import jobs as intake_jobs
from ....services.intake import state as intake_state
from ...corpus import SITE
from ...helpers import helpdesk_staff, queue

Status = InboundMessage.Status
NEXT_SCAN = "<dt>Next scan</dt><dd>{}</dd>"
REST = "(the rest were recorded before)"
DISMISSED = "dismissed"  # the filter's value, and the ``result`` key a dismissal is kept under


class IntakeCardTests(IntakeAdminTestCase):
    def card(self):
        return self.client.get(self.page)

    def test_no_next_scan_is_shown_while_switched_off_not_active_or_paused(self):
        intake_jobs.ensure_scheduled(now=self.now + timedelta(minutes=2))
        queued = dateformat.format(timezone.localtime(self.now + timedelta(minutes=2)), "M j, H:i")
        self.assertContains(self.card(), NEXT_SCAN.format(queued), html=False)

        intake_state.set_paused(SITE, True)
        self.assertContains(self.card(), NEXT_SCAN.format("– (paused)"), html=False)
        intake_state.set_paused(SITE, False)
        HelpdeskSettings.objects.update(enabled=False)
        self.assertContains(self.card(), NEXT_SCAN.format("– (switched off)"), html=False)
        HelpdeskSettings.objects.update(enabled=True)
        self.send_only_scope()
        self.assertContains(self.card(), NEXT_SCAN.format("– (not active)"), html=False)

    def test_the_last_scan_line_names_earlier_recordings_only_when_there_were_some(self):
        cases = (
            ({"listed": 0, "recorded": 0}, "Last scan: 0 messages listed, 0 new recorded for import.", False),
            ({"listed": 3, "recorded": 3}, "Last scan: 3 messages listed, 3 new recorded for import.", False),
            ({"listed": 7, "recorded": 3}, f"Last scan: 7 messages listed, 3 new recorded for import {REST}.", True),
        )
        for stats, line, rest in cases:
            with self.subTest(stats):
                IntakeState.objects.filter(mailbox=SITE).update(last_run_finished_at=self.now, last_run_stats=stats)
                response = self.card()
                self.assertContains(response, line)
                self.assertEqual(REST in response.content.decode(), rest)


class DismissTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = helpdesk_staff()
        self.client.force_login(self.staff)
        self.gone = queue(status=Status.SKIPPED, last_error="No longer in the mailbox.")
        self.failed = queue(status=Status.FAILED, last_error="Microsoft Graph could not be reached.")
        self.done = queue(status=Status.DONE)
        self.url = reverse("admin:helpdesk_ingestrecord_changelist")

    def act(self, action, *rows):
        data = {"action": action, "index": "0", "_selected_action": [str(row.pk) for row in rows]}
        return self.client.post(f"{self.url}?state=all", data, follow=True)

    def listed(self, state=None) -> set:
        response = self.client.get(self.url, {"state": state} if state else {})
        return {row.pk for row in response.context["cl"].result_list}

    def test_a_dismissed_problem_leaves_the_problems_view_and_is_audited(self):
        response = self.act("dismiss", self.gone)

        self.assertContains(
            response, "1 message dismissed as handled; the Dismissed and Everything filters still list it."
        )
        self.assertEqual(self.listed(), {self.failed.pk})
        self.assertEqual(self.listed(DISMISSED), {self.gone.pk})
        self.assertEqual(self.listed("all"), {self.gone.pk, self.failed.pk, self.done.pk})
        self.gone.refresh_from_db()
        # It keeps its status and error; the dismissal says who and when.
        self.assertEqual((self.gone.status, self.gone.last_error), (Status.SKIPPED, "No longer in the mailbox."))
        self.assertEqual(self.gone.result[DISMISSED]["by"], "Avery Agent")
        entry = LogEntry.objects.get(object_id=str(self.gone.pk))
        self.assertEqual((entry.user, entry.change_message), (self.staff, "Dismissed as handled (bulk action)."))
        self.assertContains(self.client.get(self.url, {"state": "all"}), "Skipped, dismissed")

    def test_only_problems_not_dismissed_yet_are_dismissed(self):
        self.act("dismiss", self.gone)

        response = self.act("dismiss", self.gone, self.done, self.failed)

        self.assertContains(
            response,
            "1 message dismissed as handled; the Dismissed and Everything filters still list it. 2 left as they "
            "were: only failed or skipped messages not dismissed yet are dismissed.",
        )
        self.done.refresh_from_db()
        self.assertNotIn(DISMISSED, self.done.result)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_retry_clears_the_dismissal_so_a_new_failure_is_listed_again(self):
        self.act("dismiss", self.failed)

        self.act("retry", self.failed)

        self.failed.refresh_from_db()
        self.assertEqual(self.failed.status, Status.PENDING)
        self.assertNotIn(DISMISSED, self.failed.result)
        InboundMessage.objects.filter(pk=self.failed.pk).update(status=Status.FAILED)  # it fails again
        self.assertEqual(self.listed(), {self.gone.pk, self.failed.pk})

    def test_retry_is_audited_and_says_why_it_left_a_message_as_it_was(self):
        self.act("dismiss", self.gone)

        response = self.act("retry", self.gone, self.failed, self.done)

        self.assertContains(
            response,
            "2 messages queued again for import. 1 left as it was: only failed or skipped messages are retried.",
        )
        retried = LogEntry.objects.filter(change_message__startswith="Retried")
        self.assertEqual(
            dict(retried.values_list("object_id", "change_message")),
            {
                str(self.gone.pk): "Retried: queued again for import. Its dismissal was cleared.",
                str(self.failed.pk): "Retried: queued again for import.",
            },
        )
        self.assertEqual({entry.user for entry in retried}, {self.staff})

    def test_the_classification_filter_names_them_as_the_column_does_with_no_blank_choice(self):
        InboundMessage.objects.filter(pk=self.done.pk).update(classification="auto_reply")

        response = self.client.get(self.url, {"state": "all"})

        changelist = response.context["cl"]
        found = next(spec for spec in changelist.filter_specs if spec.title == "classification")
        self.assertEqual([choice["display"] for choice in found.choices(changelist)], ["All", *LABELS.values()])
        filtered = self.client.get(self.url, {"state": "all", found.parameter_name: "auto_reply"})
        self.assertEqual([row.pk for row in filtered.context["cl"].result_list], [self.done.pk])
