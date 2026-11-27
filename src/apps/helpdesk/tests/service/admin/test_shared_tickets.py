"""Tickets have no owner (I2G-HELPDESK-01): every Admin works every ticket, whatever group they were (not) in, and each
change keeps its actor. There is no assignee or assignment group on the page (one posted is ignored), no assign
action, filter or sidebar view, and no Assignment Groups page; an old bookmark of a removed view is redirected to the
list without it. Who replied last (and when) shows in the list and on the page instead."""

from datetime import timedelta
from urllib.parse import quote

from django.urls import reverse
from django.utils import timezone

from ....models import AssignmentGroup, Ticket, TicketCategory, TicketEvent, TicketMessage
from ...helpers import make_admin
from ...tickets.test_tickets import new_ticket
from ..page.support import PageCase, change_url

CHANGELIST = "/admin/helpdesk/ticket/"
REMOVED_VIEWS = ("My Tickets", "My Groups", "Unassigned", "Assignment Groups")
Status, Kind = Ticket.Status, TicketEvent.Kind


def reply(ticket, *, author=None, name="Sam Lead", minutes_ago=5, delivery=TicketMessage.Delivery.SENT):
    return TicketMessage.objects.create(
        ticket=ticket,
        kind=TicketMessage.Kind.REPLY,
        author=author,
        from_name=name,
        occurred_at=timezone.now() - timedelta(minutes=minutes_ago),
        delivery_status=delivery,
    )


class EveryAdminWorksEveryTicketTests(PageCase):
    def setUp(self):
        super().setUp()
        self.other = make_admin(email="sam@example.com", first_name="Sam", last_name="Lead")
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(self.other)
        self.ticket = new_ticket(status=Status.NEW)
        # Held by someone else's group under the old rules: it makes no difference now.
        Ticket.objects.filter(pk=self.ticket.pk).update(assignment_group=group, assignee=self.other)
        self.category = TicketCategory.objects.create(name="Showcase")

    def test_any_admin_edits_notes_and_resolves_with_their_name_on_record(self):
        self.save(self.ticket, status=Status.OPEN, category=self.category)
        self.client.post(reverse("admin:helpdesk_ticket_note", args=[self.ticket.pk]), {"body": "On it."})
        self.save(self.ticket, status=Status.RESOLVED, resolution_code="solved")

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.category), (Status.RESOLVED, self.category))
        events = TicketEvent.objects.filter(ticket=self.ticket, kind__in=(Kind.STATUS, Kind.CATEGORY, Kind.NOTE))
        self.assertEqual(events.count(), 4)
        self.assertEqual(set(events.values_list("actor", flat=True)), {self.agent.pk})

    def test_the_page_offers_no_assignee_or_group_and_ignores_them_when_posted(self):
        response = self.page(self.ticket)
        form = self.form(response)
        self.assertNotIn("assignee", form.fields)
        self.assertNotIn("assignment_group", form.fields)
        self.assertNotContains(response, 'name="assignee"')
        self.assertNotContains(response, 'name="assignment_group"')

        data = {**self.shown(self.ticket), "assignee": str(self.agent.pk), "initial-assignee": str(self.other.pk)}
        data.update({"assignment_group": "", "initial-assignment_group": ""})
        self.client.post(change_url(self.ticket), data)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assignee, self.other)
        self.assertIsNotNone(self.ticket.assignment_group_id)
        self.assertFalse(TicketEvent.objects.filter(kind__in=(Kind.ASSIGNED, Kind.GROUP)).exists())


class RemovedViewsTests(PageCase):
    def test_old_bookmarks_go_to_the_list_without_the_removed_parameter(self):
        group = AssignmentGroup.objects.create(name="Events")
        for query, kept in (
            ("assignee=me", ""),
            ("assignee=none&status=done", "?status=done"),
            ("group=mine", ""),
            (f"group={group.pk}&mail=all", "?mail=all"),
        ):
            with self.subTest(query=query):
                response = self.client.get(f"{CHANGELIST}?{query}")

                self.assertRedirects(response, f"{CHANGELIST}{kept}", fetch_redirect_response=False)
                self.assertEqual(self.client.get(response["Location"]).status_code, 200)

    def test_the_list_has_no_assign_actions_or_filters(self):
        response = self.client.get(CHANGELIST)

        actions = {name for name, _label in response.context["action_form"].fields["action"].choices}
        self.assertIn("resolve_tickets", actions)
        self.assertFalse({"assign_to_me", "unassign"} & actions)
        parameters = {getattr(spec, "parameter_name", "") for spec in response.context["cl"].filter_specs}
        self.assertIn("reply", parameters)
        self.assertFalse({"assignee", "group"} & parameters)
        self.assertNotContains(response, "Assign to me")

    def test_no_assignment_groups_page_and_no_removed_sidebar_views(self):
        self.assertEqual(self.client.get("/admin/helpdesk/assignmentgroup/").status_code, 404)

        response = self.client.get(CHANGELIST)
        helpdesk = next(group for group in response.context["sidebar_navigation"] if group["title"] == "Helpdesk")
        titles = [item["title"] for item in helpdesk["items"]]
        self.assertEqual(titles[:4], ["Queue", "Awaiting Reply", "SLA Breached", "Automated & Spam"])
        self.assertFalse(set(REMOVED_VIEWS) & set(titles))

    def test_a_ticket_page_opened_from_a_removed_view_still_opens(self):
        ticket = new_ticket()

        response = self.client.get(f"{change_url(ticket)}?_changelist_filters={quote('assignee=me')}")

        self.assertEqual(response.status_code, 200)
        helpdesk = next(group for group in response.context["sidebar_navigation"] if group["title"] == "Helpdesk")
        self.assertTrue(next(item for item in helpdesk["items"] if item["title"] == "Queue")["active"])


class LastReplyTests(PageCase):
    def test_the_list_says_who_replied_last(self):
        answered = new_ticket(subject="Answered")
        reply(answered, name="Kim Old", minutes_ago=60)
        reply(answered, name="Sam Lead", minutes_ago=5)
        reply(answered, name="Failed Fay", minutes_ago=1, delivery=TicketMessage.Delivery.FAILED)
        new_ticket(subject="Nobody yet")

        response = self.client.get(CHANGELIST)

        self.assertContains(response, "Last reply")
        rows = {ticket.subject: ticket for ticket in response.context["cl"].result_list}
        self.assertEqual(rows["Answered"].last_reply_by, "Sam Lead")
        self.assertIsNone(rows["Nobody yet"].last_reply_at)
        self.assertContains(response, "Sam Lead")
        self.assertNotContains(response, "Failed Fay")

    def test_the_page_says_nobody_replied_yet(self):
        response = self.page(new_ticket())

        self.assertContains(response, "Nobody has replied to the requester from the helpdesk yet.")

    def test_the_page_names_the_last_replier_when_and_a_delivery_not_done_yet(self):
        ticket = new_ticket()
        sent = reply(ticket, author=self.agent, minutes_ago=30)
        when = timezone.localtime(sent.occurred_at).strftime("%b %d, %Y %H:%M")
        self.assertContains(self.page(ticket), f"Avery Agent, {when}")

        queued = reply(ticket, author=self.agent, minutes_ago=1, delivery=TicketMessage.Delivery.QUEUED)
        when = timezone.localtime(queued.occurred_at).strftime("%b %d, %Y %H:%M")
        self.assertContains(self.page(ticket), f"Avery Agent, {when} (Queued)")
