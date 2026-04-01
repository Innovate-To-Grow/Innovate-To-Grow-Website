from django.test import TestCase

from sponsors.models import Sponsor


class SponsorModelTest(TestCase):
    def test_str_includes_name_and_year(self):
        sponsor = Sponsor.objects.create(name="Acme Corp", year=2025)
        self.assertEqual(str(sponsor), "Acme Corp (2025)")

    def test_ordering_by_year_desc_then_display_order_then_name(self):
        s1 = Sponsor.objects.create(name="Beta", year=2024, display_order=0)
        s2 = Sponsor.objects.create(name="Alpha", year=2025, display_order=1)
        s3 = Sponsor.objects.create(name="Gamma", year=2025, display_order=0)
        self.assertEqual(list(Sponsor.objects.all()), [s3, s2, s1])

    def test_soft_delete_excludes_from_default_manager(self):
        sponsor = Sponsor.objects.create(name="Test", year=2025)
        sponsor.delete()
        self.assertEqual(Sponsor.objects.count(), 0)

    def test_soft_delete_visible_via_all_objects(self):
        sponsor = Sponsor.objects.create(name="Test", year=2025)
        sponsor.delete()
        self.assertEqual(Sponsor.all_objects.count(), 1)

    def test_display_order_default_is_zero(self):
        sponsor = Sponsor.objects.create(name="Test", year=2025)
        self.assertEqual(sponsor.display_order, 0)

    def test_logo_field_is_optional(self):
        sponsor = Sponsor.objects.create(name="Test", year=2025)
        self.assertFalse(sponsor.logo)

    def test_website_field_is_optional(self):
        sponsor = Sponsor.objects.create(name="Test", year=2025, website="")
        self.assertEqual(sponsor.website, "")
