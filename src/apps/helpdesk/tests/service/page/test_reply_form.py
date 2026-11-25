"""The reply form on the ticket page (``views.reply_context``) and the data the page's script reads.

- A refused reply comes back once with what was typed (body, Cc, the status chosen) and why, inline and as a message;
  when the form is no longer offered (shadow mode switched on, say), the text stays on the page, read-only, to copy.
- After a reply the status is "On hold – awaiting requester" by default, and kept for a resolved or closed ticket.
- The response templates (each filled in for the ticket) and the form helpers (each group's members, the priority of
  each impact × urgency, who "me" is) are also handed to the script as JSON.
"""

from django.test import override_settings
from django.urls import reverse
from django.utils.html import escape

from ....models import AssignmentGroup, ResponseTemplate, TicketCategory
from ...helpers import make_admin
from ...helpers.service import Status, new_ticket, sending_settings
from .support import PageCase, change_url

BODY = "The showcase starts at 10."
BAD_CC = '"bad@" in Cc is not a plain email address (use name@example.com, separated by commas).'
SHADOW = "Shadow mode is on: nothing is sent from the helpdesk. An Admin can switch it off in Helpdesk → Settings."


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class RefusedReplyTests(PageCase):
    def setUp(self):
        super().setUp()
        self.ticket = new_ticket(status=Status.OPEN)
        self.draft_key = f"helpdesk_reply_draft:{self.ticket.pk}"

    def reply(self, **data):
        response = self.client.post(
            reverse("admin:helpdesk_ticket_reply", args=[self.ticket.pk]), {"body": BODY, **data}
        )
        self.assertRedirects(response, f"{change_url(self.ticket)}#helpdesk-reply", fetch_redirect_response=False)
        return response

    def test_a_refused_reply_comes_back_once_with_what_was_typed_and_why(self):
        sending_settings()
        self.reply(cc="bad@", status=Status.OPEN)
        draft = {"body": BODY, "cc": "bad@", "status": "open", "error": BAD_CC}
        self.assertEqual(self.client.session[self.draft_key], draft)

        page = self.page(self.ticket)

        shown = {name: page.context[f"helpdesk_reply_{name}"] for name in draft}
        self.assertEqual(shown, draft)
        self.assertEqual(self.messages(page), [f"The reply was not sent: {BAD_CC}"])
        self.assertContains(page, f"Not sent: {escape(BAD_CC)}")
        self.assertContains(page, '<option value="open" selected>In progress</option>', html=True)
        self.assertNotIn(self.draft_key, self.client.session)
        again = self.page(self.ticket)  # shown once
        self.assertEqual((again.context["helpdesk_reply_body"], again.context["helpdesk_reply_error"]), ("", ""))
        self.assertFalse(self.ticket.messages.exists())

    def test_with_sending_stopped_the_text_stays_on_the_page_to_copy(self):
        self.reply(status=Status.PENDING_CUSTOMER)  # shadow mode is on

        page = self.page(self.ticket)

        self.assertNotIn("helpdesk_reply_url", page.context)
        self.assertEqual(page.context["helpdesk_reply_refusal"], SHADOW)
        self.assertEqual(page.context["helpdesk_reply_body"], BODY)
        self.assertEqual(self.messages(page), [f"The reply was not sent: {SHADOW}"])
        self.assertContains(page, "Its text is below to copy.")
        self.assertContains(
            page, f'<textarea readonly rows="6" aria-label="The reply that was not sent">{BODY}</textarea>', html=True
        )
        self.assertNotContains(page, 'id="helpdesk-reply-body"')
        self.assertNotIn("Its text is below to copy.", self.page(self.ticket).content.decode())  # shown once

    def test_a_status_the_form_does_not_offer_comes_back_as_keep_the_current_one(self):
        sending_settings()

        self.reply(cc="bad@", status=Status.CLOSED)

        self.assertEqual(self.page(self.ticket).context["helpdesk_reply_status"], "")


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class ReplyFormTests(PageCase):
    def setUp(self):
        super().setUp()
        sending_settings()

    def test_the_status_after_a_reply_is_on_hold_unless_the_ticket_is_done(self):
        defaults = {
            Status.NEW: Status.PENDING_CUSTOMER,
            Status.OPEN: Status.PENDING_CUSTOMER,
            Status.PENDING_INTERNAL: Status.PENDING_CUSTOMER,
            Status.RESOLVED: "",
            Status.CLOSED: "",
        }
        for status, default in defaults.items():
            with self.subTest(status):
                page = self.page(new_ticket(status=status))
                self.assertEqual(page.context["helpdesk_reply_status"], default)
        self.assertContains(page, '<option value="" selected>Keep the current status</option>', html=True)

    def test_the_templates_are_handed_to_the_script_filled_in(self):
        registration = TicketCategory.objects.create(name="Registration")
        ticket = new_ticket(status=Status.OPEN, category=registration, requester_name="Pat Doe")
        ResponseTemplate.objects.create(name="Hello", body="Hi {requester_name},", order=1)
        ResponseTemplate.objects.create(name="Badges", body="About {ticket}", category=registration, order=9)

        page = self.page(ticket)

        offered = page.context["helpdesk_reply_templates"]
        self.assertEqual(
            [(item["name"], item["category"], item["body"]) for item in offered],
            [("Badges", "Registration", f"About {ticket.display_number}"), ("Hello", "", "Hi Pat Doe,")],
        )
        self.assertEqual(set(offered[0]), {"id", "name", "category", "body"})
        self.assertEqual(self.json_script(page, "helpdesk-reply-templates"), offered)

    def test_the_form_helpers_handed_to_the_script(self):
        kim = make_admin(email="kim@example.com", first_name="Kim", last_name="Lee")
        events = AssignmentGroup.objects.create(name="Events")
        events.members.add(kim, self.agent)
        nobody = AssignmentGroup.objects.create(name="Nobody yet", is_active=False)

        page = self.page(new_ticket(status=Status.OPEN))

        data = page.context["helpdesk_form_data"]
        self.assertEqual(data["me"], str(self.agent.pk))
        groups = {group: set(members) for group, members in data["groups"].items()}
        self.assertEqual(groups, {str(events.pk): {str(kim.pk), str(self.agent.pk)}, str(nobody.pk): set()})
        self.assertEqual(
            data["priorities"],
            {
                "1-1": "1 – Critical",
                "1-2": "2 – High",
                "1-3": "3 – Moderate",
                "2-1": "2 – High",
                "2-2": "3 – Moderate",
                "2-3": "4 – Low",
                "3-1": "3 – Moderate",
                "3-2": "4 – Low",
                "3-3": "4 – Low",
            },
        )
        self.assertEqual(self.json_script(page, "helpdesk-form-data"), data)
        self.assertContains(page, "helpdesk/js/ticket-page.js")  # the script that reads it
