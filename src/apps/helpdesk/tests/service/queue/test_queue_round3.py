"""The queue after the second live check: the SLA column sorts as it reads, a number search keeps the list's counts,
Spam is offered only where it can match, priorities list by severity, and the bulk actions say why they left tickets as they were (or are refused, or not offered, where they could never act)."""

from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from ....models import Ticket, TicketMessage
from ...helpers.service import Status, clocked_ticket, new_ticket
from .support import ACTION_SESSION_KEY, QueueCase

Priority = Ticket.Priority


class SortAndSearchTests(QueueCase):
    def test_the_sla_column_sorts_breaches_first_then_running_paused_and_done_or_unclocked_last(self):
        now = timezone.now()
        clocked_ticket(subject="due later", started=now - timedelta(hours=1))
        clocked_ticket(subject="breached", started=now - timedelta(hours=2), response_breached=True)
        clocked_ticket(subject="due soon", started=now - timedelta(hours=20))
        answered = {"first_responded_at": now, "status": Status.PENDING_CUSTOMER, "sla_paused_at": now}
        clocked_ticket(subject="paused", started=now - timedelta(hours=1), **answered)
        new_ticket(subject="no clock", status=Status.OPEN)
        index = self.get().context["cl"].list_display.index("sla_column")

        listed = self.listed(f"o={index}")

        self.assertEqual(listed[:4], ["breached", "due soon", "due later", "paused"])
        self.assertEqual(listed[4], "no clock")
        self.assertEqual(self.listed(f"o=-{index}")[0], "no clock")

    def test_a_number_search_from_a_filtered_view_keeps_the_message_count(self):
        ticket = new_ticket(subject="Counted", status=Status.OPEN)
        for _ in range(2):
            TicketMessage.objects.create(
                ticket=ticket,
                kind=TicketMessage.Kind.CUSTOMER,
                from_address="pat@example.org",
                occurred_at=timezone.now(),
            )

        rows = self.get(f"reply=awaiting&q={ticket.number}").context["cl"].result_list

        self.assertEqual([(row.subject, row.inbound_count) for row in rows], [("Counted", 2)])


class FilterTests(QueueCase):
    def test_spam_is_a_status_choice_only_where_spam_is_listed(self):
        self.assertNotIn("Spam", self.choices("status"))
        self.assertIn("Spam", self.choices("status", "mail=automated"))
        self.assertIn("Spam", self.choices("status", "mail=all"))

    def test_priorities_are_listed_and_filtered_by_severity(self):
        new_ticket(subject="critical", priority=Priority.URGENT, status=Status.OPEN)
        new_ticket(subject="low", priority=Priority.LOW, status=Status.OPEN)

        self.assertEqual(list(self.choices("priority"))[1:], ["1 – Critical", "2 – High", "3 – Moderate", "4 – Low"])
        self.assertEqual(self.listed("priority=urgent"), ["critical"])


class ActionTests(QueueCase):
    def test_the_resolve_page_loads_the_helpdesk_stylesheet(self):
        response = self.act("resolve_tickets", new_ticket(status=Status.OPEN))

        self.assertContains(response, "helpdesk/css/helpdesk.css")
        self.assertContains(response, '<h2 class="i2g-helpdesk-heading">Resolve tickets</h2>', html=True)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_move_to_the_queue_and_mark_as_spam_say_why_they_left_tickets(self):
        person = new_ticket(status=Status.OPEN)
        spam = new_ticket(status=Status.SPAM)

        moved = self.messages(self.act("move_to_queue", person))
        marked = self.messages(self.act("mark_spam", spam, person))

        self.assertEqual(
            moved,
            [
                "0 tickets moved to the queue. 1 left as it was: only automated mail and spam are moved (a merged ticket "
                "never)."
            ],
        )
        self.assertEqual(marked, ["1 ticket marked as spam. 1 left as it was: they are spam or merged already."])

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_marking_only_spam_or_merged_tickets_is_refused_before_the_typed_word(self):
        spam = new_ticket(status=Status.SPAM)
        merged = new_ticket(status=Status.MERGED)

        response = self.act("mark_spam", spam, merged, follow=False)

        self.assertNotIn("confirm-action", response.url)
        self.assertNotIn(ACTION_SESSION_KEY, self.client.session)
        self.assertEqual(self.messages(response), ["Nothing to mark: the selected tickets are spam or merged already."])

    def test_the_automated_view_offers_only_actions_that_can_act_there(self):
        offered = {
            name
            for name, _label in self.get("mail=automated&status=any").context["action_form"].fields["action"].choices
        }

        self.assertTrue({"move_to_queue", "mark_spam", "mark_read"} <= offered)
        self.assertFalse({"merge_tickets", "resolve_tickets", "close_tickets", "reopen_tickets"} & offered)
        self.assertFalse({"assign_to_me", "unassign"} & offered)  # tickets have no owner
