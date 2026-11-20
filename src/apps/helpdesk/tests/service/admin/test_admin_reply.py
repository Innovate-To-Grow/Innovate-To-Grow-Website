"""The ticket page's reply form (offered only while sending is allowed), the reply view (queues the reply, needs the
Helpdesk grant), the response-template prefill, and the SLA displays."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import BackgroundJob

from ....models import ResponseTemplate, Ticket, TicketCategory, TicketMessage
from ....services.outbound import jobs
from ... import corpus
from ...helpers import FakeReader, helpdesk_staff, make_admin, receive
from ...helpers.service import Status, sending_settings


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class ReplyPageTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.ticket = receive(corpus.message(cc="kim@example.org"), reader=FakeReader())
        self.url = reverse("admin:helpdesk_ticket_change", args=[self.ticket.pk])
        self.reply_url = reverse("admin:helpdesk_ticket_reply", args=[self.ticket.pk])

    def replies(self):
        return TicketMessage.objects.filter(ticket=self.ticket, kind=TicketMessage.Kind.REPLY)


class ReplyFormTests(ReplyPageTestCase):
    def test_no_reply_form_in_shadow_mode(self):
        response = self.client.get(self.url)

        self.assertNotContains(response, 'id="helpdesk-reply-body"')
        self.assertNotIn("helpdesk_reply_url", response.context)
        self.assertIn("Shadow mode is on", response.context["helpdesk_reply_refusal"])
        self.assertTrue(response.context["helpdesk_shadow_mode"])

    def test_the_form_with_sending_on(self):
        sending_settings()

        response = self.client.get(self.url)

        self.assertContains(response, 'id="helpdesk-reply-body"')
        self.assertContains(response, f'action="{self.reply_url}"')
        self.assertEqual(response.context["helpdesk_reply_to"], "pat@example.org")
        self.assertEqual(
            response.context["helpdesk_reply_subject"],
            f"Re: Question about the showcase [{self.ticket.display_number}]",
        )
        self.assertContains(response, self.ticket.display_number)
        self.assertEqual(response.context["helpdesk_reply_cc_suggestions"], ["kim@example.org"])
        self.assertEqual(response.context["helpdesk_reply_body"], "")
        self.assertFalse(response.context["helpdesk_shadow_mode"])

    def test_why_a_ticket_cannot_be_answered_is_shown_with_sending_on(self):
        sending_settings()
        Ticket.objects.filter(pk=self.ticket.pk).update(status=Status.SPAM)

        response = self.client.get(self.url)

        self.assertNotContains(response, 'id="helpdesk-reply-body"')
        self.assertContains(response, "Automated mail and spam are never answered from the helpdesk.")


class TemplatePrefillTests(ReplyPageTestCase):
    def setUp(self):
        super().setUp()
        sending_settings()
        self.template = ResponseTemplate.objects.create(
            name="Showcase time", body="Hi {requester_name}, about {ticket} ({subject}) — {agent_name}", order=5
        )

    def test_a_chosen_template_fills_the_reply_with_its_placeholders_replaced(self):
        response = self.client.get(f"{self.url}?template={self.template.pk}")

        filled = f"Hi Pat Doe, about {self.ticket.display_number} (Question about the showcase) — Avery Agent"
        self.assertEqual(
            response.context["helpdesk_reply_template"],
            {"id": str(self.template.pk), "name": "Showcase time", "category": "", "body": filled},
        )
        self.assertEqual(response.context["helpdesk_reply_body"], filled)
        self.assertContains(response, f"Hi Pat Doe, about {self.ticket.display_number}")
        self.assertContains(response, f'<option value="{self.template.pk}" selected>Showcase time</option>', html=True)

    def test_an_unknown_or_malformed_or_inactive_template_fills_nothing(self):
        inactive = ResponseTemplate.objects.create(name="Old", body="Old text", is_active=False)
        for value in ("not-a-uuid", "00000000-0000-0000-0000-000000000000", str(inactive.pk)):
            with self.subTest(value):
                response = self.client.get(f"{self.url}?template={value}")
                self.assertIsNone(response.context["helpdesk_reply_template"])
                self.assertEqual(response.context["helpdesk_reply_body"], "")

    def test_the_tickets_category_templates_come_first(self):
        category = TicketCategory.objects.create(name="Registration")
        Ticket.objects.filter(pk=self.ticket.pk).update(category=category)
        first = ResponseTemplate.objects.create(name="Registration help", body="x", category=category, order=9)

        response = self.client.get(self.url)

        offered = response.context["helpdesk_reply_templates"]
        self.assertEqual([item["id"] for item in offered], [str(first.pk), str(self.template.pk)])
        self.assertEqual([item["category"] for item in offered], ["Registration", ""])


class ReplyViewTests(ReplyPageTestCase):
    def post(self, **data):
        data.setdefault("body", "The showcase starts at 10.")
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.reply_url, data)

    def test_a_reply_is_queued_and_the_page_shows_it(self):
        sending_settings()

        response = self.post(cc="lee@example.org", status=Status.PENDING_CUSTOMER)

        self.assertRedirects(response, f"{self.url}#helpdesk-timeline", fetch_redirect_response=False)
        reply = self.replies().get()
        self.assertEqual((reply.author, reply.cc_addresses), (self.agent, ["lee@example.org"]))
        self.assertTrue(BackgroundJob.objects.filter(kind=jobs.REPLY_JOB_KIND, dedupe_key=f"reply:{reply.pk}").exists())
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.PENDING_CUSTOMER)
        page = self.client.get(self.url)
        self.assertContains(page, "Reply queued to pat@example.org")
        self.assertContains(page, "The showcase starts at 10.")

    def test_a_status_the_form_does_not_offer_is_ignored(self):
        sending_settings()

        self.post(status=Status.CLOSED)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.NEW)
        self.assertEqual(self.replies().count(), 1)

    def test_a_refused_reply_says_why_and_stores_nothing(self):
        response = self.post()  # shadow mode is on

        self.assertRedirects(response, f"{self.url}#helpdesk-reply", fetch_redirect_response=False)
        self.assertFalse(self.replies().exists())
        self.assertContains(self.client.get(self.url), "Shadow mode is on")

    def test_an_empty_reply_is_refused(self):
        sending_settings()

        self.post(body="  ")

        self.assertFalse(self.replies().exists())

    def test_the_helpdesk_grant_is_required(self):
        sending_settings()
        self.client.force_login(make_admin(apps=["mail"], email="mailer@example.com"))

        response = self.post()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.replies().exists())

    def test_only_a_post_and_only_for_a_ticket_that_exists(self):
        sending_settings()

        self.assertEqual(self.client.get(self.reply_url).status_code, 405)
        missing = reverse("admin:helpdesk_ticket_reply", args=["00000000-0000-0000-0000-000000000000"])
        self.assertEqual(self.client.post(missing, {"body": "Hi"}).status_code, 404)


class SLADisplayTests(ReplyPageTestCase):
    def test_the_page_shows_both_clocks(self):
        response = self.client.get(self.url)

        html = response.content.decode()
        self.assertIn('class="i2g-helpdesk-sla is-running">On track</span>', html)
        self.assertIn("First response", html)

    def test_a_ticket_without_a_clock_says_so(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(
            sla_started_at=None, response_due_at=None, resolution_due_at=None
        )

        self.assertContains(self.client.get(self.url), "No SLA")

    def test_a_met_response_shows_when_it_was_made(self):
        self.client.post(
            self.url,
            {"status": Status.OPEN, "impact": "2", "urgency": "2", "category": "", "assignee": ""},
        )

        response = self.client.get(self.url)

        self.assertContains(response, 'class="i2g-helpdesk-sla is-met">Met</span>')
        self.assertContains(response, ", responded ")
