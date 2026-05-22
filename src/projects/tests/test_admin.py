from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from authn.models import ContactEmail
from projects.models import Project, Semester

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
