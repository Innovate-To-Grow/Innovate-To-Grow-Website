from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import BackgroundJob, InboundMessage
from apps.helpdesk.tests.admin.test_admin_ticket_page import TicketPageTestCase

from ...models import HelpdeskSettings
from ...services.ingest.pipeline import jobs
from .. import corpus
from ..helpers import FakeReader, helpdesk_staff, make_admin, queue, receive


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

    def _settings_form_data(self, settings):
        form = (
            self.client.get(reverse("admin:helpdesk_helpdesksettings_change", args=[settings.pk]))
            .context["adminform"]
            .form
        )
        data = {name: form[name].value() for name in form.fields}
        # Unchecked checkboxes are left out of a real POST.
        return {name: value for name, value in data.items() if value not in (False, None)}, form

    def test_shadow_mode_can_be_switched_off_and_on_and_saving_wakes_the_ingest(self):
        settings = HelpdeskSettings.objects.create()
        queue(corpus.message(), reader=FakeReader())
        data, form = self._settings_form_data(settings)
        data.pop("shadow_mode", None)
        url = reverse("admin:helpdesk_helpdesksettings_change", args=[settings.pk])

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        settings.refresh_from_db()
        self.assertIn("shadow_mode", form.fields)
        self.assertFalse(settings.shadow_mode)
        self.assertTrue(BackgroundJob.objects.filter(kind=jobs.INGEST_JOB_KIND).exists())

        self.client.post(url, {**data, "shadow_mode": "on"})
        settings.refresh_from_db()
        self.assertTrue(settings.shadow_mode)

    def test_categories_are_listed_and_editable(self):
        response = self.client.post(
            reverse("admin:helpdesk_ticketcategory_add"), {"name": "Registration", "is_active": "on", "order": "1"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("admin:helpdesk_ticketcategory_changelist")), "Registration")
