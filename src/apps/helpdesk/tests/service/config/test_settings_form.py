"""Helpdesk → Settings, the form an Admin saves (``admin.intake.sending.SettingsForm``): the settings carry the
labels of ``LABELS``; the acknowledgement text is stored with LF line ends (a browser posts a textarea with CRLF) and
may use only the known placeholders ({ticket}, and {requester_name} or {subject}, which lose any link)."""

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from ....admin.intake.sending import LABELS
from ....models import HelpdeskSettings
from ....models.settings import DEFAULT_ACKNOWLEDGEMENT
from ...helpers import helpdesk_staff

USE = "Use {ticket} (and {requester_name} or {subject}, which lose any link)."
CHANGE_SESSION_KEY = "_admin_pending_change_helpdesk_helpdesksettings"


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SettingsFormTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = helpdesk_staff()
        self.client.force_login(self.admin)
        self.row = HelpdeskSettings.objects.create()
        self.url = reverse("admin:helpdesk_helpdesksettings_change", args=[self.row.pk])

    def page_data(self, **values) -> dict:
        """What the change page posts back as a browser does: its textareas with CRLF line ends, an unticked box left
        out; then ``values``."""
        form = self.client.get(self.url).context["adminform"].form
        data = {name: form[name].value() for name in form.fields}
        data = {name: value for name, value in data.items() if value is not None and value is not False}
        data["acknowledgement_text"] = data["acknowledgement_text"].replace("\n", "\r\n")
        return {**data, **values}

    def bound_form(self, data):
        request = RequestFactory().post(self.url)
        request.user = self.admin
        return admin.site._registry[HelpdeskSettings].get_form(request, self.row, change=True)(data, instance=self.row)

    def test_the_settings_carry_their_labels(self):
        page = self.client.get(self.url)

        form = page.context["adminform"].form
        self.assertEqual({name: form.fields[name].label for name in LABELS}, LABELS)
        self.assertContains(page, "Shadow mode (nothing is sent)")
        self.assertContains(page, "SLA at risk after (% of its time)")

    def test_a_text_posted_with_crlf_line_ends_is_stored_with_lf(self):
        response = self.client.post(self.url, self.page_data(sla_warning_percent="60"))

        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual((self.row.acknowledgement_text, self.row.sla_warning_percent), (DEFAULT_ACKNOWLEDGEMENT, 60))

    def test_an_untouched_text_posted_with_crlf_line_ends_is_no_change(self):
        # Neither in the form's changed fields nor in the history or the typed confirmation's diff.
        form = self.bound_form(self.page_data(sla_warning_percent="60"))

        self.assertTrue(form.is_valid())
        self.assertEqual(form.changed_data, ["sla_warning_percent"])
        self.client.post(self.url, self.page_data(sla_warning_percent="60"))
        self.assertEqual(LogEntry.objects.get().get_change_message(), "Changed SLA at risk after (% of its time).")
        with self.settings(ADMIN_REQUIRE_CONFIRMATION=True):
            unchanged = self.client.post(self.url, self.page_data(sla_warning_percent="60"))
            changed = self.client.post(self.url, self.page_data(sla_warning_percent="50"))
            diff = self.client.session[CHANGE_SESSION_KEY]["diff"]
        # Nothing changed: saved at once, without the confirmation page; a change lists only what changed.
        self.assertRedirects(
            unchanged, reverse("admin:helpdesk_helpdesksettings_changelist"), fetch_redirect_response=False
        )
        self.assertIn("confirm-change", changed["Location"])
        self.assertEqual([row["field"] for row in diff], ["sla_warning_percent"])

    def test_an_unknown_placeholder_is_refused(self):
        cases = {
            "Hello {name}, ticket {ticket}.": f"Unknown placeholder: {{name}}. {USE}",
            "{link} and {name} and {link}": f"Unknown placeholders: {{link}}, {{name}}. {USE}",
        }
        for text, error in cases.items():
            with self.subTest(text):
                response = self.client.post(self.url, self.page_data(acknowledgement_text=text))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["adminform"].form.errors["acknowledgement_text"], [error])
        self.row.refresh_from_db()
        self.assertEqual(self.row.acknowledgement_text, DEFAULT_ACKNOWLEDGEMENT)

    def test_the_known_placeholders_and_plain_braces_are_accepted(self):
        text = "Hello {requester_name},\r\nwe have {subject} as {ticket}. {Nothing here is replaced}"

        response = self.client.post(self.url, self.page_data(acknowledgement_text=text))

        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.acknowledgement_text, text.replace("\r\n", "\n"))
