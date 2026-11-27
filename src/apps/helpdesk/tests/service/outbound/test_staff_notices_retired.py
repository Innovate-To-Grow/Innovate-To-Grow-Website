"""Staff are no longer emailed (I2G-HELPDESK-01): ``helpdesk.notify_staff`` stays registered, on no delivery lane, so a
notice an earlier release queued finishes without sending anything or touching the ticket. Assigning is gone from
``update_ticket`` (an assignee or group passed in is ignored: no change, no event, no job). The assignee, group and
notice entries earlier releases wrote still read on the timeline, and the settings page no longer offers the notice
switch (saving it keeps the stored value)."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.module_loading import import_string

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs.registry import registered_job_kinds

from ....admin.tickets import timeline
from ....models import AssignmentGroup, HelpdeskSettings, TicketEvent
from ....services.outbound import jobs
from ....services.tickets import events, update_ticket
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import sending_settings
from ...tickets.test_tickets import new_ticket

Kind = TicketEvent.Kind
OLD_PAYLOAD = {"ticket_id": "", "recipients": ["sam@example.com"], "reason": "assigned", "actor": "Avery Agent"}


class NotifyJobTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings()

    def test_the_kind_stays_registered_on_no_lane(self):
        kind = registered_job_kinds()[jobs.NOTIFY_JOB_KIND]

        self.assertEqual(jobs.NOTIFY_JOB_KIND, "helpdesk.notify_staff")
        self.assertEqual(kind.handler, "apps.helpdesk.services.outbound.jobs.notify_staff_job")
        self.assertIs(import_string(kind.handler), jobs.notify_staff_job)
        self.assertEqual((kind.family, kind.lane), (None, None))

    def test_a_queued_notice_sends_nothing_and_leaves_the_ticket_alone(self):
        ticket = new_ticket()
        job = SimpleNamespace(pk="job-1", payload={**OLD_PAYLOAD, "ticket_id": str(ticket.pk)})
        before = TicketEvent.objects.count()

        with (
            patch("apps.core.services.email.deliver_email") as deliver,
            self.assertLogs("apps.helpdesk.services.outbound.jobs", "INFO") as logged,
        ):
            self.assertIsNone(jobs.notify_staff_job(job))

        deliver.assert_not_called()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(TicketEvent.objects.count(), before)
        self.assertIn("staff are no longer emailed", logged.output[0])


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class NoAssigningTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings()

    def test_an_assignee_or_group_passed_to_update_ticket_is_ignored(self):
        ticket = new_ticket()
        other = make_admin(email="sam@example.com")
        group = AssignmentGroup.objects.create(name="Events")

        with self.captureOnCommitCallbacks(execute=True):
            changed = update_ticket(ticket, actor=helpdesk_staff(), assignee=other, assignment_group=group)

        self.assertEqual(changed, [])
        ticket.refresh_from_db()
        self.assertEqual((ticket.assignee_id, ticket.assignment_group_id), (None, None))
        self.assertFalse(TicketEvent.objects.filter(ticket=ticket).exists())
        self.assertFalse(BackgroundJob.objects.filter(kind=jobs.NOTIFY_JOB_KIND).exists())


class LegacyEventTests(TestCase):
    def test_entries_of_earlier_releases_still_read(self):
        ticket = new_ticket()
        agent = helpdesk_staff()
        records = [
            (Kind.ASSIGNED, agent, {"from": "Kim Old", "to": "Sam Lead"}),
            (Kind.GROUP, agent, {"from": "", "to": "Events"}),
            (Kind.NOTIFIED, None, {"reason": "group", "count": 3}),
            (Kind.NOTIFIED, None, {"reason": "assigned", "count": 1}),
        ]
        for kind, actor, data in records:
            events.record(ticket, kind, actor=actor, **data)

        described = [events.describe(event) for event in TicketEvent.objects.filter(ticket=ticket)]
        expected = [
            "Assignee changed: Kim Old → Sam Lead",
            "Assignment group changed: — → Events",
            "Assignment notice emailed to the group's 3 members",
            "Assignment notice emailed to the assignee",
        ]
        self.assertEqual(described, expected)
        shown = [entry.text for entry in timeline.build(ticket) if entry.kind == "event"]
        self.assertEqual(shown, expected)
        self.assertIn("Avery Agent", [entry.actor for entry in timeline.build(ticket)])


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SettingsPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        self.row = HelpdeskSettings.objects.create(notify_assignment=False)
        self.url = reverse("admin:helpdesk_helpdesksettings_change", args=[self.row.pk])

    def test_the_notice_switch_is_gone_and_its_stored_value_stays(self):
        page = self.client.get(self.url)
        form = page.context["adminform"].form
        self.assertNotIn("notify_assignment", form.fields)
        self.assertNotContains(page, "notify_assignment")
        self.assertIn("Sending", [fieldset.name for fieldset in page.context["adminform"]])

        data = {name: form[name].value() for name in form.fields}
        data = {name: value for name, value in data.items() if value is not None and value is not False}
        data.update(sla_warning_percent="60", notify_assignment="on")
        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual((self.row.sla_warning_percent, self.row.notify_assignment), (60, False))
