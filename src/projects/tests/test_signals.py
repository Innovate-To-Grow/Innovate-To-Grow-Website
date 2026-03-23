from django.core.cache import cache
from django.test import TestCase

from projects.models import Project, Semester


# noinspection DuplicatedCode
class ProjectCacheInvalidationSignalTests(TestCase):
    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        cache.clear()

    def test_project_save_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        cache.set("projects:current", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            Project.objects.create(semester=semester, project_title="Signal Test")

        self.assertIsNone(cache.get("projects:current"))
        self.assertIsNone(cache.get("projects:past-all"))

    def test_project_delete_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=1, is_published=True)
        project = Project.objects.create(semester=semester, project_title="Delete Test")
        cache.set("projects:current", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            project.delete()

        self.assertIsNone(cache.get("projects:current"))
        self.assertIsNone(cache.get("projects:past-all"))

    def test_semester_save_clears_project_caches(self):
        cache.set("projects:current", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            Semester.objects.create(year=2025, season=2, is_published=True)

        self.assertIsNone(cache.get("projects:current"))
        self.assertIsNone(cache.get("projects:past-all"))

    def test_semester_delete_clears_project_caches(self):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        cache.set("projects:current", {"cached": True})
        cache.set("projects:past-all", {"cached": True})

        with self.captureOnCommitCallbacks(execute=True):
            semester.delete()

        self.assertIsNone(cache.get("projects:current"))
        self.assertIsNone(cache.get("projects:past-all"))
