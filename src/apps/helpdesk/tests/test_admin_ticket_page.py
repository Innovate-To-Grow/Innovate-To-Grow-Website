"""The ticket page (timeline in a sandboxed iframe, field changes into the audit trail, internal notes with CSRF),
attachment downloads (headers, archive warning, files that are not stored), Ingest problems (Retry) and Settings."""

from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.core.models import BackgroundJob, InboundMessage

from ..models import HelpdeskSettings, Ticket, TicketAttachment, TicketEvent, TicketMessage
from ..services.ingest import jobs
from . import corpus
from .helpers import FakeReader, helpdesk_staff, make_admin, queue, receive

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
        self.assertContains(response, "automated, hidden from the default queue")

    def test_events_and_notes_appear_in_order(self):
        self.client.post(reverse("admin:helpdesk_ticket_note", args=[self.ticket.pk]), {"body": "Called the sender."})

        response = self.client.get(self.url)

        self.assertContains(response, "Ticket opened")
        self.assertContains(response, "Internal note")
        self.assertContains(response, "Called the sender.")


class SaveTests(TicketPageTestCase):
    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_a_change_saves_without_typed_confirmation_and_is_audited(self):
        data = {"status": Status.PENDING_CUSTOMER, "priority": "high", "category": "", "assignee": str(self.agent.pk)}

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(
            (self.ticket.status, self.ticket.priority, self.ticket.assignee),
            (Status.PENDING_CUSTOMER, "high", self.agent),
        )
        kinds = set(self.ticket.events.values_list("kind", flat=True))
        self.assertTrue({TicketEvent.Kind.STATUS, TicketEvent.Kind.PRIORITY, TicketEvent.Kind.ASSIGNED} <= kinds)
        self.assertEqual(
            LogEntry.objects.get(object_id=str(self.ticket.pk)).change_message, "Changed status, priority, assignee."
        )

    def test_saving_never_overwrites_what_the_ingest_wrote_meanwhile(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(participants=["pat@example.org", "new@example.org"])

        self.client.post(self.url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": ""})

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.participants, ["pat@example.org", "new@example.org"])

    def test_an_assignee_who_lost_the_grant_still_lets_the_page_save(self):
        former = make_admin(apps=["mail"], email="former@example.com")
        Ticket.objects.filter(pk=self.ticket.pk).update(assignee=former, requester_name="")

        page = self.client.get(self.url)
        response = self.client.post(
            self.url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": str(former.pk)}
        )

        self.assertContains(page, "pat@example.org")
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.assignee), (Status.OPEN, former))

    def test_only_helpdesk_staff_can_be_chosen_as_assignee(self):
        outsider = make_admin(apps=["mail"], email="mailer@example.com")

        response = self.client.post(
            self.url, {"status": Status.OPEN, "priority": "normal", "category": "", "assignee": str(outsider.pk)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("assignee", response.context["adminform"].form.errors)


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


class AttachmentDownloadTests(TicketPageTestCase):
    def test_a_download_is_an_attachment_that_is_never_sniffed_or_cached(self):
        response = self.client.get(self.download_url(self.attachment("report.pdf")))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-1.7 report")
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="report.pdf"')
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_a_raster_image_keeps_its_type_and_is_still_an_attachment(self):
        response = self.client.get(self.download_url(self.attachment("photo.png")))

        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))

    def test_an_archive_needs_a_warning_first(self):
        url = self.download_url(self.attachment("bundle.zip"))

        warning = self.client.get(url)
        download = self.client.get(f"{url}?confirm=1")

        self.assertContains(warning, "is an archive")
        self.assertContains(warning, "Download anyway")
        self.assertEqual(download.content, b"PK\x03\x04archive")

    def test_a_blocked_file_is_not_stored_and_not_served(self):
        blocked = self.attachment("setup.exe")

        response = self.client.get(self.download_url(blocked))

        self.assertTrue(blocked.blocked)
        self.assertIsNone(blocked.content)
        self.assertEqual(response.status_code, 404)

    def test_an_attachment_is_served_only_through_its_own_ticket_and_with_the_grant(self):
        other = receive(corpus.message(message_id="<other@x>", sender="kim@example.org"), reader=self.reader)
        url = self.download_url(self.attachment("report.pdf"), ticket=other)

        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(make_admin(apps=["mail"], email="mailer@example.com"))
        self.assertEqual(self.client.get(self.download_url(self.attachment("report.pdf"))).status_code, 403)


class IngestProblemTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        self.failed = queue(status=InboundMessage.Status.FAILED, last_error="Microsoft Graph could not be reached.")
        self.skipped = queue(status=InboundMessage.Status.SKIPPED, last_error="No longer in the mailbox.")
        self.done = queue(status=InboundMessage.Status.DONE)
        self.url = reverse("admin:helpdesk_ingestrecord_changelist")

    def test_the_page_opens_on_the_problems(self):
        response = self.client.get(self.url)

        self.assertEqual({row.pk for row in response.context["cl"].result_list}, {self.failed.pk, self.skipped.pk})
        everything = self.client.get(self.url, {"state": "all"})
        self.assertEqual(len(everything.context["cl"].result_list), 3)
        done = self.client.get(self.url, {"state": "done"})
        self.assertEqual([row.pk for row in done.context["cl"].result_list], [self.done.pk])

    def test_retry_queues_the_problems_again_and_wakes_the_ingest(self):
        data = {"action": "retry", "index": "0", "_selected_action": [str(self.failed.pk), str(self.done.pk)]}

        response = self.client.post(self.url, {**data, "state": "all"}, follow=True)

        self.failed.refresh_from_db()
        self.done.refresh_from_db()
        self.assertEqual((self.failed.status, self.failed.attempts), (InboundMessage.Status.PENDING, 0))
        self.assertEqual(self.done.status, InboundMessage.Status.DONE)
        self.assertContains(response, "queued again for import")
        self.assertTrue(BackgroundJob.objects.filter(kind=jobs.INGEST_JOB_KIND).exists())

    def test_rows_link_to_their_ticket_and_are_read_only(self):
        ticket = receive(corpus.message())
        row = InboundMessage.objects.get(result__ticket=ticket.number)

        response = self.client.get(self.url, {"state": "done"})
        detail = self.client.get(reverse("admin:helpdesk_ingestrecord_change", args=[row.pk]))

        self.assertContains(response, ticket.display_number)
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, 'name="_save"')


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SettingsAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        self.list_url = reverse("admin:helpdesk_helpdesksettings_changelist")

    def test_the_list_opens_the_one_settings_row(self):
        self.assertRedirects(self.client.get(self.list_url), reverse("admin:helpdesk_helpdesksettings_add"))
        settings = HelpdeskSettings.objects.create()
        self.assertRedirects(
            self.client.get(self.list_url), reverse("admin:helpdesk_helpdesksettings_change", args=[settings.pk])
        )
        self.assertEqual(self.client.get(reverse("admin:helpdesk_helpdesksettings_add")).status_code, 403)

    def test_shadow_mode_cannot_be_switched_off_and_saving_wakes_the_ingest(self):
        settings = HelpdeskSettings.objects.create()
        queue(corpus.message(), reader=FakeReader())
        form = (
            self.client.get(reverse("admin:helpdesk_helpdesksettings_change", args=[settings.pk]))
            .context["adminform"]
            .form
        )
        data = {name: form[name].value() for name in form.fields}
        data.update(enabled="on", pause_while_campaign_sending="on", shadow_mode="")

        response = self.client.post(reverse("admin:helpdesk_helpdesksettings_change", args=[settings.pk]), data)

        self.assertEqual(response.status_code, 302)
        settings.refresh_from_db()
        self.assertTrue(settings.shadow_mode)
        self.assertNotIn("shadow_mode", form.fields)
        self.assertTrue(BackgroundJob.objects.filter(kind=jobs.INGEST_JOB_KIND).exists())

    def test_categories_are_listed_and_editable(self):
        response = self.client.post(
            reverse("admin:helpdesk_ticketcategory_add"), {"name": "Registration", "is_active": "on", "order": "1"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("admin:helpdesk_ticketcategory_changelist")), "Registration")
