"""Who counts as a member of an assignment group (``tickets.eligible_members``): active Admins. Someone who is no
longer an Admin, or whose account is switched off, stays listed in the group until removed by hand, but no longer
holds its tickets:

- a group whose only members are such people does not hold back an assignment (it is open to every Admin, as a group
  without members is), on the ticket page and in the services;
- a group with one eligible member still refuses an assignee from outside it;
- the ticket page's script narrows "Assigned to" to the eligible members only.
"""

from django.core.cache import cache
from django.test import TestCase

from apps.event.tests.helpers import make_member

from ....models import AssignmentGroup
from ....services import tickets
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import Status, new_ticket
from ..page.support import PageCase


def people():
    """Two colleagues, someone who is no longer an Admin (a regular member now), and an Admin whose account is off."""
    return {
        "kim": make_admin(email="kim@example.com", first_name="Kim", last_name="Lee"),
        "lee": make_admin(email="lee@example.com", first_name="Lee", last_name="Park"),
        "former": make_member(email="fran@example.com", first_name="Fran", last_name="Former"),
        "away": make_admin(email="ali@example.com", first_name="Ali", is_active=False),
    }


class EligibleMembersTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.people = people()
        self.group = AssignmentGroup.objects.create(name="Events")

    def test_only_active_admins_count(self):
        self.group.members.add(self.agent, *self.people.values())

        eligible = {member.pk for member in tickets.eligible_members(self.group)}

        self.assertEqual(eligible, {self.agent.pk, self.people["kim"].pk, self.people["lee"].pk})

    def test_a_group_left_with_nobody_eligible_takes_any_assignee(self):
        for left in ("former", "away"):
            with self.subTest(left):
                self.group.members.set([self.people[left]])
                ticket = new_ticket(status=Status.OPEN, assignment_group=self.group)

                self.assertEqual(tickets.membership_problem(self.group, self.agent), "")
                self.assertEqual(tickets.update_ticket(ticket, actor=self.agent, assignee=self.agent), ["assignee"])
                ticket.refresh_from_db()
                self.assertEqual(ticket.assignee, self.agent)

    def test_one_eligible_member_still_keeps_an_outsider_out(self):
        self.group.members.set([self.people["former"], self.people["kim"]])
        ticket = new_ticket(status=Status.OPEN, assignment_group=self.group)

        self.assertEqual(tickets.membership_problem(self.group, self.agent), "Avery Agent is not a member of Events.")
        self.assertEqual(tickets.membership_problem(self.group, self.people["kim"]), "")
        with self.assertRaises(tickets.AssignmentRefused):
            tickets.update_ticket(ticket, actor=self.agent, assignee=self.agent)
        self.assertEqual(tickets.assign([ticket], self.agent, actor=self.agent), (0, 1))  # "Assign to me" too
        ticket.refresh_from_db()
        self.assertIsNone(ticket.assignee)


class TicketPageEligibilityTests(PageCase):
    def setUp(self):
        super().setUp()
        self.people = people()
        self.group = AssignmentGroup.objects.create(name="Events")
        self.ticket = new_ticket(status=Status.OPEN)

    def test_the_page_assigns_within_a_group_whose_members_are_no_longer_admins(self):
        self.group.members.set([self.people["former"], self.people["away"]])

        response = self.save(self.ticket, assignment_group=self.group, assignee=self.agent)

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.assignment_group, self.ticket.assignee), (self.group, self.agent))

    def test_the_page_refuses_an_outsider_while_one_member_is_eligible(self):
        self.group.members.set([self.people["former"], self.people["kim"]])

        response = self.save(self.ticket, assignment_group=self.group, assignee=self.agent)

        self.assertEqual(self.form(response).errors["assignee"], ["Avery Agent is not a member of Events."])
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assignee)

    def test_the_script_is_handed_only_the_eligible_members(self):
        self.group.members.set([self.agent, *self.people.values()])
        lapsed = AssignmentGroup.objects.create(name="Lapsed")
        lapsed.members.set([self.people["former"], self.people["away"]])

        data = self.page(self.ticket).context["helpdesk_form_data"]

        groups = {group: set(members) for group, members in data["groups"].items()}
        kim, lee = str(self.people["kim"].pk), str(self.people["lee"].pk)
        self.assertEqual(groups, {str(self.group.pk): {str(self.agent.pk), kim, lee}, str(lapsed.pk): set()})
