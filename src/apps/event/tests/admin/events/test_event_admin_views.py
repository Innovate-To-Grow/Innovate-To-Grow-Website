from django.test import TestCase

from apps.event.models import CheckIn, Event, Question, Ticket
from apps.event.services import build_event_copy_template
from apps.event.tests.helpers import (
    make_event,
    make_superuser,
)


class _EventAdminCase(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @staticmethod
    def _copy_post_data(*, name, slug, ticket_rows=(), question_rows=(), **overrides):
        data = {
            "name": name,
            "slug": slug,
            "date": "2026-10-01",
            "end_date": "2026-10-03",
            "location": "Copied Hall",
            "description": "Reviewed copied Event.",
            "ticket_login_validity_days": "30",
            "ticket_login_reusable": "on",
            "registration_sheet_id": "",
            "registration_sheet_gid": "",
            "tickets-TOTAL_FORMS": str(len(ticket_rows)),
            "tickets-INITIAL_FORMS": "0",
            "tickets-MIN_NUM_FORMS": "0",
            "tickets-MAX_NUM_FORMS": "1000",
            "questions-TOTAL_FORMS": str(len(question_rows)),
            "questions-INITIAL_FORMS": "0",
            "questions-MIN_NUM_FORMS": "0",
            "questions-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        for index, row in enumerate(ticket_rows):
            data[f"tickets-{index}-name"] = row["name"]
            data[f"tickets-{index}-order"] = str(row["order"])
            if row.get("DELETE"):
                data[f"tickets-{index}-DELETE"] = "on"
        for index, row in enumerate(question_rows):
            data[f"questions-{index}-text"] = row["text"]
            data[f"questions-{index}-order"] = str(row["order"])
            if row.get("is_required"):
                data[f"questions-{index}-is_required"] = "on"
            if row.get("DELETE"):
                data[f"questions-{index}-DELETE"] = "on"
        data.update(overrides)
        return data


class EventAdminTest(_EventAdminCase):
    def test_changelist_accessible(self):
        response = self.client.get("/admin/event/event/")
        self.assertEqual(response.status_code, 200)

    def test_add_form_accessible(self):
        response = self.client.get("/admin/event/event/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copy from existing Event")
        self.assertContains(response, "event/js/event_admin.js")
        self.assertContains(response, "event/css/event_admin.css")
        self.assertContains(response, "Phone Number")
        self.assertContains(response, "Secondary Email")
        self.assertContains(response, "Verify if provided")
        self.assertContains(response, 'id="event-copy-source-hint"')
        self.assertContains(response, 'aria-describedby="event-copy-source-hint"')
        self.assertContains(response, 'aria-hidden="true"')
        self.assertContains(response, 'id="event-phone-dependency-hint"')
        self.assertContains(response, "event-phone-dependency-hint", count=3)
        self.assertContains(response, "event-secondary-email-dependency-hint", count=3)

    def test_copy_template_builder_returns_ordered_safe_snapshot(self):
        source = make_event(
            name="Builder Source",
            registration_open=True,
            registration_sheet_id="private-source-sheet",
            registration_sheet_gid=72,
        )
        later_ticket = Ticket.objects.create(event=source, name="VIP", order=20)
        first_ticket = Ticket.objects.create(event=source, name="General", order=10)
        later_question = Question.objects.create(event=source, text="Dietary needs?", order=9)
        first_question = Question.objects.create(event=source, text="Role?", is_required=True, order=2)

        template = build_event_copy_template(source)

        self.assertEqual(template.source_id, source.pk)
        self.assertEqual(template.source_name, source.name)
        self.assertEqual(template.event_initial["name"], "")
        self.assertEqual(template.event_initial["slug"], "")
        self.assertFalse(template.event_initial["registration_open"])
        self.assertEqual(template.event_initial["registration_sheet_id"], "")
        self.assertIsNone(template.event_initial["registration_sheet_gid"])
        self.assertEqual(
            template.ticket_initial(),
            [
                {"name": first_ticket.name, "order": 10},
                {"name": later_ticket.name, "order": 20},
            ],
        )
        self.assertEqual(
            template.question_initial(),
            [
                {"text": first_question.text, "is_required": True, "order": 2},
                {"text": later_question.text, "is_required": False, "order": 9},
            ],
        )
        self.assertNotIn("barcode", template.ticket_initial()[0])

    def test_add_form_loads_safe_copy_source_without_creating_event(self):
        source = make_event(
            name="Source Event",
            date="2026-05-14",
            end_date="2026-05-16",
            location="Source Hall",
            description="Reusable source description.",
            registration_open=True,
            allow_secondary_email=True,
            collect_phone=True,
            verify_phone=True,
            require_phone=True,
            verify_secondary_email=True,
            require_secondary_email=True,
            ticket_login_validity_days=45,
            ticket_login_reusable=False,
            registration_sheet_id="source-sheet",
            registration_sheet_gid=987,
            registration_sheet_sync_count=22,
            registration_sheet_sync_error="old error",
        )
        source_ticket = Ticket.objects.create(event=source, name="VIP", order=3)
        source_question = Question.objects.create(event=source, text="Why attend?", is_required=True, order=4)
        CheckIn.objects.create(event=source, name="Source entrance")
        original_count = Event.objects.count()

        response = self.client.get(f"/admin/event/event/add/?copy_from={source.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), original_count)
        self.assertContains(response, "Loaded safe template data from")
        self.assertContains(response, "<strong>Source Event</strong>", html=True)
        self.assertContains(response, "Source Event — May 14–16, 2026")
        self.assertContains(response, 'href="#tickets-group"')
        self.assertContains(response, 'href="#questions-group"')
        initial = response.context["adminform"].form.initial
        self.assertEqual(initial["name"], "")
        self.assertEqual(initial["slug"], "")
        self.assertEqual(str(initial["date"]), "2026-05-14")
        self.assertEqual(str(initial["end_date"]), "2026-05-16")
        self.assertEqual(initial["location"], "Source Hall")
        self.assertFalse(initial["registration_open"])
        self.assertTrue(initial["allow_secondary_email"])
        self.assertTrue(initial["collect_phone"])
        self.assertTrue(initial["verify_phone"])
        self.assertTrue(initial["require_phone"])
        self.assertTrue(initial["verify_secondary_email"])
        self.assertTrue(initial["require_secondary_email"])
        self.assertEqual(initial["ticket_login_validity_days"], 45)
        self.assertFalse(initial["ticket_login_reusable"])
        self.assertEqual(initial["registration_sheet_id"], "")
        self.assertIsNone(initial["registration_sheet_gid"])

        inline_forms = {inline.opts.model: inline.formset.forms for inline in response.context["inline_admin_formsets"]}
        self.assertEqual(inline_forms[Ticket][0].initial, {"name": "VIP", "order": 3})
        self.assertEqual(
            inline_forms[Question][0].initial,
            {"text": "Why attend?", "is_required": True, "order": 4},
        )
        source_ticket.refresh_from_db()
        source_question.refresh_from_db()
