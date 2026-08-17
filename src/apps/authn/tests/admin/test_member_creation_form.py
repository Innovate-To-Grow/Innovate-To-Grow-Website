from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.authn.admin.members.forms import MemberChangeForm, MemberCreationForm
from apps.authn.models import Member
from apps.authn.tests.helpers import PNG_1PX, PNG_1PX_DATA_URI, png_upload


class MemberCreationFormPasswordTest(TestCase):
    def test_empty_passwords_valid_and_sets_unusable_password(self):
        form = MemberCreationForm(
            {
                "first_name": "No",
                "last_name": "Password",
                "password1": "",
                "password2": "",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user: Member = form.save()
        self.assertIsNotNone(user.pk)
        self.assertFalse(user.has_usable_password())

    def test_mismatched_passwords_invalid(self):
        form = MemberCreationForm(
            {
                "first_name": "A",
                "last_name": "B",
                "password1": "onepassword123",
                "password2": "otherpassword123",
                "is_active": "on",
            }
        )
        self.assertFalse(form.is_valid())

    def test_matching_passwords_sets_usable(self):
        form = MemberCreationForm(
            {
                "first_name": "A",
                "last_name": "B",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "is_active": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.has_usable_password())


class MemberChangeFormProfileImageTest(TestCase):
    def _member(self):
        return Member.objects.create_user(
            first_name="Avatar",
            last_name="User",
            password="StrongPass123!",
            profile_image="data:image/png;base64,old-image",
        )

    def _form_data(self, member, **overrides):
        data = {
            "password": member.password,
            "first_name": member.first_name,
            "middle_name": member.middle_name or "",
            "last_name": member.last_name,
            "organization": member.organization or "",
            "title": member.title or "",
            "profile_image": "",
            "is_active": "on" if member.is_active else "",
            "is_staff": "on" if member.is_staff else "",
            "is_superuser": "on" if member.is_superuser else "",
            "groups": [],
            "user_permissions": [],
            "last_login": "",
            # date_joined has a callable model default, so Django sets show_hidden_initial and
            # compares against the "initial-date_joined" hidden input a rendered form submits — not
            # against the instance. Send both, truncated to whole seconds like the widget renders
            # them (DateTimeInput.supports_microseconds is False), otherwise date_joined shows up in
            # changed_data on every save and masks what these tests assert.
            "date_joined": member.date_joined.replace(microsecond=0).isoformat(),
            "initial-date_joined": member.date_joined.replace(microsecond=0).isoformat(),
        }
        data.update(overrides)
        return data

    def test_empty_profile_image_input_preserves_existing_image(self):
        member = self._member()

        form = MemberChangeForm(data=self._form_data(member, first_name="Updated"), files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.first_name, "Updated")
        self.assertEqual(saved.profile_image, "data:image/png;base64,old-image")

    def test_omitted_profile_image_input_preserves_existing_image(self):
        member = self._member()
        data = self._form_data(member, first_name="Omitted")
        data.pop("profile_image")

        form = MemberChangeForm(data=data, files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.first_name, "Omitted")
        self.assertEqual(saved.profile_image, "data:image/png;base64,old-image")

    def test_uploaded_profile_image_replaces_existing_image(self):
        member = self._member()

        form = MemberChangeForm(
            data=self._form_data(member),
            files={"profile_image": png_upload()},
            instance=member,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.profile_image, PNG_1PX_DATA_URI)

    def test_oversized_upload_is_rejected(self):
        member = self._member()
        oversized = SimpleUploadedFile("big.png", PNG_1PX + b"\x00" * (5 * 1024 * 1024), content_type="image/png")

        form = MemberChangeForm(data=self._form_data(member), files={"profile_image": oversized}, instance=member)

        self.assertFalse(form.is_valid())
        self.assertIn("5 MB", str(form.errors["profile_image"]))
        member.refresh_from_db()
        self.assertEqual(member.profile_image, "data:image/png;base64,old-image")

    def test_non_image_upload_is_rejected(self):
        """The admin used to trust the client's Content-Type and store whatever was uploaded."""
        member = self._member()
        disguised = SimpleUploadedFile("evil.png", b"<html>not an image</html>", content_type="image/png")

        form = MemberChangeForm(data=self._form_data(member), files={"profile_image": disguised}, instance=member)

        self.assertFalse(form.is_valid())
        self.assertIn("does not match", str(form.errors["profile_image"]))

    def test_upload_content_type_is_taken_from_the_signature_not_the_client(self):
        member = self._member()
        lying = SimpleUploadedFile("avatar.jpg", PNG_1PX, content_type="image/jpeg")

        form = MemberChangeForm(data=self._form_data(member), files={"profile_image": lying}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().profile_image.startswith("data:image/png;base64,"))

    # --- changed_data: profile_image must not look dirty when it was never touched -------------

    def test_unchanged_profile_image_is_not_in_changed_data(self):
        member = self._member()

        form = MemberChangeForm(data=self._form_data(member, first_name="Updated"), files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["first_name"])

    def test_no_edits_at_all_yields_empty_changed_data(self):
        member = self._member()

        form = MemberChangeForm(data=self._form_data(member), files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, [])

    def test_uploaded_profile_image_is_in_changed_data(self):
        member = self._member()

        form = MemberChangeForm(data=self._form_data(member), files={"profile_image": png_upload()}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["profile_image"])

    def test_clearing_an_existing_image_is_a_change(self):
        member = self._member()
        clear_name = MemberChangeForm().fields["profile_image"].widget.clear_checkbox_name("profile_image")

        form = MemberChangeForm(data=self._form_data(member, **{clear_name: "on"}), files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["profile_image"])
        self.assertEqual(form.save().profile_image, "")

    def test_large_stored_image_round_trips_without_being_marked_changed(self):
        member = Member.objects.create_user(
            first_name="Big",
            last_name="Avatar",
            password="StrongPass123!",
            profile_image="data:image/png;base64," + ("A" * 2_000_000),
        )

        form = MemberChangeForm(data=self._form_data(member, title="Dean"), files={}, instance=member)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.changed_data, ["title"])
        self.assertEqual(len(form.save().profile_image), len("data:image/png;base64,") + 2_000_000)
