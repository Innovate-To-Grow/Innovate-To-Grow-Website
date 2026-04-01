from django.test import TestCase

from projects.models import Project, Semester


class SemesterModelTest(TestCase):
    def test_str_returns_label(self):
        sem = Semester.objects.create(year=2025, season=Semester.Season.SPRING)
        self.assertEqual(str(sem), "2025-1 Spring")

    def test_label_auto_generated_on_save(self):
        sem = Semester.objects.create(year=2025, season=Semester.Season.FALL)
        self.assertEqual(sem.label, "2025-2 Fall")

    def test_is_current_forces_is_published(self):
        sem = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_current=True, is_published=False)
        self.assertTrue(sem.is_published)

    def test_is_current_clears_other_semesters(self):
        sem1 = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_current=True)
        sem2 = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_current=True)
        sem1.refresh_from_db()
        self.assertFalse(sem1.is_current)
        self.assertTrue(sem2.is_current)

    def test_ordering_by_year_desc_season_desc(self):
        s1 = Semester.objects.create(year=2024, season=Semester.Season.SPRING)
        s2 = Semester.objects.create(year=2025, season=Semester.Season.FALL)
        s3 = Semester.objects.create(year=2025, season=Semester.Season.SPRING)
        self.assertEqual(list(Semester.objects.all()), [s2, s3, s1])

    def test_season_choices(self):
        self.assertEqual(Semester.Season.SPRING, 1)
        self.assertEqual(Semester.Season.FALL, 2)

    def test_current_pk_subquery_returns_current(self):
        Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)
        current = Semester.objects.create(year=2025, season=Semester.Season.SPRING, is_current=True, is_published=True)
        qs = Semester.current_pk_subquery()
        self.assertEqual(list(qs), [{"pk": current.pk}])


class ProjectModelTest(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(year=2025, season=Semester.Season.SPRING)

    def test_str_with_team_number(self):
        project = Project.objects.create(semester=self.semester, project_title="AI Research", team_number="5")
        self.assertEqual(str(project), "Team 5 - AI Research")

    def test_str_without_team_number(self):
        project = Project.objects.create(semester=self.semester, project_title="Solo Project")
        self.assertEqual(str(project), "Solo Project")

    def test_str_truncates_long_title(self):
        title = "A" * 100
        project = Project.objects.create(semester=self.semester, project_title=title)
        self.assertEqual(str(project), title[:60])

    def test_soft_delete(self):
        project = Project.objects.create(semester=self.semester, project_title="Test")
        project.delete()
        self.assertEqual(Project.objects.count(), 0)
        self.assertEqual(Project.all_objects.count(), 1)

    def test_blank_field_defaults(self):
        project = Project.objects.create(semester=self.semester, project_title="Test")
        self.assertEqual(project.class_code, "")
        self.assertEqual(project.team_number, "")
        self.assertEqual(project.team_name, "")
        self.assertEqual(project.organization, "")
        self.assertEqual(project.abstract, "")
