from django.contrib import admin
from django.test import RequestFactory, override_settings
from django.urls import reverse

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import CurrentProjectSchedule, EventAgendaItem
from apps.event.tests.admin.current_projects.test_current_project_agenda_inline import (
    _CurrentProjectScheduleAgendaInlineCase,
)
from apps.event.tests.helpers import make_admin, make_member


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CurrentProjectScheduleAgendaInlineTest(_CurrentProjectScheduleAgendaInlineCase):
    def test_an_oversized_display_order_is_rejected(self):
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-display_order": "10000"})

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use a number up to 9999.")
        self.expo.refresh_from_db()
        self.assertEqual(self.expo.display_order, 0)

    def test_the_add_form_creates_a_schedule_together_with_its_agenda(self):
        add_url = reverse("admin:event_currentprojectschedule_add")
        data = scrape_admin_form(self.client, add_url, overrides={"name": "Innovate to Grow 2027"})
        created = CurrentProjectSchedule.objects.exclude(pk=self.config.pk)
        self.assertFalse(created.exists())
        data.update(
            {
                "agenda_items-TOTAL_FORMS": "1",
                "agenda_items-0-id": "",
                "agenda_items-0-section_type": EventAgendaItem.SectionType.EXPO,
                "agenda_items-0-display_order": "0",
                "agenda_items-0-time_label": "9:00",
                "agenda_items-0-title": "Doors open",
                "agenda_items-0-location": "Gym",
            }
        )

        response = self.client.post(add_url, data)

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        schedule = created.get()
        self.assertEqual(list(schedule.agenda_items.values_list("title", flat=True)), ["Doors open"])

    def test_deleting_a_row(self):
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-DELETE": "on"})

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertFalse(EventAgendaItem.objects.filter(config=self.config).exists())

    def test_the_empty_form_offers_a_blank_table_choice_so_untouched_rows_are_ignored(self):
        formset = self._formset(self.client.get(self.url))

        empty_choices = formset.empty_form.fields["section_type"].choices
        self.assertEqual(empty_choices[0], ("", "---------"))
        self.assertEqual([value for value, _ in empty_choices].count(""), 1)
        self.assertNotIn("", [value for value, _ in formset.forms[0].fields["section_type"].choices])

    def test_a_row_marked_for_deletion_is_not_blamed_for_a_duplicate_order(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-1-DELETE": "on", "agenda_items-0-display_order": "1"},
        )
        data["agenda_items-TOTAL_FORMS"] = "3"
        data.update(self._new_row_data(2, display_order="", time_label="1:00", title=""))  # unrelated error: no title

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "share a display order")
        self.assertNotContains(response, "Please correct the duplicate")

    def test_swapping_rows_while_someone_else_adds_a_row_above_them(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-display_order": "1", "agenda_items-1-display_order": "0"},
        )
        self._expo_row("Added by another editor", 2)

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(
            self._titles(),
            ["Expo - Posters - Demos - Lunch", "Registration and Coffee", "Added by another editor"],
        )

    def test_a_row_at_a_huge_order_does_not_get_in_the_way_of_reordering(self):
        self._expo_row("Legacy row", 1_000_000)
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-display_order": "3"})

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee", "Legacy row"])

    def test_moving_a_row_to_the_other_table_onto_an_order_saved_by_someone_else_is_reported(self):
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-section_type": EventAgendaItem.SectionType.AWARDS},
        )
        EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.AWARDS,
            time_label="4:45",
            title="Added by another editor",
            display_order=0,
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Another row of this table already uses this display order.")
        self.expo.refresh_from_db()
        self.assertEqual(self.expo.section_type, EventAgendaItem.SectionType.EXPO)

    def test_an_order_saved_by_someone_else_in_the_other_table_is_not_a_clash(self):
        data = scrape_admin_form(self.client, self.url)
        EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.AWARDS,
            time_label="4:45",
            title="Added by another editor",
            display_order=1,
        )
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(self._new_row_data(1, display_order="1", time_label="1:00", title="Mine"))

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee", "Mine"])

    def test_a_blank_row_is_appended_after_rows_saved_by_someone_else(self):
        data = scrape_admin_form(self.client, self.url)
        self._expo_row("Added by another editor", 5)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(self._new_row_data(1, display_order="", time_label="1:00", title="Mine"))

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee", "Added by another editor", "Mine"])

    def test_inline_follows_the_admin_rule(self):
        from apps.event.admin.schedule.agenda import EventAgendaItemInline

        inline = EventAgendaItemInline(CurrentProjectSchedule, admin.site)
        request = RequestFactory().get("/admin/")
        permissions = ("has_view_permission", "has_add_permission", "has_change_permission", "has_delete_permission")

        request.user = make_admin(email="event-staff@example.com")
        for permission in permissions:
            self.assertTrue(getattr(inline, permission)(request), permission)

        request.user = make_member(email="plain-agenda@example.com")
        for permission in permissions:
            self.assertFalse(getattr(inline, permission)(request), permission)
