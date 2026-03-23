"""Tests for ProfileView PATCH (text field updates)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from authn.models.members.member import MemberProfile

Member = get_user_model()


class ProfileUpdateTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(
            username="profuser",
            email="prof@example.com",
            password="StrongPass123!",
            first_name="Original",
            last_name="Name",
            is_active=True,
        )
        self.client.force_authenticate(user=self.member)

    def test_get_profile_returns_all_fields(self):
        response = self.client.get("/authn/profile/")
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertIn("member_uuid", data)
        self.assertIn("email", data)
        self.assertIn("username", data)
        self.assertIn("first_name", data)
        self.assertIn("last_name", data)
        self.assertIn("display_name", data)
        self.assertIn("organization", data)
        self.assertIn("email_subscribe", data)
        self.assertIn("is_active", data)
        self.assertIn("date_joined", data)
        self.assertIn("profile_image", data)

    def test_patch_first_name(self):
        response = self.client.patch(
            "/authn/profile/",
            {"first_name": "NewFirst"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "NewFirst")

    def test_patch_last_name(self):
        response = self.client.patch(
            "/authn/profile/",
            {"last_name": "NewLast"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.last_name, "NewLast")

    def test_patch_organization(self):
        response = self.client.patch(
            "/authn/profile/",
            {"organization": "Acme Corp"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.organization, "Acme Corp")

    def test_patch_display_name(self):
        response = self.client.patch(
            "/authn/profile/",
            {"display_name": "Cool Display Name"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        profile = MemberProfile.objects.get(model_user=self.member)
        self.assertEqual(profile.display_name, "Cool Display Name")

    def test_patch_email_subscribe(self):
        response = self.client.patch(
            "/authn/profile/",
            {"email_subscribe": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.email_subscribe)

    def test_patch_multiple_fields(self):
        response = self.client.patch(
            "/authn/profile/",
            {"first_name": "Multi", "last_name": "Update", "organization": "TestOrg"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Multi")
        self.assertEqual(self.member.last_name, "Update")
        self.assertEqual(self.member.organization, "TestOrg")

    def test_patch_ignores_readonly_fields(self):
        original_email = self.member.email
        original_username = self.member.username
        original_uuid = str(self.member.member_uuid)

        response = self.client.patch(
            "/authn/profile/",
            {"email": "hacked@evil.com", "username": "hacked", "member_uuid": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.email, original_email)
        self.assertEqual(self.member.username, original_username)
        self.assertEqual(str(self.member.member_uuid), original_uuid)

    def test_unauthenticated_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/authn/profile/")
        self.assertEqual(response.status_code, 401)
