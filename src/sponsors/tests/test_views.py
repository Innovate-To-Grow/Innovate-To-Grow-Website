from django.test import TestCase
from rest_framework.test import APIClient

from sponsors.models import Sponsor


class SponsorListAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.sponsor_2025a = Sponsor.objects.create(
            name="Acme Corp", year=2025, display_order=0, website="https://acme.com"
        )
        self.sponsor_2025b = Sponsor.objects.create(name="Beta Inc", year=2025, display_order=1)
        self.sponsor_2024 = Sponsor.objects.create(name="Old Sponsor", year=2024, display_order=0)

    def test_list_returns_grouped_by_year(self):
        response = self.client.get("/sponsors/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["year"], 2025)
        self.assertEqual(len(data[0]["sponsors"]), 2)
        self.assertEqual(data[0]["sponsors"][0]["name"], "Acme Corp")
        self.assertEqual(data[0]["sponsors"][1]["name"], "Beta Inc")
        self.assertEqual(data[1]["year"], 2024)
        self.assertEqual(len(data[1]["sponsors"]), 1)

    def test_empty_list(self):
        Sponsor.objects.all().delete()
        response = self.client.get("/sponsors/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_soft_deleted_sponsors_excluded(self):
        self.sponsor_2025a.delete()
        response = self.client.get("/sponsors/")
        data = response.json()
        names_2025 = [s["name"] for s in data[0]["sponsors"]]
        self.assertNotIn("Acme Corp", names_2025)

    def test_sponsor_fields(self):
        response = self.client.get("/sponsors/")
        sponsor = response.json()[0]["sponsors"][0]
        self.assertIn("id", sponsor)
        self.assertIn("name", sponsor)
        self.assertIn("logo", sponsor)
        self.assertIn("website", sponsor)
        self.assertEqual(sponsor["website"], "https://acme.com")
