from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.projects.admin.semester import SemesterAdmin
from apps.projects.models import Project, Semester

User = get_user_model()


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


def _project_csv_upload():
    content = "\n".join(
        [
            "Year-Semester,ClassCode,Team#,TeamName,ProjectTitle,Organization,Industry,Col7,Abstract,StudentNames",
            "2024-2 Fall,CSE,101,Alpha,Smart App,TechCorp,Software,,An abstract,Alice Bob",
        ]
    )
    return SimpleUploadedFile("projects.csv", content.encode("utf-8"), content_type="text/csv")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=True)
class ProjectAdminConfirmationTest(TestCase):
    def setUp(self):
        self.admin_user = _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_publish_all_form_renders_confirmation_input(self):
        response = self.client.get(reverse("admin:projects_semester_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="confirmation_text"')
        self.assertContains(response, 'id="publish-all-confirmation"')
        self.assertContains(response, 'Type "publish all"')

    def test_publish_all_rejects_missing_confirmation_text(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=False)

        response = self.client.post(reverse("admin:projects_publish_all"), {}, follow=True)

        self.assertContains(response, "Confirmation text does not match")
        semester.refresh_from_db()
        self.assertFalse(semester.is_published)

    def test_publish_all_succeeds_with_confirmation_text(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=False)

        response = self.client.post(reverse("admin:projects_publish_all"), {"confirmation_text": "publish all"})

        self.assertRedirects(response, reverse("admin:projects_semester_changelist"))
        semester.refresh_from_db()
        self.assertTrue(semester.is_published)

    def test_import_page_renders_confirmation_input(self):
        response = self.client.get(reverse("admin:projects_import_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="confirmation_text"')
        self.assertContains(response, 'Type <strong>"import"</strong>')

    def test_real_import_rejects_missing_confirmation_text(self):
        response = self.client.post(
            reverse("admin:projects_import_csv"),
            {"csv_file": _project_csv_upload()},
            follow=True,
        )

        self.assertContains(response, "Confirmation text does not match")
        self.assertEqual(Project.objects.count(), 0)

    def test_real_import_succeeds_with_confirmation_text(self):
        response = self.client.post(
            reverse("admin:projects_import_csv"),
            {"csv_file": _project_csv_upload(), "confirmation_text": "import"},
        )

        self.assertRedirects(response, reverse("admin:projects_semester_changelist"))
        self.assertEqual(Project.objects.count(), 1)
        semester = Semester.objects.get(year=2024, season=Semester.Season.FALL)
        self.assertFalse(semester.is_published)

    def test_dry_run_import_does_not_require_confirmation_text(self):
        response = self.client.post(
            reverse("admin:projects_import_csv"),
            {"csv_file": _project_csv_upload(), "dry_run": "1"},
        )

        self.assertRedirects(response, reverse("admin:projects_semester_changelist"))
        self.assertEqual(Project.objects.count(), 0)

    def test_import_without_file_reports_error(self):
        response = self.client.post(reverse("admin:projects_import_csv"), {}, follow=True)

        self.assertContains(response, "No file uploaded.")
        self.assertEqual(Project.objects.count(), 0)

    def test_import_surfaces_row_errors_as_warnings(self):
        # A CSV whose data row has a malformed semester label produces row-level
        # errors that the admin echoes back as warning messages.
        content = "\n".join(
            [
                "Year-Semester,ClassCode,Team#,TeamName,ProjectTitle,Organization,Industry,Col7,Abstract,StudentNames",
                "bad-semester,CSE,101,Alpha,Title,Org,Software,,Abstract,Alice",
            ]
        )
        upload = SimpleUploadedFile("projects.csv", content.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("admin:projects_import_csv"),
            {"csv_file": upload, "confirmation_text": "import"},
            follow=True,
        )

        self.assertRedirects(response, reverse("admin:projects_semester_changelist"))
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("row" in m.lower() or "error" in m.lower() or "invalid" in m.lower() for m in messages))


class SemesterAdminActionTest(TestCase):
    """Exercises the bulk publish/unpublish action methods directly.

    Driving them through the changelist POST would route through the
    confirmation mixin; calling the bound action methods isolates the action
    logic (the queryset update + cache invalidation + user message).
    """

    def setUp(self):
        self.admin = SemesterAdmin(Semester, admin.site)
        self.factory = RequestFactory()

    def _request(self):
        request = self.factory.post("/admin/projects/semester/")
        # message_user needs the messages framework wired onto the request.
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_publish_selected_action_publishes(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=False)

        self.admin.publish_selected(self._request(), Semester.objects.filter(pk=semester.pk))

        semester.refresh_from_db()
        self.assertTrue(semester.is_published)

    def test_unpublish_selected_action_unpublishes(self):
        semester = Semester.objects.create(year=2024, season=Semester.Season.FALL, is_published=True)

        self.admin.unpublish_selected(self._request(), Semester.objects.filter(pk=semester.pk))

        semester.refresh_from_db()
        self.assertFalse(semester.is_published)
