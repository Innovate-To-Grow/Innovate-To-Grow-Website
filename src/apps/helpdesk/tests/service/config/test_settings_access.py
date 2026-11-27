"""Helpdesk → Settings: who may change it (``admin.intake.settings`` with ``admin.intake.sending.SendingFieldsMixin``).

Every Admin gets every field, the three that decide what the helpdesk sends (shadow mode, the acknowledgement switch
and its text) included, and saves them like the rest. The deprecated assignment-notice switch is not on the form
(staff get no helpdesk email, I2G-HELPDESK-01) and a save leaves its stored value alone. A member who is not an Admin, or an
Admin whose account is switched off, is sent to the admin sign-in and changes nothing. The list goes straight to the
one row (it is listed empty while there is no row and the Admin may not add it)."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.event.tests.helpers import make_member

from ....models import HelpdeskSettings
from ...helpers import helpdesk_staff, make_admin

SENDING = ("shadow_mode", "send_acknowledgement", "acknowledgement_text")
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

    def form_data(self) -> dict:
        form = self.client.get(self.url).context["adminform"].form
        data = {name: form[name].value() for name in form.fields}
        return {name: value for name, value in data.items() if value is not None and value is not False}

    def test_every_admin_gets_the_sending_fields_themselves(self):
        page = self.client.get(self.url)

        self.assertEqual(readonly(page), {})
        self.assertTrue(set(SENDING) <= set(page.context["adminform"].form.fields))
        self.assertNotIn("notify_assignment", page.context["adminform"].form.fields)
        descriptions = {fieldset.name: fieldset.description for fieldset in page.context["adminform"]}
        self.assertEqual(descriptions["Sending"], "Used only while shadow mode is off.")
        self.assertNotContains(page, "I2G Master")

    def test_an_admin_changes_the_sending_fields_like_the_rest(self):
        data = self.form_data()
        data.pop("shadow_mode", None)
        data.update(
            send_acknowledgement="on",
            acknowledgement_text="Thanks, {ticket} is open.",
            sla_warning_percent="60",
            notify_assignment="",  # posted by a page an earlier release rendered: ignored
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(
            (self.row.shadow_mode, self.row.send_acknowledgement, self.row.notify_assignment), (False, True, True)
        )
        self.assertEqual(
            (self.row.acknowledgement_text, self.row.sla_warning_percent), ("Thanks, {ticket} is open.", 60)
        )
        self.assertTrue(LogEntry.objects.exists())

    def test_a_member_who_is_not_an_admin_changes_nothing(self):
        data = self.form_data()
        data.pop("shadow_mode", None)
        for member in (make_member(email="member@example.com"), make_admin(email="away@example.com", is_active=False)):
            with self.subTest(is_staff=member.is_staff, is_active=member.is_active):
                self.client.force_login(member)

                response = self.client.post(self.url, data)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
        self.row.refresh_from_db()
        self.assertTrue(self.row.shadow_mode)
        self.assertFalse(LogEntry.objects.exists())


class SettingsListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.row = HelpdeskSettings.objects.create()
        self.list_url = reverse("admin:helpdesk_helpdesksettings_changelist")
        self.change_url = reverse("admin:helpdesk_helpdesksettings_change", args=[self.row.pk])

    def test_a_member_who_is_not_an_admin_is_sent_to_the_sign_in(self):
        self.client.force_login(make_member(email="member@example.com"))

        for url in (self.list_url, self.change_url):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_every_admin_goes_straight_to_the_row(self):
        for member in (helpdesk_staff(), make_admin(email="other@example.com")):
            with self.subTest(member=member.pk):
                self.client.force_login(member)

                self.assertRedirects(self.client.get(self.list_url), self.change_url)

    def test_without_a_row_someone_who_may_not_add_one_sees_the_empty_list(self):
        HelpdeskSettings.objects.all().delete()
        self.client.force_login(helpdesk_staff())

        with patch.object(type(admin.site._registry[HelpdeskSettings]), "has_add_permission", return_value=False):
            response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].result_list), [])
