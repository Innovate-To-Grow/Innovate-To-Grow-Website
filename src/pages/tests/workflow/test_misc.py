"""
Tests for PageComponent cache invalidation and workflow transitions without a user.

Covers:
- PageComponent parent cache invalidation via placements
- Workflow transitions with user=None
"""

from django.core.cache import cache
from django.test import TestCase

from ...models import HomePage, Page, PageComponent, PageComponentPlacement
from ...models.pages.content.home_page import HOMEPAGE_CACHE_KEY
from ...models.pages.content.page import PAGE_CACHE_KEY_PREFIX


class PageComponentCacheInvalidationTest(TestCase):
    """Test that saving a PageComponent/Placement invalidates parent cache."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_placement_save_invalidates_page_cache(self):
        """Creating a placement invalidates the parent Page cache."""
        page = Page.objects.create(title="Parent", slug="parent-page", status="published")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.parent-page"

        # Populate cache
        Page.get_published_by_slug("parent-page")
        self.assertIsNotNone(cache.get(cache_key))

        # Create component + placement -> parent cache invalidated via placement.save()
        comp = PageComponent.objects.create(
            name="Comp", component_type="html", html_content="<p>Content</p>"
        )
        PageComponentPlacement.objects.create(component=comp, page=page, order=1)
        self.assertIsNone(cache.get(cache_key))

    def test_placement_save_invalidates_homepage_cache(self):
        """Creating a placement invalidates the parent HomePage cache."""
        hp = HomePage.objects.create(name="Home", status="published", is_active=True)

        # Populate cache
        HomePage.get_active()
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        # Create component + placement -> parent cache invalidated via placement.save()
        comp = PageComponent.objects.create(
            name="HP Comp", component_type="html", html_content="<p>Content</p>"
        )
        PageComponentPlacement.objects.create(component=comp, home_page=hp, order=1)
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_component_update_invalidates_page_cache(self):
        """Updating a component invalidates the parent Page cache via _invalidate_all_parent_caches."""
        page = Page.objects.create(title="Parent", slug="parent-upd", status="published")
        comp = PageComponent.objects.create(
            name="Update Comp", component_type="html", html_content="<p>Old</p>"
        )
        PageComponentPlacement.objects.create(component=comp, page=page, order=1)
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.parent-upd"

        # Populate cache
        Page.get_published_by_slug("parent-upd")
        self.assertIsNotNone(cache.get(cache_key))

        # Update component -> cache invalidated via component.save() -> _invalidate_all_parent_caches()
        comp.html_content = "<p>New</p>"
        comp.save()
        self.assertIsNone(cache.get(cache_key))


class WorkflowWithoutUserTest(TestCase):
    """Test workflow transitions work without a user (user=None)."""

    def test_page_workflow_without_user(self):
        page = Page.objects.create(title="No User", slug="no-user")

        page.submit_for_review()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "review")
        self.assertIsNone(page.submitted_for_review_by)

        page.publish()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "published")
        self.assertIsNone(page.published_by)

        page.unpublish()
        page.refresh_from_db()
        self.assertEqual(self.page_status(page), "draft")

    def test_homepage_workflow_without_user(self):
        hp = HomePage.objects.create(name="No User Home")

        hp.submit_for_review()
        hp.refresh_from_db()
        self.assertEqual(hp.status, "review")
        self.assertIsNone(hp.submitted_for_review_by)

        hp.publish()
        hp.refresh_from_db()
        self.assertEqual(hp.status, "published")
        self.assertIsNone(hp.published_by)

    @staticmethod
    def page_status(page):
        return page.status
