import asyncio

from django.core.cache import cache
from django.test import TransactionTestCase

from apps.event.models import CurrentProject, CurrentProjectSchedule
from apps.projects.models import Project, Semester
from apps.system_intelligence.services import tools as si_tools
from apps.system_intelligence.services.tools.domains import projects as projects_module


class ProjectToolTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.spring = Semester.objects.create(year=2026, season=Semester.Season.SPRING, is_published=True)
        self.fall = Semester.objects.create(year=2026, season=Semester.Season.FALL, is_published=False)
        self.project = Project.objects.create(
            semester=self.spring,
            class_code="CSE",
            team_number="CSE-001",
            team_name="Delta",
            project_title="Campus Navigator",
            organization="UC Merced",
            industry="Education",
        )

    def test_get_project_detail_by_title(self):
        # projects.py lines 57-58: title branch.
        result = asyncio.run(si_tools.get_project_detail(title="Navigator"))
        self.assertEqual(result["project"]["team_number"], "CSE-001")
        self.assertEqual(result["semester"]["year"], 2026)

    def test_get_project_detail_by_team_number(self):
        # projects.py lines 59-60: team_number branch.
        result = asyncio.run(si_tools.get_project_detail(team_number="CSE-001"))
        self.assertEqual(result["project"]["project_title"], "Campus Navigator")

    def test_get_project_detail_without_args_returns_tool_error(self):
        # projects.py line 61: ActionRequestError -> tool error string.
        result = asyncio.run(si_tools.get_project_detail())
        self.assertIn("Provide project_id, title, or team_number", result["result"])

    def test_semester_summary_by_year_and_fall_season(self):
        # projects.py lines 74/76/80-82 + 90/97 via _season_value + _find_semester.
        Project.objects.create(
            semester=self.fall,
            class_code="CSE",
            team_number="CSE-900",
            team_name="Omega",
            project_title="Fall Thing",
            organization="UC Merced",
            industry="Tech",
        )
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season="Fall"))
        self.assertEqual(result["semester"]["season"], Semester.Season.FALL)
        self.assertEqual(result["project_count"], 1)

    def test_semester_summary_season_as_int(self):
        # projects.py line 76: isinstance(season, int) branch returns season directly.
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season=1))
        self.assertEqual(result["semester"]["season"], Semester.Season.SPRING)

    def test_semester_summary_invalid_season_returns_tool_error(self):
        # projects.py line 82: unrecognised season raises ActionRequestError.
        result = asyncio.run(si_tools.get_semester_project_summary(year=2026, season="winter"))
        self.assertIn("season must be Spring, Fall, 1, or 2", result["result"])

    def test_semester_summary_by_id(self):
        # projects.py line 90: semester_id branch.
        result = asyncio.run(si_tools.get_semester_project_summary(semester_id=str(self.spring.pk)))
        self.assertEqual(result["project_count"], 1)

    def test_semester_summary_no_args_picks_latest(self):
        # projects.py line 97: fallback ordering by -year/-season.
        result = asyncio.run(si_tools.get_semester_project_summary())
        self.assertEqual(result["semester"]["year"], 2026)

    def test_current_schedule_by_id(self):
        # projects.py line 123: schedule_id branch.
        schedule = CurrentProjectSchedule.objects.create(name="Showcase", is_active=False)
        CurrentProject.objects.create(
            schedule=schedule,
            class_code="CSE",
            team_number="CSE-001",
            project_title="Live Nav",
            organization="UC Merced",
            is_presenting=True,
        )
        result = asyncio.run(si_tools.get_current_project_schedule(schedule_id=str(schedule.pk)))
        self.assertEqual(result["presenting_count"], 1)

    def test_current_schedule_inactive_fallback(self):
        # projects.py line 127: active_only False -> order_by(-updated_at).
        schedule = CurrentProjectSchedule.objects.create(name="Old", is_active=False)
        result = asyncio.run(si_tools.get_current_project_schedule(active_only=False))
        self.assertEqual(result["schedule"]["id"], str(schedule.pk))

    def test_season_value_none_returns_none(self):
        # projects.py line 74: explicit None short-circuit.
        self.assertIsNone(projects_module._season_value(None))
