"""Helpdesk → Queue filters and columns after the live check of the admin flows.

- Status: the two groups have keys of their own ("active", the default, and "done"), so ?status=open is In progress
  only and ?status=closed is Closed only.
- SLA: "at risk" is a clock still running past the settings' warning share of its target and not overdue yet.
- Columns: who replied to the requester last and when (tickets have no owner, I2G-HELPDESK-01: no group or assignee
  filter or column), and not the creation time the shared timestamp mixin adds.
"""

from datetime import timedelta

from django.utils import timezone

from ....models import HelpdeskSettings, TicketMessage
from ...helpers import make_admin
from ...helpers.service import Status, clocked_ticket, new_ticket
from .support import QueueCase

HOUR = timedelta(hours=1)
OPEN_STATUSES = {"new", "open", "pending_customer", "pending_internal"}


class StatusFilterTests(QueueCase):
    def setUp(self):
        super().setUp()
        for status in (*OPEN_STATUSES, Status.RESOLVED, Status.CLOSED):
            new_ticket(subject=str(status), status=status)

    def test_the_two_groups_and_the_single_statuses(self):
        self.assertEqual(set(self.listed()), OPEN_STATUSES)  # the default
        self.assertEqual(set(self.listed("status=active")), OPEN_STATUSES)
        self.assertEqual(set(self.listed("status=done")), {"resolved", "closed"})
        self.assertEqual(self.listed("status=open"), ["open"])  # In progress, not every open status
        self.assertEqual(self.listed("status=closed"), ["closed"])
        self.assertEqual(self.listed("status=pending_customer"), ["pending_customer"])
        self.assertEqual(len(self.listed("status=any")), 6)

    def test_the_choices_and_which_one_is_selected(self):
        def selected(query=""):
            return [text for text, chosen in self.choices("status", query).items() if chosen]

        self.assertEqual(
            list(self.choices("status"))[:4],
            ["Open (new, in progress, on hold)", "Resolved & closed", "New", "In progress"],
        )
        self.assertEqual(selected(), ["Open (new, in progress, on hold)"])
        self.assertEqual(selected("status=open"), ["In progress"])
        self.assertEqual(selected("status=done"), ["Resolved & closed"])
        self.assertEqual(selected("mail=all"), ["Any status"])  # automated mail shown: every status by default


class AtRiskFilterTests(QueueCase):
    """Normal priority, as seeded: the first response within 1 day, the resolution within 5 days."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        responded = {"first_responded_at": now - 90 * HOUR, "status": Status.OPEN}
        clocked_ticket(subject="response at risk", started=now - 20 * HOUR)  # 20 h of 24
        clocked_ticket(subject="past half", started=now - 14 * HOUR)  # 14 h of 24
        clocked_ticket(subject="on track", started=now - 2 * HOUR)
        clocked_ticket(subject="overdue", started=now - 30 * HOUR)
        clocked_ticket(subject="resolution at risk", started=now - 100 * HOUR, **responded)  # 100 h of 120
        paused = {**responded, "status": Status.PENDING_CUSTOMER, "sla_paused_at": now - HOUR}
        clocked_ticket(subject="paused", started=now - 100 * HOUR, **paused)  # stands still: not at risk
        new_ticket(subject="no clock")

    def column_states(self, query) -> set[str]:
        changelist = self.get(query).context["cl"]
        return {changelist.model_admin.sla_column(ticket)[0] for ticket in changelist.result_list}

    def test_at_risk_is_a_running_clock_past_the_share_and_not_overdue(self):
        self.assertEqual(set(self.listed("sla=at_risk")), {"response at risk", "resolution at risk"})
        self.assertEqual(self.listed("sla=breached"), ["overdue"])
        self.assertEqual(self.column_states("sla=at_risk"), {"at_risk"})  # the column agrees with the filter

    def test_the_share_comes_from_the_settings(self):
        HelpdeskSettings.objects.create(sla_warning_percent=50)

        self.assertEqual(set(self.listed("sla=at_risk")), {"response at risk", "past half", "resolution at risk"})
        self.assertEqual(self.column_states("sla=at_risk"), {"at_risk"})
        self.assertTrue(self.choices("SLA", "sla=at_risk")["At risk (past 50% of the target)"])

    def test_the_choices_name_the_share(self):
        self.assertEqual(list(self.choices("SLA")), ["All", "Breached", "At risk (past 75% of the target)", "No SLA"])


class ColumnTests(QueueCase):
    def test_the_list_shows_who_replied_last_and_not_when_it_was_created(self):
        kim = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        replied, failed, nobody = (
            new_ticket(subject="replied"),
            new_ticket(subject="failed"),
            new_ticket(subject="none"),
        )
        at = timezone.now() - HOUR
        for ticket, name, delivery in ((replied, "Kim Lee", "sent"), (failed, "Avery Agent", "failed")):
            TicketMessage.objects.create(
                ticket=ticket, kind="reply", author=kim, from_name=name, occurred_at=at, delivery_status=delivery
            )

        response = self.get()
        changelist = response.context["cl"]
        model_admin = changelist.model_admin
        rows = {row.subject: row for row in changelist.result_list}

        self.assertIn("last_reply_column", changelist.list_display)
        self.assertFalse({"group_column", "assignee_column", "created_at"} & set(changelist.list_display))
        self.assertEqual(model_admin.last_reply_column.short_description, "Last reply")
        self.assertContains(response, "Kim Lee")
        when = timezone.localtime(at).strftime("%b %d, %H:%M")
        self.assertIn(
            f'Kim Lee<br><span class="i2g-helpdesk-muted">{when}</span>', model_admin.last_reply_column(rows["replied"])
        )
        self.assertEqual(model_admin.last_reply_column(rows["failed"]), "—")  # it never reached the requester
        self.assertEqual(model_admin.last_reply_column(rows["none"]), "—")
