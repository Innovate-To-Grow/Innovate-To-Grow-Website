"""The ticket page (timeline in a sandboxed iframe, field changes into the audit trail, internal notes with CSRF),
attachment downloads (headers, archive warning, files that are not stored), Ingest problems (Retry) and Settings."""

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_member

from ...models import Ticket, TicketAttachment, TicketEvent, TicketMessage
from .. import corpus
from ..helpers import FakeReader, helpdesk_staff, receive

Status = Ticket.Status


class TicketPageTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.reader = FakeReader()
        raw = corpus.message(
            html='<p>Hello <a href="https://example.org">site</a></p><script>alert(1)</script>',
            attachments=[
                ("report.pdf", b"%PDF-1.7 report", "application/pdf"),
                ("photo.png", b"\x89PNG\r\n\x1a\nimage", "image/png"),
                ("bundle.zip", b"PK\x03\x04archive", "application/zip"),
                ("setup.exe", b"MZ\x90\x00", "application/octet-stream"),
            ],
        )
        self.ticket = receive(raw, reader=self.reader)
        self.url = reverse("admin:helpdesk_ticket_change", args=[self.ticket.pk])

    def attachment(self, filename) -> TicketAttachment:
        return TicketAttachment.objects.get(message__ticket=self.ticket, filename=filename)

    def download_url(self, attachment, ticket=None):
        return reverse("admin:helpdesk_ticket_attachment", args=[(ticket or self.ticket).pk, attachment.pk])


class TimelineTests(TicketPageTestCase):
    def test_the_page_shows_the_sanitized_message_in_a_locked_down_iframe(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('sandbox="allow-popups allow-popups-to-escape-sandbox"', html)
        self.assertNotIn("allow-scripts", html)
        self.assertNotIn("allow-same-origin", html)
        self.assertIn("srcdoc=", html)
        # The body is escaped into the attribute; the script was removed when the message was stored.
        self.assertIn("&lt;p&gt;Hello", html)
        self.assertNotIn("alert(1)", html)
        self.assertContains(response, "Shadow mode.")
        self.assertContains(response, "Add an internal note")
        self.assertContains(response, "Blocked file type")
        self.assertContains(response, "archive: download after a warning")

    def test_opening_the_ticket_marks_it_read(self):
        self.assertTrue(self.ticket.unread)

        self.client.get(self.url)

        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.unread)

    def test_automated_messages_are_collapsed_and_labelled(self):
        oof = receive(corpus.out_of_office(), reader=self.reader)

        response = self.client.get(reverse("admin:helpdesk_ticket_change", args=[oof.pk]))

        self.assertContains(response, "<details>")
        self.assertContains(response, "Automatic reply")
        # The classification says how a person's message misread as automated mail gets back to the queue.
        self.assertContains(
            response,
            "Automatic reply — hidden from the default queue. If a person wrote it, use "
            "&quot;Not automated: move to the queue&quot; beside Save at the bottom of this page.",
        )

    def test_events_and_notes_appear_in_order(self):
        self.client.post(reverse("admin:helpdesk_ticket_note", args=[self.ticket.pk]), {"body": "Called the sender."})

        response = self.client.get(self.url)

        self.assertContains(response, "Ticket opened")
        self.assertContains(response, "Internal note")
        self.assertContains(response, "Called the sender.")


class SaveTests(TicketPageTestCase):
    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_change_saves_without_typed_confirmation_and_is_audited(self):
        # Impact 1 × urgency 2 makes the priority High (the priority itself is read-only on the page).
        data = {
            "status": Status.PENDING_CUSTOMER,
            "impact": "1",
            "urgency": "2",
            "priority": "low",
            "category": "",
            "assignee": str(self.agent.pk),  # posted by a page an earlier release rendered: ignored
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.impact, self.ticket.priority, self.ticket.assignee),
            (Status.PENDING_CUSTOMER, 1, "high", None),
        )
        kinds = set(self.ticket.events.values_list("kind", flat=True))
        self.assertTrue({TicketEvent.Kind.STATUS, TicketEvent.Kind.IMPACT, TicketEvent.Kind.PRIORITY} <= kinds)
        self.assertNotIn(TicketEvent.Kind.ASSIGNED, kinds)
        changes = self.ticket.events.filter(kind__in=(TicketEvent.Kind.STATUS, TicketEvent.Kind.IMPACT))
        self.assertEqual(set(changes.values_list("actor", flat=True)), {self.agent.pk})  # who made each change
        self.assertEqual(  # the fields as the page names them
            LogEntry.objects.get(object_id=str(self.ticket.pk)).change_message, "Changed status, impact, priority."
        )

    def test_saving_never_overwrites_what_the_ingest_wrote_meanwhile(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(participants=["pat@example.org", "new@example.org"])

        self.client.post(self.url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": ""})

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.participants, ["pat@example.org", "new@example.org"])

    def test_a_deprecated_assignee_who_is_no_longer_an_admin_still_lets_the_page_save(self):
        former = make_member(email="former@example.com")
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=former, requester_name="")

        page = self.client.get(self.url)
        response = self.client.post(
            self.url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": str(former.pk)}
        )

        self.assertContains(page, "pat@example.org")
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.assignee), (Status.OPEN, former))


class NoteTests(TicketPageTestCase):
    def note_url(self):
        return reverse("admin:helpdesk_ticket_note", args=[self.ticket.pk])

    def test_a_note_needs_text_and_a_bounded_length(self):
        empty = self.client.post(self.note_url(), {"body": "   "}, follow=True)
        too_long = self.client.post(self.note_url(), {"body": "x" * 20001}, follow=True)

        self.assertContains(empty, "Write the note before adding it.")
        self.assertContains(too_long, "at most 20,000 characters")
        self.assertFalse(self.ticket.messages.filter(kind=TicketMessage.Kind.NOTE).exists())

    def test_a_note_requires_post_and_csrf(self):
        self.assertEqual(self.client.get(self.note_url()).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.agent)

        self.assertEqual(strict.post(self.note_url(), {"body": "x"}).status_code, 403)
        self.assertFalse(self.ticket.messages.filter(kind=TicketMessage.Kind.NOTE).exists())
