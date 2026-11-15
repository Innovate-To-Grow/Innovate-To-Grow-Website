from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import CurrentProjectSchedule, EventAgendaItem
from apps.event.tests.admin.current_projects.test_current_project_agenda_inline import (
    _CurrentProjectScheduleAgendaInlineCase,
)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CurrentProjectScheduleAgendaInlineTest(_CurrentProjectScheduleAgendaInlineCase):
    def test_a_deleted_rows_order_can_be_reused_in_the_same_save(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-DELETE": "on", "agenda_items-1-display_order": "0"},
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._titles(), ["Expo - Posters - Demos - Lunch"])
        self.assertEqual(EventAgendaItem.objects.get(config=self.config).display_order, 0)

    def test_deleting_the_second_row_while_the_first_takes_its_order(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-1-DELETE": "on", "agenda_items-0-display_order": "1"},
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee"])
        self.assertEqual(EventAgendaItem.objects.get(config=self.config).display_order, 1)

    def test_a_row_can_jump_past_the_end_while_another_takes_the_front(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-display_order": "3", "agenda_items-1-display_order": "0"},
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Expo - Posters - Demos - Lunch", "Registration and Coffee"])

    def test_two_rows_can_trade_tables_in_one_save(self):
        awards = EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.AWARDS,
            time_label="4:45",
            title="Award Ceremony",
            display_order=0,
        )
        # The inline lists Awards before Expo, so index 0 is the awards row and index 1 the expo row.
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={
                "agenda_items-0-section_type": EventAgendaItem.SectionType.EXPO,
                "agenda_items-1-section_type": EventAgendaItem.SectionType.AWARDS,
            },
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        awards.refresh_from_db()
        self.expo.refresh_from_db()
        self.assertEqual(awards.section_type, EventAgendaItem.SectionType.EXPO)
        self.assertEqual(self.expo.section_type, EventAgendaItem.SectionType.AWARDS)

    def test_a_title_edit_does_not_rewrite_display_orders(self):
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-title": "Check-in"})

        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertFalse(
            [q["sql"] for q in queries if q["sql"].startswith("UPDATE") and '"display_order" + ' in q["sql"]]
        )

    def test_rendering_the_form_runs_no_ordering_aggregate(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.client.get(self.url).status_code, 200)

        self.assertFalse([q["sql"] for q in queries if "MAX(" in q["sql"] and "display_order" in q["sql"]])

    def test_a_row_saved_by_someone_else_in_the_meantime_is_reported_not_a_server_error(self):
        data = scrape_admin_form(self.client, self.url)  # this editor's page was loaded with one row
        self._expo_row("Added by another editor", 7)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(self._new_row_data(1, display_order="7", time_label="1:00", title="Mine"))

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Another row of this table already uses this display order.")
        self.assertFalse(EventAgendaItem.objects.filter(title="Mine").exists())

    def test_moving_a_row_onto_an_order_saved_by_someone_else_is_reported(self):
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-display_order": "7"})
        self._expo_row("Added by another editor", 7)

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Another row of this table already uses this display order.")
        self.expo.refresh_from_db()
        self.assertEqual(self.expo.display_order, 0)

    def test_a_row_above_the_cap_stays_editable_while_it_is_left_alone(self):
        self.expo.display_order = 20000
        self.expo.save()
        data = scrape_admin_form(self.client, self.url, overrides={"agenda_items-0-title": "Check-in"})

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.expo.refresh_from_db()
        self.assertEqual((self.expo.title, self.expo.display_order), ("Check-in", 20000))

    def test_a_reorder_does_not_disturb_rows_of_other_schedules(self):
        other = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        untouched = EventAgendaItem.objects.create(
            config=other,
            section_type=EventAgendaItem.SectionType.EXPO,
            time_label="9:00",
            title="Welcome",
            display_order=0,
        )
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-display_order": "1", "agenda_items-1-display_order": "0"},
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        untouched.refresh_from_db()
        self.assertEqual(untouched.display_order, 0)

    def test_a_duplicate_row_order_within_a_table_is_rejected(self):
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(self._new_row_data(1, time_label="9:30", title="Welcome", display_order="0"))

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Two rows of the same table share a display order.")
        self.assertFalse(EventAgendaItem.objects.filter(title="Welcome").exists())

    def test_the_same_order_in_the_other_table_is_fine(self):
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(
            self._new_row_data(
                1,
                section_type=EventAgendaItem.SectionType.AWARDS,
                time_label="4:45",
                title="Award Ceremony",
                display_order="0",
            )
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(EventAgendaItem.SectionType.AWARDS), ["Award Ceremony"])
