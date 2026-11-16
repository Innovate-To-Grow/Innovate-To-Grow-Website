from django.test import override_settings

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import Event, Question, Ticket
from apps.event.tests.admin.events.test_event_admin_views import _EventAdminCase
from apps.event.tests.helpers import (
    make_event,
)


class EventAdminTest(_EventAdminCase):
    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_confirmation_reviews_final_children_then_saves_new_rows_without_changing_source(self):
        source = make_event(name="Confirmation Copy Source", registration_open=True)
        kept_ticket = Ticket.objects.create(event=source, name="General", order=1)
        deleted_ticket = Ticket.objects.create(event=source, name="Remove VIP", order=2)
        kept_question = Question.objects.create(event=source, text="Role?", is_required=True, order=1)
        deleted_question = Question.objects.create(event=source, text="Remove question?", order=2)
        original_ticket_rows = list(source.tickets.values("pk", "name", "order", "barcode"))
        original_question_rows = list(source.questions.values("pk", "text", "is_required", "order"))
        self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        response = self.client.post(
            f"/admin/event/event/add/?copy_from={source.pk}",
            self._copy_post_data(
                name="Confirmed Event Copy",
                slug="confirmed-event-copy",
                ticket_rows=[
                    {"name": "General Edited", "order": 5},
                    {"name": deleted_ticket.name, "order": deleted_ticket.order, "DELETE": True},
                    {"name": "New Sponsor", "order": 2},
                ],
                question_rows=[
                    {"text": "Role edited?", "is_required": False, "order": 4},
                    {"text": deleted_question.text, "order": deleted_question.order, "DELETE": True},
                    {"text": "New required question?", "is_required": True, "order": 3},
                ],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)
        self.assertFalse(Event.objects.filter(slug="confirmed-event-copy").exists())

        confirmation = self.client.get(response.url)
        self.assertEqual(confirmation.status_code, 200)
        child_diff = {
            item["label"]: item["new_value"]
            for item in confirmation.context["diff"]
            if item["field"].startswith(("tickets", "questions"))
        }
        self.assertEqual(
            child_diff,
            {
                "Ticket type 1": "New Sponsor — order 2",
                "Ticket type 2": "General Edited — order 5",
                "Question 1": "New required question? — required: Yes; order 3",
                "Question 2": "Role edited? — required: No; order 4",
            },
        )
        self.assertNotContains(confirmation, deleted_ticket.name)
        self.assertNotContains(confirmation, deleted_question.text)

        pending = self.client.session["_admin_pending_change_event_event"]
        confirmed = self.client.post(
            response.url,
            {"token": pending["token"], "confirmation_word": "event"},
        )

        self.assertEqual(confirmed.status_code, 302)
        copied = Event.objects.get(slug="confirmed-event-copy")
        self.assertEqual(
            list(copied.tickets.values_list("name", "order")),
            [("New Sponsor", 2), ("General Edited", 5)],
        )
        self.assertEqual(
            list(copied.questions.values_list("text", "is_required", "order")),
            [("New required question?", True, 3), ("Role edited?", False, 4)],
        )
        self.assertNotIn(kept_ticket.pk, copied.tickets.values_list("pk", flat=True))
        self.assertNotIn(kept_ticket.barcode, copied.tickets.values_list("barcode", flat=True))
        self.assertNotIn(kept_question.pk, copied.questions.values_list("pk", flat=True))
        source.refresh_from_db()
        self.assertTrue(source.registration_open)
        self.assertEqual(list(source.tickets.values("pk", "name", "order", "barcode")), original_ticket_rows)
        self.assertEqual(
            list(source.questions.values("pk", "text", "is_required", "order")),
            original_question_rows,
        )

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_confirmation_explicitly_shows_none_for_zero_children(self):
        response = self.client.post(
            "/admin/event/event/add/",
            self._copy_post_data(name="No Children Copy", slug="no-children-copy"),
        )

        self.assertEqual(response.status_code, 302)
        confirmation = self.client.get(response.url)
        child_diff = {
            item["label"]: item["new_value"]
            for item in confirmation.context["diff"]
            if item["field"] in {"tickets", "questions"}
        }
        self.assertEqual(child_diff, {"Ticket types": "None", "Questions": "None"})

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_inline_only_change_to_existing_event_shows_confirmation(self):
        """EventAdmin renders richer inline rows only for adds; on a change the generic inline
        rows are the only inline coverage. An inline-only edit must still produce a diff —
        otherwise the mixin's no-diff short-circuit saved it with no confirmation at all."""
        event = make_event(name="Inline Change Event")
        change_url = f"/admin/event/event/{event.pk}/change/"
        data = scrape_admin_form(
            self.client,
            change_url,
            {
                "tickets-TOTAL_FORMS": "1",
                "tickets-0-name": "Late Bird",
                "tickets-0-order": "1",
            },
        )

        response = self.client.post(change_url, data)

        self.assertEqual(response.status_code, 302)
        self.assertIn("confirm-change", response.url)
        pending = self.client.session["_admin_pending_change_event_event"]
        self.assertIn("tickets-add", [row["field"] for row in pending["diff"]])
        self.assertEqual(event.tickets.count(), 0)

        confirmed = self.client.post(
            response.url,
            {"token": pending["token"], "confirmation_word": "event"},
        )

        self.assertEqual(confirmed.status_code, 302)
        self.assertEqual(event.tickets.count(), 1)
        self.assertEqual(event.tickets.get().name, "Late Bird")

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
    def test_invalid_children_stay_on_add_form_without_pending_confirmation_or_event(self):
        response = self.client.post(
            "/admin/event/event/add/",
            self._copy_post_data(
                name="Invalid Children Copy",
                slug="invalid-children-copy",
                ticket_rows=[{"name": "", "order": 1}],
                question_rows=[{"text": "", "is_required": True, "order": 1}],
            ),
        )

        self.assertEqual(response.status_code, 200)
        inline_formsets = {inline.opts.model: inline.formset for inline in response.context["inline_admin_formsets"]}
        self.assertIn("name", inline_formsets[Ticket].forms[0].errors)
        self.assertIn("text", inline_formsets[Question].forms[0].errors)
        self.assertNotIn("_admin_pending_change_event_event", self.client.session)
        self.assertFalse(Event.objects.filter(slug="invalid-children-copy").exists())
