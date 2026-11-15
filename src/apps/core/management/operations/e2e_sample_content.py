"""Sample admin content for ``seed_admin_e2e``: an unpublished semester, a project in it, and an event with two
ticket types and two questions, each upserted by its natural key so that a second run changes nothing."""

from datetime import date

from apps.event.models import Event, Question, Ticket
from apps.projects.models import Project, Semester

DEFAULT_EVENT_NAME = "E2E Event Copy Template"


class SampleContentMixin:
    def _upsert_sample_semester(self):
        semester, _ = Semester.objects.update_or_create(
            year=2099,
            season=Semester.Season.FALL,
            defaults={"is_published": False},
        )
        return semester

    def _upsert_sample_project(self, semester):
        project, _ = Project.objects.update_or_create(
            semester=semester,
            team_number="E2E-1",
            defaults={
                "class_code": "E2E",
                "team_name": "Admin Browser Team",
                "project_title": "E2E Solar Orchard Dashboard",
                "organization": "Innovate To Grow QA",
                "industry": "Testing",
                "abstract": "Seed project used by browser-driven Django admin tests.",
                "student_names": "Ada Lovelace; Grace Hopper",
                "track": 1,
                "presentation_order": 1,
            },
        )
        return project

    def _upsert_sample_event(self):
        event, _ = Event.objects.update_or_create(
            slug="e2e-event-copy-template",
            defaults={
                "name": DEFAULT_EVENT_NAME,
                "date": date(2099, 5, 14),
                "end_date": date(2099, 5, 16),
                "location": "E2E Event Hall",
                "description": "Seed Event used to verify the safe Add Event copy flow.",
                "registration_open": False,
                "allow_secondary_email": True,
                "collect_phone": True,
                "verify_phone": True,
                "ticket_login_validity_days": 45,
                "ticket_login_reusable": False,
            },
        )
        ticket_templates = {
            "E2E General Admission": {"order": 1},
            "E2E VIP Admission": {"order": 2},
        }
        event.tickets.exclude(name__in=ticket_templates).delete()
        for name, defaults in ticket_templates.items():
            Ticket.objects.update_or_create(event=event, name=name, defaults=defaults)

        question_templates = {
            "What brings you to the E2E Event?": {"is_required": True, "order": 1},
            "Do you need accessibility accommodations?": {"is_required": False, "order": 2},
        }
        event.questions.exclude(text__in=question_templates).delete()
        for text, defaults in question_templates.items():
            Question.objects.update_or_create(event=event, text=text, defaults=defaults)
        return event
