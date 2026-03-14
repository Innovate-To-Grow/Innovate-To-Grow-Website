from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from authn.models import ContactPhone

Member = get_user_model()


class ContactPhoneTests(APITestCase):
    def setUp(self):
        self.member = Member.objects.create_user(
            username="testuser",
            email="primary@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.other_member = Member.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.client.force_authenticate(user=self.member)

    # ── List ─────────────────────────────────────────────

    def test_list_contact_phones_empty(self):
        response = self.client.get("/authn/contact-phones/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_list_returns_own_phones_only(self):
        ContactPhone.objects.create(member=self.member, phone_number="+12025551234", region="1-US")
        ContactPhone.objects.create(member=self.other_member, phone_number="+12025555678", region="1-US")
        response = self.client.get("/authn/contact-phones/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["phone_number"], "+12025551234")

    # ── Create ───────────────────────────────────────────

    def test_create_contact_phone(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "2025551234", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["phone_number"], "+12025551234")
        self.assertEqual(response.data["region"], "1-US")
        self.assertEqual(response.data["region_display"], "United States")
        self.assertFalse(response.data["subscribe"])
        self.assertFalse(response.data["verified"])
        self.assertIn("id", response.data)
        self.assertIn("created_at", response.data)

    def test_create_with_subscribe(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "2025551234", "region": "1-US", "subscribe": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["subscribe"])

    def test_create_normalizes_formatted_number(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "(202) 555-1234", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["phone_number"], "+12025551234")

    def test_create_preserves_international_prefix(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "+8613800138000", "region": "86"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["phone_number"], "+8613800138000")

    def test_create_rejects_duplicate(self):
        ContactPhone.objects.create(member=self.other_member, phone_number="+12025551234", region="1-US")
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "2025551234", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_too_short(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "123", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_too_long(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "1234567890123456", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_invalid_region(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "2025551234", "region": "999-XX"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_rejects_non_digits(self):
        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "abc1234567", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_reclaims_soft_deleted(self):
        phone = ContactPhone.objects.create(member=self.member, phone_number="+12025551234", region="1-US")
        phone.delete()  # soft-delete
        self.assertFalse(ContactPhone.objects.filter(pk=phone.pk).exists())

        response = self.client.post(
            "/authn/contact-phones/",
            {"phone_number": "+12025551234", "region": "1-US"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["phone_number"], "+12025551234")

    # ── Update (subscribe toggle) ──────────────────────

    def test_patch_subscribe_toggle(self):
        phone = ContactPhone.objects.create(
            member=self.member, phone_number="+12025551234", region="1-US", subscribe=False
        )
        response = self.client.patch(
            f"/authn/contact-phones/{phone.pk}/",
            {"subscribe": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["subscribe"])

        phone.refresh_from_db()
        self.assertTrue(phone.subscribe)

    def test_cannot_patch_other_users_phone(self):
        phone = ContactPhone.objects.create(member=self.other_member, phone_number="+12025551234", region="1-US")
        response = self.client.patch(
            f"/authn/contact-phones/{phone.pk}/",
            {"subscribe": True},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    # ── Delete ───────────────────────────────────────────

    def test_delete_returns_204(self):
        phone = ContactPhone.objects.create(member=self.member, phone_number="+12025551234", region="1-US")
        response = self.client.delete(f"/authn/contact-phones/{phone.pk}/")
        self.assertEqual(response.status_code, 204)

        # Soft-deleted: not visible via objects
        self.assertFalse(ContactPhone.objects.filter(pk=phone.pk).exists())

    # ── Scoping ──────────────────────────────────────────

    def test_cannot_delete_other_users_phone(self):
        phone = ContactPhone.objects.create(member=self.other_member, phone_number="+12025551234", region="1-US")
        response = self.client.delete(f"/authn/contact-phones/{phone.pk}/")
        self.assertEqual(response.status_code, 404)

    # ── Auth required ────────────────────────────────────

    def test_unauthenticated_list_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/authn/contact-phones/")
        self.assertEqual(response.status_code, 401)
