from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authn.services.members.accounts.profile_image import (
    CONTENT_TYPE_ERROR,
    DIMENSIONS_ERROR,
    OVERSIZE_ERROR,
    SIGNATURE_ERROR,
    ProfileImageError,
)
from apps.authn.tests.account.profile.test_profile import _PNG_BYTES, _ProfileUpdateCase


class ProfileUpdateTests(_ProfileUpdateCase):
    def test_patch_profile_image_preserves_known_validation_messages(self):
        for message in (OVERSIZE_ERROR, CONTENT_TYPE_ERROR, SIGNATURE_ERROR, DIMENSIONS_ERROR):
            with self.subTest(message=message):
                upload = SimpleUploadedFile("avatar.png", _PNG_BYTES, content_type="image/png")
                with patch(
                    "apps.authn.views.account.profile.encode_profile_image",
                    side_effect=ProfileImageError(message),
                ):
                    response = self.client.patch("/authn/profile/", {"profile_image": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": message})

    def test_patch_profile_image_does_not_expose_unexpected_exception_details(self):
        self.member.profile_image = "data:image/png;base64,QQ=="
        self.member.save(update_fields=["profile_image"])
        for message in (
            "Failed opening /private/internal/avatar.png with credential=private-value",
            f"{CONTENT_TYPE_ERROR}\nInternal decoder details: /private/internal/avatar.png",
        ):
            with self.subTest(message=message):
                upload = SimpleUploadedFile("avatar.png", _PNG_BYTES, content_type="image/png")
                with patch(
                    "apps.authn.views.account.profile.encode_profile_image",
                    side_effect=ProfileImageError(message),
                ):
                    response = self.client.patch("/authn/profile/", {"profile_image": upload}, format="multipart")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": "Profile image could not be processed."})
                self.member.refresh_from_db()
                self.assertEqual(self.member.profile_image, "data:image/png;base64,QQ==")

    def test_patch_invalid_json_field_returns_400(self):
        response = self.client.patch("/authn/profile/", {"first_name": ""}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/authn/profile/")
        self.assertEqual(response.status_code, 401)
