"""The ticket page's resolution and routing fields.

- Resolution: a code to resolve or close the ticket here (one resolved meanwhile keeps its own), and a resolved or
  closed ticket keeps it; the notes are at most 20,000 characters, a line break counted once however the browser sent
  it, and the notes box says so (maxlength).
- Routing: the assignee rule is the services' (``tickets.membership_problem``); groups and categories offered are the
  active ones plus the ticket's own; no add, change, delete or view buttons beside category, group and assignee.
"""

from unittest.mock import patch

from unfold.widgets import UnfoldAdminTextareaWidget

from ....models import AssignmentGroup, Ticket, TicketCategory
from ....services import tickets
from ...helpers import make_admin, make_superuser
from ...helpers.service import Status, new_ticket
from .support import PageCase

RELATED = ("category", "assignment_group", "assignee")


class ResolutionTests(PageCase):
    def test_editing_the_status_into_resolved_or_closed_needs_a_code(self):
        ticket = new_ticket(status=Status.OPEN)
        for status in (Status.RESOLVED, Status.CLOSED):
            with self.subTest(status):
                response = self.save(ticket, status=status)

                self.assertEqual(
                    self.form(response).errors["resolution_code"],
                    ["Choose a resolution code to resolve or close the ticket."],
                )
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).status, Status.OPEN)

    def test_a_ticket_resolved_while_the_page_was_open_stays_resolved_with_its_code(self):
        ticket = new_ticket(status=Status.OPEN)
        shown = self.shown(ticket)  # In progress, no code
        tickets.resolve([ticket], actor=make_admin(apps=["helpdesk"], email="kim@example.com"), code="solved")

        self.assertEqual(self.save(ticket, shown, urgency="1").status_code, 302)

        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolution_code, ticket.urgency), (Status.RESOLVED, "solved", 1))

    def test_a_resolved_or_closed_ticket_keeps_its_resolution_code(self):
        for status in (Status.RESOLVED, Status.CLOSED):
            ticket = new_ticket(status=status, resolution_code="solved")
            with self.subTest(status):
                response = self.save(ticket, resolution_code="")

                self.assertEqual(
                    self.form(response).errors["resolution_code"],
                    ["A resolved or closed ticket keeps its resolution code."],
                )
                ticket.refresh_from_db()
                self.assertEqual(ticket.resolution_code, "solved")

    def test_another_code_may_replace_it(self):
        ticket = new_ticket(status=Status.RESOLVED, resolution_code="solved")

        self.assertEqual(self.save(ticket, resolution_code="workaround").status_code, 302)

        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolution_code), (Status.RESOLVED, "workaround"))

    def test_notes_are_at_most_20000_characters_counting_each_line_break_once(self):
        ticket = new_ticket(status=Status.OPEN)
        # 20,000 characters with "\n" line breaks; 20,099 as a browser posts them ("\r\n").
        notes = "\r\n".join(["x" * 199] * 99 + ["x" * 200])

        refused = self.save(ticket, resolution_notes="x" * 20001)
        accepted = self.save(ticket, resolution_notes=notes)

        self.assertEqual(
            self.form(refused).errors["resolution_notes"], ["Resolution notes can be at most 20,000 characters."]
        )
        self.assertEqual(accepted.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.resolution_notes, notes.replace("\r\n", "\n"))
        self.assertEqual(len(ticket.resolution_notes), 20000)

    def test_the_notes_box_says_how_long_the_notes_may_be(self):
        form = self.form(self.page(new_ticket()))

        self.assertIsInstance(form.fields["resolution_notes"].widget, UnfoldAdminTextareaWidget)
        self.assertIn('maxlength="20000"', str(form["resolution_notes"]))


class RoutingTests(PageCase):
    def test_the_assignee_rule_is_the_services(self):
        group = AssignmentGroup.objects.create(name="Events")
        ticket = new_ticket(status=Status.OPEN)

        with patch.object(tickets, "membership_problem", return_value="Avery is away this week.") as problem:
            response = self.save(ticket, assignment_group=group, assignee=self.agent)

        problem.assert_called_once_with(group, self.agent)
        self.assertEqual(self.form(response).errors["assignee"], ["Avery is away this week."])
        self.assertContains(response, "Avery is away this week.")
        ticket.refresh_from_db()
        self.assertEqual((ticket.assignment_group, ticket.assignee), (None, None))

    def test_the_page_says_who_is_not_a_member(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(make_admin(apps=["helpdesk"], email="kim@example.com", first_name="Kim", last_name="Lee"))

        response = self.save(new_ticket(status=Status.OPEN), assignment_group=group, assignee=self.agent)

        self.assertContains(response, "Avery Agent is not a member of Events.")

    def test_groups_and_categories_offered_are_the_active_ones_and_the_tickets_own(self):
        AssignmentGroup.objects.create(name="Events")
        retired = AssignmentGroup.objects.create(name="Retired", is_active=False)
        AssignmentGroup.objects.create(name="Gone", is_active=False)
        TicketCategory.objects.create(name="Registration")
        parking = TicketCategory.objects.create(name="Parking", is_active=False)
        TicketCategory.objects.create(name="Old", is_active=False)
        ticket = new_ticket(status=Status.OPEN, assignment_group=retired, category=parking)

        def offered(item, name) -> set[str]:
            return {choice.name for choice in self.form(self.page(item)).fields[name].queryset}

        self.assertEqual(offered(ticket, "assignment_group"), {"Events", "Retired"})
        self.assertEqual(offered(ticket, "category"), {"Registration", "Parking"})
        other = new_ticket(status=Status.OPEN)
        self.assertEqual(offered(other, "assignment_group"), {"Events"})
        self.assertEqual(offered(other, "category"), {"Registration"})
        # The ticket's own retired group and category do not stop its page from saving.
        self.assertEqual(self.save(ticket, urgency="1").status_code, 302)
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).assignment_group, retired)

    def test_no_related_object_buttons_beside_category_group_and_assignee(self):
        self.client.force_login(make_superuser(email="master@example.com"))  # who may add, change or delete any of them

        response = self.page(new_ticket(category=TicketCategory.objects.create(name="Registration")))

        form = self.form(response)
        for name in RELATED:
            widget = form.fields[name].widget
            with self.subTest(name):
                flags = (widget.can_add_related, widget.can_change_related, widget.can_delete_related)
                self.assertEqual((*flags, widget.can_view_related), (False, False, False, False))
                for link in ("add", "change", "delete", "view"):
                    self.assertNotContains(response, f'id="{link}_id_{name}"')
