"""The Agenda items inline on the CurrentProjectSchedule change form (the schedule page's Expo and Awards tables)."""

from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import CurrentProjectSchedule, EventAgendaItem
from apps.event.serializers.schedule import build_schedule_payload
from apps.event.tests.helpers import make_admin, make_superuser


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CurrentProjectScheduleAgendaInlineTest(TestCase):
    """The Expo / Awards tables are edited on the schedule's change form, not in code."""

    def setUp(self):
        cache.clear()
        make_superuser(email="agenda-admin@example.com")
        self.client.login(username="agenda-admin@example.com", password="testpass123")
        self.config = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        self.expo = EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.EXPO,
            time_label="9:00",
            title="Registration and Coffee",
            location="Gym",
            display_order=0,
        )
        self.url = reverse("admin:event_currentprojectschedule_change", args=[self.config.pk])

    def test_change_form_lists_the_agenda_items(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        inlines = {formset.formset.model: formset.formset for formset in response.context["inline_admin_formsets"]}
        self.assertEqual([form.instance for form in inlines[EventAgendaItem].forms], [self.expo])
        self.assertContains(response, "Registration and Coffee")

    def _expo_row(self, title, order, time="10:00"):
        return EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.EXPO,
            time_label=time,
            title=title,
            location="Gym",
            display_order=order,
        )

    def _new_row_data(self, index, **fields):
        row = {
            "section_type": EventAgendaItem.SectionType.EXPO,
            "display_order": "0",
            "time_label": "",
            "title": "",
            "location": "Gym",
            **fields,
        }
        data = {f"agenda_items-{index}-{name}": value for name, value in row.items()}
        data[f"agenda_items-{index}-id"] = ""
        data[f"agenda_items-{index}-config"] = str(self.config.pk)
        return data

    def _titles(self, section_type=EventAgendaItem.SectionType.EXPO):
        rows = EventAgendaItem.objects.filter(config=self.config, section_type=section_type).order_by("display_order")
        return list(rows.values_list("title", flat=True))

    def test_editing_a_row_updates_what_the_public_schedule_serves(self):
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-title": "Check-in", "agenda_items-0-location": "Student Union"},
        )
        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        expo = build_schedule_payload(CurrentProjectSchedule.objects.get(pk=self.config.pk))["expo"]
        self.assertEqual(expo["location"], "Student Union")
        self.assertEqual([item["title"] for item in expo["items"]], ["Check-in"])

    def test_adding_a_row(self):
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(
            self._new_row_data(
                1,
                section_type=EventAgendaItem.SectionType.AWARDS,
                time_label="4:45",
                title="Award Ceremony",
            )
        )

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        added = EventAgendaItem.objects.get(config=self.config, title="Award Ceremony")
        self.assertEqual(added.section_type, EventAgendaItem.SectionType.AWARDS)

    def _formset(self, response):
        return next(
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.model is EventAgendaItem
        )

    def test_a_new_row_is_blank_until_it_is_appended(self):
        response = self.client.get(self.url)

        self.assertIsNone(self._formset(response).empty_form["display_order"].value())

    def test_rows_left_blank_are_appended_in_the_order_they_were_entered(self):
        self._expo_row("Lunch", 4)
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "4"
        data.update(self._new_row_data(2, display_order="", time_label="1:00", title="First new"))
        data.update(self._new_row_data(3, display_order="", time_label="2:00", title="Second new"))

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee", "Lunch", "First new", "Second new"])
        orders = EventAgendaItem.objects.filter(config=self.config).order_by("display_order")
        self.assertEqual(list(orders.values_list("display_order", flat=True)), [0, 4, 5, 6])

    def test_a_blank_row_goes_after_an_explicit_one_entered_in_the_same_save(self):
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "3"
        data.update(self._new_row_data(1, display_order="20", time_label="1:00", title="Explicit"))
        data.update(self._new_row_data(2, display_order="", time_label="2:00", title="Blank"))

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(self._titles(), ["Registration and Coffee", "Explicit", "Blank"])

    def test_untouched_extra_rows_are_ignored(self):
        data = scrape_admin_form(self.client, self.url)
        data["agenda_items-TOTAL_FORMS"] = "2"
        data.update(self._new_row_data(1, display_order="", section_type="", location=""))

        self.assertEqual(self.client.post(self.url, data).status_code, 302)

        self.assertEqual(EventAgendaItem.objects.filter(config=self.config).count(), 1)

    def test_swapping_two_rows_in_one_save(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-display_order": "1", "agenda_items-1-display_order": "0"},
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._titles(), ["Expo - Posters - Demos - Lunch", "Registration and Coffee"])

    def test_inserting_a_row_at_the_top_while_shifting_the_others_down(self):
        self._expo_row("Expo - Posters - Demos - Lunch", 1)
        data = scrape_admin_form(
            self.client,
            self.url,
            overrides={"agenda_items-0-display_order": "1", "agenda_items-1-display_order": "2"},
        )
        data["agenda_items-TOTAL_FORMS"] = "3"
        data.update(self._new_row_data(2, time_label="8:30", title="Doors open", display_order="0"))

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._titles(), ["Doors open", "Registration and Coffee", "Expo - Posters - Demos - Lunch"])

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

    def test_inline_follows_the_event_app_access_rule(self):
        from apps.event.admin.current_project.admin import EventAgendaItemInline

        inline = EventAgendaItemInline(CurrentProjectSchedule, admin.site)
        request = RequestFactory().get("/admin/")
        permissions = ("has_view_permission", "has_add_permission", "has_change_permission", "has_delete_permission")

        request.user = make_admin(apps=["event"], email="event-staff@example.com")
        for permission in permissions:
            self.assertTrue(getattr(inline, permission)(request), permission)

        request.user = make_admin(apps=["cms"], email="cms-staff@example.com")
        for permission in permissions:
            self.assertFalse(getattr(inline, permission)(request), permission)
