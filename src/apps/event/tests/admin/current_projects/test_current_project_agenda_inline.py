"""The Agenda items inline on the CurrentProjectSchedule change form (the schedule page's Expo and Awards tables)."""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import CurrentProjectSchedule, EventAgendaItem
from apps.event.serializers.schedule import build_schedule_payload
from apps.event.tests.helpers import make_superuser


class _CurrentProjectScheduleAgendaInlineCase(TestCase):
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

    def _formset(self, response):
        return next(
            inline.formset
            for inline in response.context["inline_admin_formsets"]
            if inline.formset.model is EventAgendaItem
        )


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CurrentProjectScheduleAgendaInlineTest(_CurrentProjectScheduleAgendaInlineCase):
    """The Expo / Awards tables are edited on the schedule's change form, not in code."""

    def test_change_form_lists_the_agenda_items(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        inlines = {formset.formset.model: formset.formset for formset in response.context["inline_admin_formsets"]}
        self.assertEqual([form.instance for form in inlines[EventAgendaItem].forms], [self.expo])
        self.assertContains(response, "Registration and Coffee")

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
