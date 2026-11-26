"""Assignment notifications: to the new assignee (never the member who made the change), or to the group's members
when a group is assigned with nobody in it; only to active Admins; never in shadow mode or with
``notify_assignment`` off. Queued as ``helpdesk.notify_staff`` when the change commits; the timeline records a notice
only once the job sent it (``test_job_state_and_notices``)."""

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_member

from ....models import AssignmentGroup, HelpdeskSettings, TicketEvent
from ....services import tickets
from ....services.outbound import jobs
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import new_ticket, sending_settings

Kind = TicketEvent.Kind


class AssignmentNotificationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.settings = sending_settings()
        self.lead = helpdesk_staff("lead@example.com")
        self.agent = make_admin(email="agent2@example.com", first_name="Kim", last_name="Lee")
        self.ticket = new_ticket()

    def update(self, **changes):
        with self.captureOnCommitCallbacks(execute=True):
            return tickets.update_ticket(self.ticket, actor=self.lead, **changes)

    def notices(self):
        return list(BackgroundJob.objects.filter(kind=jobs.NOTIFY_JOB_KIND).values_list("payload", flat=True))

    def test_the_new_assignee_is_notified(self):
        self.update(assignee=self.agent)

        self.assertEqual(
            self.notices(),
            [
                {
                    "ticket_id": str(self.ticket.pk),
                    "recipients": ["agent2@example.com"],
                    "reason": "assigned",
                    "actor": "Avery Agent",
                }
            ],
        )
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())  # queued, not sent yet

    def test_assigning_oneself_notifies_nobody(self):
        self.update(assignee=self.lead)

        self.assertEqual(self.notices(), [])
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())

    def test_unassigning_notifies_nobody(self):
        self.update(assignee=self.agent)
        self.update(assignee=None)

        self.assertEqual(len(self.notices()), 1)

    def test_an_assignee_who_is_not_an_admin_or_inactive_is_not_emailed(self):
        outsider = make_member(email="member@example.com")
        self.update(assignee=outsider)
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])
        self.update(assignee=self.agent)

        self.assertEqual(self.notices(), [])

    def test_a_group_with_nobody_assigned_notifies_its_members_but_the_actor(self):
        third = make_admin(email="third@example.com")
        outsider = make_member(email="member@example.com")
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.lead, self.agent, third, outsider)

        self.update(assignment_group=group)

        (payload,) = self.notices()
        self.assertEqual(payload["reason"], "group")
        self.assertEqual(sorted(payload["recipients"]), ["agent2@example.com", "third@example.com"])
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())

    def test_a_group_assigned_together_with_an_assignee_notifies_only_the_assignee(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.agent, make_admin(email="third@example.com"))

        self.update(assignment_group=group, assignee=self.agent)

        (payload,) = self.notices()
        self.assertEqual((payload["reason"], payload["recipients"]), ("assigned", ["agent2@example.com"]))

    def test_a_group_change_on_an_assigned_ticket_notifies_nobody(self):
        self.update(assignee=self.agent)
        group = AssignmentGroup.objects.create(name="Events")
        # The assignee is one of the group's members (a group they are not in is refused: membership rule).
        group.members.add(self.agent, make_admin(email="third@example.com"))

        self.update(assignment_group=group)

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.assignment_group, self.ticket.assignee), (group, self.agent))
        self.assertEqual(len(self.notices()), 1)  # only the assignment before it

    def test_an_empty_group_notifies_nobody(self):
        self.update(assignment_group=AssignmentGroup.objects.create(name="Nobody"))

        self.assertEqual(self.notices(), [])

    def test_nothing_in_shadow_mode(self):
        HelpdeskSettings.objects.update(shadow_mode=True)

        self.update(assignee=self.agent)

        self.assertEqual(self.notices(), [])
        self.assertFalse(self.ticket.events.filter(kind=Kind.NOTIFIED).exists())

    def test_nothing_with_notifications_off(self):
        HelpdeskSettings.objects.update(notify_assignment=False)

        self.update(assignee=self.agent)

        self.assertEqual(self.notices(), [])

    def test_a_change_by_the_system_names_the_helpdesk(self):
        with self.captureOnCommitCallbacks(execute=True):
            tickets.update_ticket(self.ticket, actor=None, assignee=self.agent)

        self.assertEqual(self.notices()[0]["actor"], "The helpdesk")
