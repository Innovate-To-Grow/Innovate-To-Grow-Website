"""
Tests for MobileID admin scanning functionality.

Covers:
- TransactionAdmin custom views (scan, lookup, confirm)
- Barcode lookup with valid/invalid values
- Transaction creation via confirm endpoint
"""

import json

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .admin import TransactionAdmin
from .models import Barcode, Transaction

User = get_user_model()


class TransactionAdminScanViewTest(TestCase):
    """Test TransactionAdmin custom scan views."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.client.force_login(self.admin_user)

        # Create test member and barcode
        self.member = User.objects.create_user(
            username="testmember",
            password="pass123",
            email="member@test.com",
            first_name="Test",
            last_name="Member",
        )
        self.barcode = Barcode.objects.create(
            model_user=self.member,
            barcode_type="Identification",
            barcode="BC-12345",
            profile_name="Test Profile",
        )

    def test_scan_view_renders(self):
        """GET scan/ returns the scanning page."""
        url = reverse("admin:mobileid_transaction_scan")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scan Barcode")
        self.assertContains(response, "html5-qrcode")

    def test_lookup_valid_barcode(self):
        """POST scan/lookup/ with valid barcode returns user info."""
        url = reverse("admin:mobileid_transaction_scan_lookup")
        response = self.client.post(
            url,
            data=json.dumps({"barcode": "BC-12345"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["username"], "testmember")
        self.assertEqual(data["barcode_value"], "BC-12345")
        self.assertEqual(data["barcode_type"], "Identification")
        self.assertEqual(data["profile_name"], "Test Profile")

    def test_lookup_invalid_barcode(self):
        """POST scan/lookup/ with nonexistent barcode returns not found."""
        url = reverse("admin:mobileid_transaction_scan_lookup")
        response = self.client.post(
            url,
            data=json.dumps({"barcode": "NONEXISTENT"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["found"])
        self.assertIn("error", data)

    def test_lookup_empty_barcode(self):
        """POST scan/lookup/ with empty barcode returns error."""
        url = reverse("admin:mobileid_transaction_scan_lookup")
        response = self.client.post(
            url,
            data=json.dumps({"barcode": ""}),
            content_type="application/json",
        )
        data = response.json()
        self.assertFalse(data["found"])

    def test_lookup_get_not_allowed(self):
        """GET scan/lookup/ returns 405."""
        url = reverse("admin:mobileid_transaction_scan_lookup")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_confirm_creates_transaction(self):
        """POST scan/confirm/ creates a Transaction record."""
        url = reverse("admin:mobileid_transaction_scan_confirm")
        response = self.client.post(
            url,
            data=json.dumps({
                "barcode_id": str(self.barcode.pk),
                "user_id": str(self.member.pk),
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("transaction_id", data)

        # Verify transaction was created
        self.assertEqual(Transaction.objects.count(), 1)
        txn = Transaction.objects.first()
        self.assertEqual(txn.model_user, self.member)
        self.assertEqual(txn.barcode_used, self.barcode)

    def test_confirm_invalid_barcode_id(self):
        """POST scan/confirm/ with invalid barcode returns error."""
        url = reverse("admin:mobileid_transaction_scan_confirm")
        response = self.client.post(
            url,
            data=json.dumps({
                "barcode_id": "00000000-0000-0000-0000-000000000000",
                "user_id": str(self.member.pk),
            }),
            content_type="application/json",
        )
        data = response.json()
        self.assertFalse(data["success"])

    def test_confirm_missing_fields(self):
        """POST scan/confirm/ without required fields returns error."""
        url = reverse("admin:mobileid_transaction_scan_confirm")
        response = self.client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
        )
        data = response.json()
        self.assertFalse(data["success"])

    def test_confirm_get_not_allowed(self):
        """GET scan/confirm/ returns 405."""
        url = reverse("admin:mobileid_transaction_scan_confirm")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


class TransactionAdminDisplayTest(TestCase):
    """Test TransactionAdmin list display methods."""

    def setUp(self):
        self.site = AdminSite()
        self.admin = TransactionAdmin(Transaction, self.site)

        self.member = User.objects.create_user(
            username="member1", password="pass", email="m@test.com"
        )
        self.barcode = Barcode.objects.create(
            model_user=self.member,
            barcode_type="DynamicBarcode",
            barcode="DYN-001",
        )
        self.transaction = Transaction.objects.create(
            model_user=self.member,
            barcode_used=self.barcode,
        )

    def test_user_display(self):
        self.assertEqual(self.admin.user_display(self.transaction), "member1")

    def test_barcode_display(self):
        result = self.admin.barcode_display(self.transaction)
        self.assertIn("DYN-001", result)


class TransactionChangeListTest(TestCase):
    """Test that the change list has the scan button."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin", password="admin123", email="admin@test.com"
        )
        self.client.force_login(self.admin_user)

    def test_changelist_has_scan_button(self):
        url = reverse("admin:mobileid_transaction_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scan Barcode")
