from django.core.cache import cache
from django.test import TestCase

from apps.projects.models import Project, Semester
from apps.projects.signals import PROJECT_ARCHIVE_VERSION_KEY


# noinspection DuplicatedCode
class ProjectCacheInvalidationSignalTests(TestCase):
    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        cache.clear()

    def test_project_save_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        cache.set("event:current-projects", {"cached": True})
        cache.set("projects:past-all", {"cached": True})
        cache.set(PROJECT_ARCHIVE_VERSION_KEY, 7)

        with self.captureOnCommitCallbacks(execute=True):
            Project.objects.create(semester=semester, project_title="Signal Test")

        self.assertIsNone(cache.get("event:current-projects"))
        self.assertIsNone(cache.get("projects:past-all"))
        self.assertEqual(cache.get(PROJECT_ARCHIVE_VERSION_KEY), 8)

    def test_project_delete_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        project = Project.objects.create(semester=semester, project_title="Delete Test")
        cache.set("event:current-projects", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            project.delete()

        self.assertIsNone(cache.get("event:current-projects"))
        self.assertIsNone(cache.get("projects:past-all"))

    def test_semester_save_clears_project_caches(self):
        cache.set("event:current-projects", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            Semester.objects.create(year=2025, season=2, is_published=True)

        self.assertIsNone(cache.get("event:current-projects"))
        self.assertIsNone(cache.get("projects:past-all"))

    def test_semester_delete_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        cache.set("event:current-projects", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            semester.delete()

        self.assertIsNone(cache.get("event:current-projects"))
        self.assertIsNone(cache.get("projects:past-all"))
