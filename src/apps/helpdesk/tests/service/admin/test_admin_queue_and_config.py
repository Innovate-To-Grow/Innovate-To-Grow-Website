"""The ticket form's ServiceNow rules: a resolution code to resolve or close, and impact and urgency kept when a form
leaves them out. Tickets have no owner (I2G-HELPDESK-01): the form has no assignee or assignment group, and a page an
earlier release rendered that still posts them saves without touching the deprecated values."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ....models import AssignmentGroup, Ticket
from ...helpers import helpdesk_staff, make_admin
from ...helpers.service import Status, new_ticket

HOUR = timedelta(hours=1)


class TicketFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.other = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        self.client.force_login(self.agent)
        self.ticket = new_ticket(status=Status.OPEN)
        self.url = reverse("admin:helpdesk_ticket_change", args=[self.ticket.pk])

    def save(self, **values):
        data = {"status": Status.OPEN, "impact": "2", "urgency": "2", "category": ""}
        data.update({key: str(value.pk) if hasattr(value, "pk") else value for key, value in values.items()})
        return self.client.post(self.url, data)

    def errors(self, response):
        return response.context["adminform"].form.errors

    def test_resolving_or_closing_needs_a_resolution_code(self):
        for status in (Status.RESOLVED, Status.CLOSED):
            with self.subTest(status):
                response = self.save(status=status)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Choose a resolution code", str(self.errors(response)["resolution_code"]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.OPEN)

    def test_with_a_code_and_notes_it_resolves(self):
        response = self.save(status=Status.RESOLVED, resolution_code="solved", resolution_notes="Answered by phone.")

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.resolution_code, self.ticket.resolution_notes),
            (Status.RESOLVED, "solved", "Answered by phone."),
        )

    def test_a_ticket_already_resolved_saves_without_a_code(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.RESOLVED)

        self.assertEqual(self.save(status=Status.RESOLVED, impact="1").status_code, 302)

    def test_an_assignee_or_group_an_old_page_posts_is_ignored(self):
        group = AssignmentGroup.objects.create(name="Events")
        Ticket.objects.filter(pk=self.ticket.pk).update(assignment_group=group, assignee=self.agent)

        response = self.save(assignment_group="", assignee=self.other, impact="1")

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.impact, self.ticket.assignment_group, self.ticket.assignee), (1, group, self.agent)
        )

    def test_a_form_without_impact_or_urgency_keeps_the_tickets(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(impact=1, urgency=1, priority="urgent")

        response = self.client.post(self.url, {"status": Status.PENDING_INTERNAL, "category": "", "assignee": ""})

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.impact, self.ticket.priority), ("pending_internal", 1, "urgent")
        )

    def test_the_form_has_no_assignee_or_group(self):
        form = self.client.get(self.url).context["adminform"].form

        self.assertFalse({"assignee", "assignment_group"} & set(form.fields))
