"""What the ticket page hands the browser, and what a save of the resolution records.

- Every editable field (``form.EDITABLE``) renders ``autocomplete="off"``: a value the browser restores on Back would
  count as this person's edit. The data the page's script reads says whether the page shows the saved ticket
  ("fresh": a GET) or a refused save's input (a POST shown again), so the script resets only a fresh page.
- Clearing the resolution code of an open ticket is recorded as "Resolution code cleared (was: …)"; reopening a
  resolved ticket, notes typed with it or not, as "Resolution cleared on reopening (was: …)".
"""

import re

from ....admin.tickets.form import EDITABLE
from ....models import TicketEvent
from ...helpers.service import Status, new_ticket
from .support import PageCase

Kind = TicketEvent.Kind


def control(html: str, name: str) -> str:
    """The opening tag of the control named ``name`` (not its hidden ``initial-`` twin)."""
    found = re.search(rf'<(?:select|input|textarea)\b[^>]*\bname="{name}"[^>]*>', html)
    return found.group(0) if found else ""


class BrowserRestoreTests(PageCase):
    def test_every_editable_field_renders_autocomplete_off(self):
        form = self.form(self.page(new_ticket(status=Status.OPEN)))

        self.assertEqual(set(EDITABLE) - set(form.fields), set())  # all of them are on a person's open ticket
        for name in EDITABLE:
            with self.subTest(name):
                tag = control(str(form[name]), name)
                self.assertTrue(tag, name)
                self.assertIn('autocomplete="off"', tag)
                self.assertIn(f'name="{form[name].html_initial_name}"', str(form[name]))  # the value shown

    def test_the_page_says_whether_it_shows_the_saved_ticket(self):
        ticket = new_ticket(status=Status.OPEN)

        page = self.page(ticket)
        refused = self.save(ticket, status=Status.MERGED, urgency="1")

        self.assertIs(page.context["helpdesk_form_data"]["fresh"], True)
        self.assertIs(self.json_script(page, "helpdesk-form-data")["fresh"], True)
        self.assertContains(page, "helpdesk/js/ticket-form.js")  # the script that reads it
        self.assertEqual(refused.status_code, 200)
        self.assertIn("status", self.form(refused).errors)
        self.assertIs(refused.context["helpdesk_form_data"]["fresh"], False)
        self.assertIs(self.json_script(refused, "helpdesk-form-data")["fresh"], False)


class ResolutionHistoryTests(PageCase):
    def resolution(self, ticket) -> TicketEvent:
        return ticket.events.get(kind=Kind.RESOLUTION)

    def test_clearing_the_code_of_an_open_ticket_is_no_reopening(self):
        ticket = new_ticket(status=Status.OPEN, resolution_code="solved")

        response = self.save(ticket, resolution_code="")

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolution_code), (Status.OPEN, ""))
        event = self.resolution(ticket)
        self.assertEqual((event.actor, event.data), (self.agent, {"code": "", "notes": False, "was": "solved"}))
        page = self.page(ticket)
        self.assertContains(page, "Resolution code cleared (was: Solved) — Avery Agent")
        self.assertNotContains(page, "on reopening")

    def test_reopening_clears_it_even_with_notes_typed_in_the_same_save(self):
        ticket = new_ticket(status=Status.RESOLVED, resolution_code="solved")

        response = self.save(ticket, status=Status.OPEN, resolution_notes="Called back: still waiting for the badge.")

        self.assertEqual(response.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual((ticket.status, ticket.resolution_code), (Status.OPEN, ""))
        event = self.resolution(ticket)
        self.assertEqual((event.actor, event.data), (self.agent, {"cleared": "solved"}))
        self.assertContains(self.page(ticket), "Resolution cleared on reopening (was: Solved) — Avery Agent")
