"""Coverage gaps for admin forms, inlines, helpers, Unfold context, and login edge cases."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

Member = get_user_model()


# ---------------------------------------------------------------------------
# admin/members/forms.py
# ---------------------------------------------------------------------------
class Base64ImageWidgetTests(SimpleTestCase):
    def _widget(self):
        from apps.authn.admin.members.forms import Base64ImageWidget

        return Base64ImageWidget()

    def test_value_from_datadict_clear_checkbox_returns_empty(self):
        """forms.py — clear checkbox checked, no upload -> returns empty string."""
        widget = self._widget()
        name = "profile_image"
        clear_name = widget.clear_checkbox_name(name)
        result = widget.value_from_datadict({clear_name: "on"}, {}, name)
        self.assertEqual(result, "")

    def test_value_from_datadict_returns_upload_without_reading_it(self):
        """The widget must not consume the stream: ConfirmOnSaveMixin caches request.FILES later."""
        from apps.authn.tests.helpers import PNG_1PX, png_upload

        widget = self._widget()
        upload = png_upload()
        result = widget.value_from_datadict({}, {"profile_image": upload}, "profile_image")
        self.assertIs(result, upload)
        self.assertEqual(upload.read(), PNG_1PX)

    def test_value_from_datadict_returns_none_when_untouched(self):
        widget = self._widget()
        self.assertIsNone(widget.value_from_datadict({}, {}, "profile_image"))

    def test_render_never_inlines_the_stored_base64(self):
        """Regression: inlining the value made the change page grow with the stored image."""
        widget = self._widget()
        widget.preview_url = "/admin/authn/member/abc/profile-image/"
        value = "data:image/png;base64," + ("A" * 5000)

        html = widget.render("profile_image", value)

        self.assertNotIn("base64", html)
        self.assertNotIn("A" * 60, html)
        self.assertIn('src="/admin/authn/member/abc/profile-image/"', html)
        self.assertIn("Current image", html)

    def test_render_offers_a_reachable_remove_checkbox(self):
        """The stock ClearableFileInput template gates this on value.url, which a str never has."""
        widget = self._widget()
        widget.preview_url = "/admin/authn/member/abc/profile-image/"

        html = widget.render("profile_image", "data:image/png;base64,AAAA")

        self.assertIn('name="profile_image-clear"', html)

    def test_render_without_a_stored_image_shows_only_the_file_input(self):
        widget = self._widget()

        html = widget.render("profile_image", "")

        self.assertNotIn("<img", html)
        self.assertNotIn('name="profile_image-clear"', html)
        self.assertIn('type="file"', html)


class MemberCreationFormPasswordIncompleteTests(TestCase):
    def test_only_one_password_field_set_is_invalid(self):
        """forms.py:101-108 — one field filled, the other blank -> password_incomplete error."""
        from django.forms.utils import ErrorDict

        from apps.authn.admin.members.forms import MemberCreationForm

        form = MemberCreationForm(
            {
                "first_name": "Half",
                "last_name": "Password",
                "password1": "OnlyOnePass123!",
                "password2": "",
                "is_active": "on",
            }
        )
        form.cleaned_data = {"password1": "OnlyOnePass123!", "password2": ""}
        form._errors = ErrorDict()
        form.validate_passwords()
        self.assertIn("password2", form._errors)
        self.assertEqual(form._errors["password2"].data[0].code, "password_incomplete")
        self.assertNotIn("set_usable_password", form.cleaned_data)


class MemberChangeFormClearImageTests(TestCase):
    def test_clear_checkbox_clears_image(self):
        """forms.py:129 — clear checkbox in submitted data clears the stored image."""
        from apps.authn.admin.members.forms import MemberChangeForm

        member = Member.objects.create_user(
            first_name="Avatar",
            last_name="User",
            password="StrongPass123!",
            profile_image="data:image/png;base64,old-image",
        )
        clear_name = MemberChangeForm().fields["profile_image"].widget.clear_checkbox_name("profile_image")
        data = {
            "password": member.password,
            "first_name": member.first_name,
            "middle_name": "",
            "last_name": member.last_name,
            "organization": "",
            "title": "",
            "profile_image": "",
            clear_name: "on",
            "is_active": "on",
            "is_staff": "",
            "is_superuser": "",
            "groups": [],
            "user_permissions": [],
            "last_login": "",
            "date_joined": member.date_joined.isoformat(),
        }
        form = MemberChangeForm(data=data, files={}, instance=member)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.profile_image, "")


class MemberImportFormValidationTests(SimpleTestCase):
    def test_wrong_extension_rejected(self):
        """import_forms.py — anything but .xlsx (openpyxl reads only that format) raises a validation error."""
        from apps.authn.admin.members.import_forms import MemberImportForm

        upload = SimpleUploadedFile("members.txt", b"data", content_type="text/plain")
        form = MemberImportForm(data={}, files={"excel_file": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("excel_file", form.errors)
        self.assertIn("Please upload an .xlsx file", str(form.errors["excel_file"]))

    def test_oversized_file_rejected(self):
        """import_forms.py — a file larger than 5MB raises a validation error."""
        from apps.authn.admin.members.import_forms import MemberImportForm

        big = SimpleUploadedFile(
            "members.xlsx",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        form = MemberImportForm(data={}, files={"excel_file": big})
        self.assertFalse(form.is_valid())
        self.assertIn("excel_file", form.errors)
        self.assertIn("cannot exceed 5MB", str(form.errors["excel_file"]))
