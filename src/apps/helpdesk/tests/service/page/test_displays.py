"""What the ticket page shows beside its form.

- SLA: the clocks of the ticket as saved (a refused save does not show the clock of the status it asked for); a paused
  resolution clock says what is left of its target when it runs again.
- Linked tickets (in the Ticket section): related, merged into, follow-ups and the tickets merged in.
- Mail (collapsed): the flags (backfilled said in words), the classification (automated mail and spam say how to move
  them to the queue) and when the ticket was resolved or closed.
"""

from datetime import UTC, datetime, timedelta

from django.utils import timezone

from ....models import AssignmentGroup, Ticket
from ...helpers import make_admin
from ...helpers.service import Status, clocked_ticket, new_ticket
from .support import PageCase, change_url, ticket_admin

HOUR = timedelta(hours=1)
MOVE = (
    'hidden from the default queue. If a person wrote it, use "Not automated: move to the queue" beside Save at the '
    "bottom of this page."
)


class SLAPanelTests(PageCase):
    def test_a_refused_save_shows_the_clocks_of_the_saved_ticket(self):
        group = AssignmentGroup.objects.create(name="Events")
        group.members.add(make_admin(apps=["helpdesk"], email="kim@example.com"))
        ticket = clocked_ticket()  # New: both clocks run

        response = self.save(
            ticket, status=Status.RESOLVED, resolution_code="solved", assignment_group=group, assignee=self.agent
        )

        self.assertIn("assignee", self.form(response).errors)  # refused: the agent is not in Events
        # Still New: the response and the resolution are on track (not "No SLA" and "Met" for a resolved ticket).
        self.assertContains(response, 'class="i2g-helpdesk-sla is-running">On track</span>', count=2)
        self.assertNotContains(response, "is-met")
        self.assertEqual(Ticket.objects.get(pk=ticket.pk).status, Status.NEW)

    def test_a_paused_clock_says_what_is_left_when_it_runs_again(self):
        now = timezone.now()
        # The 5-day resolution target started 30 h ago and stood still from 10 h in: 4 d 14 h of it are left.
        ticket = clocked_ticket(
            started=now - 30 * HOUR,
            status=Status.PENDING_CUSTOMER,
            first_responded_at=now - 29 * HOUR,
            sla_paused_at=now - 20 * HOUR,
        )

        response = self.page(ticket)

        paused = '<span class="i2g-helpdesk-sla is-paused">Paused</span> — 4 d 14 h left when it runs again'
        self.assertContains(response, paused)  # not its due time, which moves on while the clock stands still
        self.assertContains(response, 'class="i2g-helpdesk-sla is-met">Met</span>')


class LinkedTicketTests(PageCase):
    def link(self, label, ticket) -> str:
        return f'{label} <a href="{change_url(ticket)}">{ticket.display_number}</a>'

    def test_follow_ups_and_merged_tickets_are_linked_both_ways(self):
        first = new_ticket(subject="Parking")
        follow_up = new_ticket(subject="Parking again", related_ticket=first)
        merged = new_ticket(subject="Parking too", status=Status.MERGED, merged_into=first)
        links = ticket_admin().links_display

        self.assertEqual(links(first), f"{self.link('Follow-up', follow_up)}, {self.link('Merged in', merged)}")
        self.assertEqual(links(follow_up), self.link("Related to", first))
        self.assertEqual(links(merged), self.link("Merged into", first))
        self.assertEqual(links(new_ticket()), "—")
        self.assertContains(self.page(first), self.link("Merged in", merged))

    def test_the_sections_the_page_shows_them_in(self):
        sections = dict(ticket_admin().fieldsets)

        self.assertIn("links_display", sections["Ticket"]["fields"])
        self.assertEqual(sections["Mail"]["classes"], ("collapse",))
        self.assertIn("closed_display", sections["Mail"]["fields"])
        self.assertEqual(ticket_admin().empty_value_display, "—")


class MailSectionTests(PageCase):
    def test_flags_say_when_a_ticket_was_backfilled(self):
        backfilled = "backfilled (imported late: no SLA and no acknowledgement)"
        flagged = new_ticket(backfilled=True, flags=["flood"])
        flags = ticket_admin().flags_display

        self.assertEqual(flags(flagged), f"flood, {backfilled}")
        self.assertEqual(flags(new_ticket(backfilled=True)), backfilled)
        self.assertEqual(flags(new_ticket(flags=["reply_all"])), "reply all")
        self.assertEqual(flags(new_ticket()), "—")
        self.assertContains(self.page(flagged), backfilled)

    def test_the_classification_of_spam_and_automated_mail_says_how_to_move_it(self):
        classification = ticket_admin().classification_display
        spam = new_ticket(status=Status.SPAM, classification="spam")
        bounce = new_ticket(automated=True, status=Status.CLOSED, classification="bounce")

        self.assertEqual(classification(spam), f"Spam — {MOVE}")
        self.assertEqual(classification(bounce), f"Bounce or delay report — {MOVE}")
        self.assertEqual(classification(new_ticket(classification="human")), "Human (or uncertain)")
        self.assertEqual(classification(new_ticket()), "—")
        self.assertContains(self.page(spam), "Spam — hidden from the default queue.")

    def test_when_it_was_resolved_or_closed(self):
        # Nov 3, 2026 18:05 UTC is 10:05 in the site's time zone (Pacific, standard time).
        closed = new_ticket(
            status=Status.CLOSED, resolution_code="solved", closed_at=datetime(2026, 11, 3, 18, 5, tzinfo=UTC)
        )
        closed_display = ticket_admin().closed_display

        self.assertEqual(closed_display.short_description, "Resolved or closed at")
        self.assertEqual(closed_display(closed), "Nov 03, 2026 10:05")
        self.assertEqual(closed_display(new_ticket()), "—")
        response = self.page(closed)
        self.assertContains(response, "Resolved or closed at")
        self.assertContains(response, "Nov 03, 2026 10:05")
