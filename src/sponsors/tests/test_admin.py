from django.test import TestCase

from authn.models import ContactEmail, Member
from sponsors.admin.sponsor import SponsorAdmin
from sponsors.models import Sponsor


class SponsorAdminTest(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="admin", email="admin@example.com", password="testpass123"
        )
        ContactEmail.objects.create(
            member=self.admin_user, email_address="admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="admin", password="testpass123")

    def test_changelist_accessible(self):
        response = self.client.get("/admin/sponsors/sponsor/")
        self.assertEqual(response.status_code, 200)

    def test_add_form_accessible(self):
        response = self.client.get("/admin/sponsors/sponsor/add/")
        self.assertEqual(response.status_code, 200)

    def test_search_by_name(self):
        Sponsor.objects.create(name="Searchable Corp", year=2025)
        response = self.client.get("/admin/sponsors/sponsor/?q=Searchable")
        self.assertEqual(response.status_code, 200)

    def test_list_filter_by_year(self):
        response = self.client.get("/admin/sponsors/sponsor/?year=2025")
        self.assertEqual(response.status_code, 200)

    def test_logo_preview_small_with_logo(self):
        sponsor = Sponsor(name="Test", year=2025)
        sponsor.logo.name = "sponsors/logos/test.png"
        admin_instance = SponsorAdmin(Sponsor, None)
        result = admin_instance.logo_preview_small(sponsor)
        self.assertIn("<img", result)
        self.assertIn("test.png", result)

    def test_logo_preview_small_without_logo(self):
        sponsor = Sponsor(name="Test", year=2025)
        admin_instance = SponsorAdmin(Sponsor, None)
        result = admin_instance.logo_preview_small(sponsor)
        self.assertEqual(result, "-")

    def test_logo_preview_with_logo(self):
        sponsor = Sponsor(name="Test", year=2025)
        sponsor.logo.name = "sponsors/logos/test.png"
        admin_instance = SponsorAdmin(Sponsor, None)
        result = admin_instance.logo_preview(sponsor)
        self.assertIn("<img", result)

    def test_logo_preview_without_logo(self):
        sponsor = Sponsor(name="Test", year=2025)
        admin_instance = SponsorAdmin(Sponsor, None)
        result = admin_instance.logo_preview(sponsor)
        self.assertEqual(result, "No logo uploaded")
