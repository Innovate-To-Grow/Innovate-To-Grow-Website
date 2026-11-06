from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.admin.current_project.admin import SHEET_LINK_FIELD, CurrentProjectScheduleAdmin, google_sheet_url
from apps.event.models import CurrentProjectSchedule
from apps.event.tests.helpers import make_superuser

SHEET_ID = "1AbC-dEf_GhIjK"
BUTTON_TEXT = "Open Google Sheet"
BUTTON_OPENING_TAG = (
    f'<a class="i2g-admin-action" href="https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit" '
    'target="_blank" rel="noopener noreferrer">'
)


class CurrentProjectScheduleSheetLinkTest(TestCase):
    """The change form's Open Google Sheet button: under the Sheet ID of a saved row that has one, else absent."""

    def setUp(self):
        cache.clear()
        make_superuser(email="schedule-admin@example.com")
        self.client.login(username="schedule-admin@example.com", password="testpass123")

    @staticmethod
    def change_url(schedule):
        return reverse("admin:event_currentprojectschedule_change", args=[schedule.pk])

    def test_saved_row_with_a_sheet_id_links_the_sheet_under_the_id_field(self):
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", sheet_id=SHEET_ID)

        response = self.client.get(self.change_url(schedule))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(BUTTON_OPENING_TAG, html)
        self.assertEqual(html.count(BUTTON_TEXT), 1)
        # In the Google Sheet Source fieldset: after the Sheet ID input, before the worksheet GIDs.
        self.assertLess(html.index('name="sheet_id"'), html.index(BUTTON_TEXT))
        self.assertLess(html.index(BUTTON_TEXT), html.index('name="tracks_gid"'))

    def test_saved_row_without_a_sheet_id_shows_no_button(self):
        for sheet_id in ("", "   "):
            with self.subTest(sheet_id=repr(sheet_id)):
                schedule = CurrentProjectSchedule.objects.create(
                    name=f"Row {len(sheet_id)}", is_active=False, sheet_id=sheet_id
                )

                response = self.client.get(self.change_url(schedule))

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, BUTTON_TEXT)
                self.assertNotContains(response, "docs.google.com/spreadsheets")

    def test_add_form_shows_no_button(self):
        response = self.client.get(reverse("admin:event_currentprojectschedule_add"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, BUTTON_TEXT)
        self.assertNotContains(response, "docs.google.com/spreadsheets")

    def test_fieldsets_gain_the_link_only_for_a_saved_row_with_a_sheet(self):
        model_admin = CurrentProjectScheduleAdmin(CurrentProjectSchedule, admin.site)
        request = RequestFactory().get("/")
        saved = CurrentProjectSchedule.objects.create(name="Saved", sheet_id=SHEET_ID)
        unsaved = CurrentProjectSchedule(name="Unsaved", sheet_id=SHEET_ID)

        def fields(obj):
            return [field for _, options in model_admin.get_fieldsets(request, obj) for field in options["fields"]]

        self.assertEqual(fields(saved).index(SHEET_LINK_FIELD), fields(saved).index("sheet_id") + 1)
        self.assertNotIn(SHEET_LINK_FIELD, fields(None))
        self.assertNotIn(SHEET_LINK_FIELD, fields(unsaved))
        self.assertEqual(fields(None), fields(unsaved))

    def test_sheet_url_quotes_the_id(self):
        self.assertEqual(google_sheet_url(SHEET_ID), f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
        self.assertEqual(google_sheet_url("a b/c?d"), "https://docs.google.com/spreadsheets/d/a%20b%2Fc%3Fd/edit")
