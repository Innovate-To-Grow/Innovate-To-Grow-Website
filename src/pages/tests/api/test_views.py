from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from ...models import HomePage, Page


class HomePageAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("pages:home-page")

    def test_get_active_home_page(self):
        """Active and published home page returns 200."""
        HomePage.objects.create(name="Active", status="published", is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Active")

    def test_no_active_home_page(self):
        """Inactive home page returns 404."""
        HomePage.objects.create(name="Inactive", is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_draft_not_returned(self):
        """Draft home page is not returned even if it's the only one."""
        HomePage.objects.create(name="Draft", status="draft", is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_response_includes_status_and_published(self):
        """Response includes status and published fields."""
        HomePage.objects.create(name="Home", status="published", is_active=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "published")
        self.assertTrue(response.data["published"])


class PageRetrieveAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_retrieve_published_page(self):
        """Published page returns 200."""
        Page.objects.create(title="About", slug="about", status="published")
        url = reverse("pages:page-retrieve", kwargs={"slug": "about"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "About")
        self.assertEqual(response.data["status"], "published")
        self.assertTrue(response.data["published"])

    def test_retrieve_draft_returns_404(self):
        """Draft page returns 404 via public API."""
        Page.objects.create(title="Draft", slug="draft-page", status="draft")
        url = reverse("pages:page-retrieve", kwargs={"slug": "draft-page"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_review_returns_404(self):
        """Page in review returns 404 via public API."""
        Page.objects.create(title="Review", slug="review-page", status="review")
        url = reverse("pages:page-retrieve", kwargs={"slug": "review-page"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_not_found(self):
        """Nonexistent slug returns 404."""
        url = reverse("pages:page-retrieve", kwargs={"slug": "missing"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PageListAPIViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("pages:page-list")

    def test_list_only_published_pages(self):
        """Only published pages appear in the list."""
        Page.objects.create(title="Published", slug="published", status="published")
        Page.objects.create(title="Draft", slug="draft", status="draft")
        Page.objects.create(title="Review", slug="review", status="review")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pages = response.data["pages"]
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["title"], "Published")

    def test_list_empty(self):
        """Empty list returns empty pages array."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["pages"]), 0)
