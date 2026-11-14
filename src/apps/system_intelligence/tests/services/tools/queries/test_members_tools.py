from django.test import TestCase

from apps.system_intelligence.services.query_tools.tool_modules.custom.query import (
    allowed_output_fields,
    is_allowed_query_key,
    validate_output_fields,
)
from apps.system_intelligence.services.query_tools.tool_modules.members import count_members, search_members
from apps.system_intelligence.services.query_tools.tool_modules.projects import search_projects, search_semesters


class MembersToolsTest(TestCase):
    def _make_member(self, first="Jane", last="Doe", org="Acme"):
        from apps.authn.models import Member

        return Member.objects.create(first_name=first, last_name=last, organization=org, is_staff=False)

    def test_search_members_by_name_and_org(self):
        member = self._make_member()
        from apps.authn.models import ContactEmail

        ContactEmail.objects.create(member=member, email_address="jane@acme.com", email_type="primary")
        result = search_members(
            {
                "name": "Jane Doe",
                "email": "jane@acme",
                "organization": "Acme",
                "is_staff": False,
                "is_active": True,
            }
        )
        self.assertIn("Jane", result)

    def test_count_members(self):
        self._make_member()
        self._make_member(first="Bob", org="Beta")
        result = count_members({"is_staff": False, "is_active": True, "organization": "Acme"})
        self.assertEqual(result, "Count: 1")


class ProjectsToolsTest(TestCase):
    def _make_project(self):
        from apps.projects.models import Project, Semester

        semester = Semester.objects.create(year=2025, season=1, is_published=True, label="Spring 2025")
        return Project.objects.create(
            project_title="Smart Garden",
            team_name="Green Team",
            team_number=3,
            class_code="ENGR101",
            organization="Acme",
            industry="AgTech",
            semester=semester,
        )

    def test_search_projects_all_filters(self):
        self._make_project()
        result = search_projects(
            {
                "title": "Smart",
                "team_name": "Green",
                "organization": "Acme",
                "industry": "AgTech",
                "semester": "Spring",
                "class_code": "ENGR",
            }
        )
        self.assertIn("Smart Garden", result)

    def test_search_semesters(self):
        from apps.projects.models import Semester

        Semester.objects.create(year=2025, season=1, is_published=True, label="Spring 2025")
        result = search_semesters({"year": 2025, "season": "1", "is_published": True})
        self.assertIn("2025", result)


class CustomQueryKeyTest(TestCase):
    def test_too_many_parts_rejected(self):
        self.assertFalse(is_allowed_query_key("Semester", "year__gte__extra"))

    def test_field_not_in_allowlist_rejected(self):
        self.assertFalse(is_allowed_query_key("Semester", "secret_field"))

    def test_unsafe_lookup_rejected(self):
        self.assertFalse(is_allowed_query_key("Semester", "year__regex"))

    def test_valid_field_and_lookup_accepted(self):
        self.assertTrue(is_allowed_query_key("Semester", "year__gte"))
        self.assertTrue(is_allowed_query_key("Semester", "-year"))

    def test_allowed_output_fields_sorted(self):
        fields = allowed_output_fields("Semester")
        self.assertEqual(fields, sorted(fields))

    def test_event_allowlist_exposes_date_range_without_legacy_live_flag(self):
        fields = allowed_output_fields("Event")

        self.assertIn("date", fields)
        self.assertIn("end_date", fields)
        self.assertNotIn("is_live", fields)

    def test_validate_output_fields_invalid(self):
        msg = validate_output_fields("Semester", ["year", "nope"])
        self.assertIn("field 'nope' is not allowed", msg)

    def test_validate_output_fields_valid(self):
        self.assertEqual(validate_output_fields("Semester", ["year"]), "")
