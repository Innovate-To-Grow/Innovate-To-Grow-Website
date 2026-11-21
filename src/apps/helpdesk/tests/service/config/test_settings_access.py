"""Helpdesk → Settings for Helpdesk staff who are not an I2G Master (``admin.intake.sending.SendingFieldsMixin``).

The four settings that decide what the helpdesk sends (shadow mode, the acknowledgement switch and its text, the
assignment notices) are shown read-only in words (On / Off, the text with its line breaks, escaped), and their
sections say only an I2G Master can change them; a POST crafted to change them changes none of them while the other
settings save. The list goes straight to the one row for whoever may see it (it is listed empty while there is no row
and they may not add it), and answers 403 at once (no redirect to the row first) to staff without the Helpdesk app."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ....models import HelpdeskSettings
from ...helpers import helpdesk_staff, make_admin, make_superuser

SENDING = ("shadow_mode", "send_acknowledgement", "acknowledgement_text", "notify_assignment")
MASTER_ONLY = "Only an I2G Master can change these: they decide what the helpdesk sends from the site's address."
TEXT = "Hello <b>Pat</b>,\nwe opened {ticket}."


def readonly(response) -> dict[str, tuple[str, str]]:
    """The read-only rows of the change page: their name, label and what they show."""
    return {
        field.field["name"]: (str(field.field["label"]), str(field.contents()))
        for fieldset in response.context["adminform"]
        for line in fieldset
        for field in line
        if field.is_readonly
    }


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class SendingFieldsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)
        self.row = HelpdeskSettings.objects.create(acknowledgement_text=TEXT)
        self.url = reverse("admin:helpdesk_helpdesksettings_change", args=[self.row.pk])

    def test_they_are_shown_read_only_in_words_with_the_reason(self):
        page = self.client.get(self.url)

        self.assertEqual(
            readonly(page),
            {
                "shadow_mode_shown": ("Shadow mode (nothing is sent)", "On"),
                "send_acknowledgement_shown": ("Send an acknowledgement", "Off"),
                "acknowledgement_text_shown": (
                    "Acknowledgement text",
                    "<div>Hello &lt;b&gt;Pat&lt;/b&gt;,<br>we opened {ticket}.</div>",
                ),
                "notify_assignment_shown": ("Notify staff of assignments", "On"),
            },
        )
        self.assertFalse(set(SENDING) & set(page.context["adminform"].form.fields))
        descriptions = {fieldset.name: fieldset.description for fieldset in page.context["adminform"]}
        self.assertIsNone(descriptions["Switches"])  # its toggles are theirs; shadow mode moved to the sending part
        self.assertEqual(
            descriptions["Sending and notifications"], f"Used only while shadow mode is off. {MASTER_ONLY}"
        )
        self.assertIsNone(descriptions["SLA and automation"])
        self.assertContains(page, "Only an I2G Master can change these", count=1)  # the sending section only

    def test_the_words_follow_the_switches(self):
        HelpdeskSettings.objects.filter(pk=self.row.pk).update(
            shadow_mode=False, send_acknowledgement=True, notify_assignment=False
        )

        shown = readonly(self.client.get(self.url))

        self.assertEqual(
            [shown[f"{name}_shown"][1] for name in ("shadow_mode", "send_acknowledgement", "notify_assignment")],
            ["Off", "On", "Off"],
        )

    def test_a_crafted_post_changes_none_of_them_while_the_rest_saves(self):
        form = self.client.get(self.url).context["adminform"].form
        data = {name: form[name].value() for name in form.fields}
        data = {name: value for name, value in data.items() if value is not None and value is not False}
        data.update(
            shadow_mode="false",
            send_acknowledgement="on",
            acknowledgement_text="Click https://evil.example to keep {ticket}",
            notify_assignment="false",
            sla_warning_percent="60",
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(
            (self.row.shadow_mode, self.row.send_acknowledgement, self.row.notify_assignment), (True, False, True)
        )
        self.assertEqual((self.row.acknowledgement_text, self.row.sla_warning_percent), (TEXT, 60))
        self.assertEqual(LogEntry.objects.get().get_change_message(), "Changed SLA at risk after (% of its time).")

    def test_a_master_gets_the_fields_themselves(self):
        self.client.force_login(make_superuser(email="master@example.com"))

        page = self.client.get(self.url)

        self.assertEqual(readonly(page), {})
        self.assertTrue(set(SENDING) <= set(page.context["adminform"].form.fields))
        self.assertNotContains(page, "Only an I2G Master can change these")


class SettingsListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.row = HelpdeskSettings.objects.create()
        self.list_url = reverse("admin:helpdesk_helpdesksettings_changelist")
        self.change_url = reverse("admin:helpdesk_helpdesksettings_change", args=[self.row.pk])

    def test_staff_without_the_helpdesk_app_get_403_and_no_redirect_to_the_row(self):
        self.client.force_login(make_admin(apps=["mail"], email="mailer@example.com"))

        listed = self.client.get(self.list_url)

        self.assertEqual(listed.status_code, 403)
        self.assertFalse(listed.has_header("Location"))
        self.assertEqual(self.client.get(self.change_url).status_code, 403)

    def test_whoever_may_see_the_settings_goes_straight_to_the_row(self):
        for member in (helpdesk_staff(), make_superuser(email="master@example.com")):
            with self.subTest(member.is_superuser):
                self.client.force_login(member)

                self.assertRedirects(self.client.get(self.list_url), self.change_url)

    def test_without_a_row_someone_who_may_not_add_one_sees_the_empty_list(self):
        HelpdeskSettings.objects.all().delete()
        self.client.force_login(helpdesk_staff())

        with patch.object(type(admin.site._registry[HelpdeskSettings]), "has_add_permission", return_value=False):
            response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [])
