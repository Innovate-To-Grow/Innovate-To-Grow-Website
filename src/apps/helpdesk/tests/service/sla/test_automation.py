"""The worker's hourly helpdesk automation: resolved tickets close by themselves after ``auto_close_resolved_days``
(0: never; a ticket reopened meanwhile is left alone; the timeline says why it closed), and running SLA clocks past
their due time are flagged."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.management.operations import worker_maintenance

from ....models import HelpdeskSettings, Ticket, TicketEvent
from ....services.sla import automation
from ....services.tickets import events
from ...helpers.service import Status, new_ticket

DAY = timedelta(days=1)


def resolved(days_ago, **values) -> Ticket:
    at = timezone.now() - days_ago * DAY
    return new_ticket(status=Status.RESOLVED, resolved_at=at, closed_at=at, resolution_code="solved", **values)


class AutoCloseTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_resolved_tickets_close_after_the_set_days_by_the_system(self):
        old = resolved(8)
        recent = resolved(6)
        open_ticket = new_ticket(status=Status.OPEN)

        self.assertEqual(automation.auto_close_resolved(), 1)

        old.refresh_from_db()
        recent.refresh_from_db()
        open_ticket.refresh_from_db()
        self.assertEqual((old.status, recent.status, open_ticket.status), (Status.CLOSED, Status.RESOLVED, Status.OPEN))
        self.assertEqual(old.resolved_at.date(), (timezone.now() - 8 * DAY).date())  # kept from when it was resolved
        self.assertEqual(old.resolution_code, "solved")  # closing is no reopening: the resolution stays
        event = old.events.get(kind=TicketEvent.Kind.STATUS)
        reason = "closed automatically 7 days after it was resolved"
        self.assertEqual((event.actor, event.data), (None, {"from": "resolved", "to": "closed", "reason": reason}))
        self.assertEqual(events.describe(event), f"Status changed: Resolved → Closed ({reason})")

    def test_the_period_comes_from_the_settings(self):
        HelpdeskSettings.objects.create(auto_close_resolved_days=2)
        ticket = resolved(3)

        self.assertEqual(automation.auto_close_resolved(), 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.CLOSED)
        reason = ticket.events.get(kind=TicketEvent.Kind.STATUS).data["reason"]
        self.assertEqual(reason, "closed automatically 2 days after it was resolved")

    def test_one_day_reads_in_the_singular(self):
        HelpdeskSettings.objects.create(auto_close_resolved_days=1)
        ticket = resolved(2)

        self.assertEqual(automation.auto_close_resolved(), 1)
        reason = ticket.events.get(kind=TicketEvent.Kind.STATUS).data["reason"]
        self.assertEqual(reason, "closed automatically 1 day after it was resolved")

    def test_zero_days_never_closes(self):
        HelpdeskSettings.objects.create(auto_close_resolved_days=0)
        ticket = resolved(400)

        self.assertEqual(automation.auto_close_resolved(), 0)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.RESOLVED)

    def test_a_ticket_reopened_meanwhile_is_left_alone(self):
        ticket = resolved(10)

        def reopen():
            # The requester's reply lands between the list and the close.
            Ticket.objects.filter(pk=ticket.pk).update(status=Status.OPEN, resolved_at=None, closed_at=None)
            return False

        self.assertEqual(automation.auto_close_resolved(should_stop=reopen), 0)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, Status.OPEN)
        self.assertFalse(ticket.events.exists())

    def test_a_stop_request_ends_it_before_the_next_ticket(self):
        resolved(10)
        resolved(9)

        self.assertEqual(automation.auto_close_resolved(should_stop=lambda: True), 0)
        self.assertEqual(Ticket.objects.filter(status=Status.RESOLVED).count(), 2)

    def test_judged_at_the_given_time(self):
        resolved(1)

        self.assertEqual(automation.auto_close_resolved(now=timezone.now() + 7 * DAY), 1)


class RunTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_run_closes_and_flags_and_reports_both(self):
        resolved(8)
        now = timezone.now()
        new_ticket(sla_started_at=now - 2 * DAY, response_due_at=now - DAY, resolution_due_at=now + DAY)

        self.assertEqual(automation.run(), {"auto_closed": 1, "sla_breaches": 1})
        self.assertEqual(automation.run(), {"auto_closed": 0, "sla_breaches": 0})

    def test_the_worker_runs_it_hourly_before_the_retention(self):
        names = [name for name, _task in worker_maintenance.MAINTENANCE_TASKS]

        self.assertIn("Helpdesk SLA and auto-close", names)
        self.assertLess(names.index("Helpdesk SLA and auto-close"), names.index("Helpdesk retention"))
        task = dict(worker_maintenance.MAINTENANCE_TASKS)["Helpdesk SLA and auto-close"]
        stop = object()
        with patch.object(
            worker_maintenance, "run_helpdesk_automation", return_value={"auto_closed": 1, "sla_breaches": 0}
        ) as run:
            with self.assertLogs(worker_maintenance.logger, "INFO"):
                task(should_stop=stop)
        run.assert_called_once_with(should_stop=stop)

    def test_the_worker_logs_nothing_when_nothing_happened(self):
        task = dict(worker_maintenance.MAINTENANCE_TASKS)["Helpdesk SLA and auto-close"]
        with (
            patch.object(
                worker_maintenance, "run_helpdesk_automation", return_value={"auto_closed": 0, "sla_breaches": 0}
            ),
            patch.object(worker_maintenance.logger, "info") as info,
        ):
            task()
        info.assert_not_called()
