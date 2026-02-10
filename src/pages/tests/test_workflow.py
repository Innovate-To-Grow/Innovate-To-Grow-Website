"""
Tests for publishing workflow transitions, version tracking, and cache behavior.

Covers:
- WorkflowPublishingMixin transitions on Page model
- HomePage workflow transitions (with is_active semantics)
- Version history creation on workflow actions
- Cache invalidation on save/delete/publish
- Page.get_published_by_slug() caching
- HomePage.get_active() caching
- PageComponent parent cache invalidation
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from ..models import HomePage, Page, PageComponent
from ..models.pages.home_page import HOMEPAGE_CACHE_KEY
from ..models.pages.page import PAGE_CACHE_KEY_PREFIX

User = get_user_model()


class PageWorkflowTransitionTest(TestCase):
    """Test publishing workflow transitions on Page model."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.page = Page.objects.create(title="Test Page", slug="test-workflow")

    def test_initial_status_is_draft(self):
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

    # ========================
    # submit_for_review
    # ========================

    def test_submit_for_review_from_draft(self):
        """Draft -> Review transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "review")
        self.assertIsNotNone(self.page.submitted_for_review_at)
        self.assertEqual(self.page.submitted_for_review_by, self.user)
        self.assertFalse(self.page.published)

    def test_submit_for_review_from_review_raises(self):
        """Review -> Review transition is invalid."""
        self.page.submit_for_review(user=self.user)
        with self.assertRaises(ValueError) as ctx:
            self.page.submit_for_review(user=self.user)
        self.assertIn("Cannot submit for review", str(ctx.exception))

    def test_submit_for_review_from_published_raises(self):
        """Published -> Review transition is invalid."""
        self.page.status = "published"
        self.page.save()
        with self.assertRaises(ValueError):
            self.page.submit_for_review(user=self.user)

    # ========================
    # publish
    # ========================

    def test_publish_from_review(self):
        """Review -> Published transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)
        self.assertIsNotNone(self.page.published_at)
        self.assertEqual(self.page.published_by, self.user)

    def test_publish_directly_from_draft(self):
        """Draft -> Published transition succeeds (direct publish)."""
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)

    def test_publish_from_published_raises(self):
        """Published -> Published transition is invalid."""
        self.page.publish(user=self.user)
        with self.assertRaises(ValueError) as ctx:
            self.page.publish(user=self.user)
        self.assertIn("Cannot publish", str(ctx.exception))

    def test_publish_sets_published_at_only_once(self):
        """published_at is set on first publish and not overwritten."""
        self.page.publish(user=self.user)
        first_published_at = self.page.published_at

        # Unpublish and re-publish
        self.page.unpublish(user=self.user)
        self.page.publish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.published_at, first_published_at)

    # ========================
    # unpublish
    # ========================

    def test_unpublish_from_published(self):
        """Published -> Draft transition succeeds."""
        self.page.publish(user=self.user)
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

    def test_unpublish_from_review(self):
        """Review -> Draft transition succeeds."""
        self.page.submit_for_review(user=self.user)
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_unpublish_from_draft(self):
        """Draft -> Draft unpublish is a no-op (no error)."""
        self.page.unpublish(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    # ========================
    # reject_review
    # ========================

    def test_reject_review_from_review(self):
        """Review -> Draft via rejection."""
        self.page.submit_for_review(user=self.user)
        self.page.reject_review(user=self.user)
        self.page.refresh_from_db()
        self.assertEqual(self.page.status, "draft")

    def test_reject_review_from_draft_raises(self):
        """Cannot reject from draft status."""
        with self.assertRaises(ValueError) as ctx:
            self.page.reject_review(user=self.user)
        self.assertIn("Cannot reject", str(ctx.exception))

    def test_reject_review_from_published_raises(self):
        """Cannot reject from published status."""
        self.page.publish(user=self.user)
        with self.assertRaises(ValueError):
            self.page.reject_review(user=self.user)

    # ========================
    # Full workflow cycle
    # ========================

    def test_full_workflow_cycle(self):
        """Draft -> Review -> Published -> Draft -> Review -> Published."""
        # Draft -> Review
        self.page.submit_for_review(user=self.user)
        self.assertEqual(self.page.status, "review")

        # Review -> Published
        self.page.publish(user=self.user)
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)

        # Published -> Draft (unpublish)
        self.page.unpublish(user=self.user)
        self.assertEqual(self.page.status, "draft")
        self.assertFalse(self.page.published)

        # Draft -> Review again
        self.page.submit_for_review(user=self.user)
        self.assertEqual(self.page.status, "review")

        # Review -> Reject
        self.page.reject_review(user=self.user)
        self.assertEqual(self.page.status, "draft")

        # Draft -> Publish directly
        self.page.publish(user=self.user)
        self.assertEqual(self.page.status, "published")
        self.assertTrue(self.page.published)


class PageWorkflowVersionTest(TestCase):
    """Test that workflow transitions create version records."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.page = Page.objects.create(title="Version Page", slug="version-page")

    def test_submit_for_review_creates_version(self):
        initial_count = len(self.page.get_versions())
        self.page.submit_for_review(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)
        latest = versions[0]  # Most recent version
        self.assertIn("review", latest.comment.lower())

    def test_publish_creates_version(self):
        self.page.submit_for_review(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.publish(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)

    def test_unpublish_creates_version(self):
        self.page.publish(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.unpublish(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)

    def test_reject_review_creates_version(self):
        self.page.submit_for_review(user=self.user)
        initial_count = len(self.page.get_versions())
        self.page.reject_review(user=self.user)
        versions = self.page.get_versions()
        self.assertGreater(len(versions), initial_count)


class HomePageWorkflowTransitionTest(TestCase):
    """Test publishing workflow transitions on HomePage model."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.hp = HomePage.objects.create(name="Test Home")

    def test_initial_status_is_draft(self):
        self.assertEqual(self.hp.status, "draft")
        self.assertFalse(self.hp.published)
        self.assertFalse(self.hp.is_active)

    # ========================
    # submit_for_review
    # ========================

    def test_submit_for_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "review")
        self.assertIsNotNone(self.hp.submitted_for_review_at)
        self.assertEqual(self.hp.submitted_for_review_by, self.user)

    def test_submit_for_review_from_review_raises(self):
        self.hp.submit_for_review(user=self.user)
        with self.assertRaises(ValueError):
            self.hp.submit_for_review(user=self.user)

    # ========================
    # publish
    # ========================

    def test_publish_from_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.publish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "published")
        self.assertTrue(self.hp.published)
        self.assertIsNotNone(self.hp.published_at)

    def test_publish_directly_from_draft(self):
        self.hp.publish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "published")
        self.assertTrue(self.hp.published)

    def test_publish_from_published_raises(self):
        self.hp.publish(user=self.user)
        with self.assertRaises(ValueError):
            self.hp.publish(user=self.user)

    # ========================
    # unpublish (with is_active semantics)
    # ========================

    def test_unpublish_deactivates(self):
        """Unpublishing a home page also sets is_active=False."""
        self.hp.publish(user=self.user)
        # Manually activate
        self.hp.is_active = True
        self.hp.save()
        self.assertTrue(self.hp.is_active)

        self.hp.unpublish(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")
        self.assertFalse(self.hp.is_active)

    # ========================
    # reject_review
    # ========================

    def test_reject_review(self):
        self.hp.submit_for_review(user=self.user)
        self.hp.reject_review(user=self.user)
        self.hp.refresh_from_db()
        self.assertEqual(self.hp.status, "draft")

    def test_reject_review_from_draft_raises(self):
        with self.assertRaises(ValueError):
            self.hp.reject_review(user=self.user)

    # ========================
    # is_active validation
    # ========================

    def test_cannot_activate_draft(self):
        """Cannot set is_active=True on a draft home page."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Bad", status="draft", is_active=True)

    def test_cannot_activate_review(self):
        """Cannot set is_active=True on a home page in review."""
        with self.assertRaises(ValidationError):
            HomePage.objects.create(name="Bad", status="review", is_active=True)

    def test_can_activate_published(self):
        """Can set is_active=True on a published home page."""
        hp = HomePage.objects.create(name="Good", status="published", is_active=True)
        self.assertTrue(hp.is_active)

    def test_activate_deactivates_others(self):
        """Setting one home page active deactivates all others."""
        hp1 = HomePage.objects.create(name="HP1", status="published", is_active=True)
        hp2 = HomePage.objects.create(name="HP2", status="published", is_active=False)

        hp2.is_active = True
        hp2.save()

        hp1.refresh_from_db()
        hp2.refresh_from_db()
        self.assertFalse(hp1.is_active)
        self.assertTrue(hp2.is_active)


class HomePageWorkflowVersionTest(TestCase):
    """Test that HomePage workflow transitions create version records."""

    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="testpass123")
        self.hp = HomePage.objects.create(name="Version Home")

    def test_submit_for_review_creates_version(self):
        initial_count = len(self.hp.get_versions())
        self.hp.submit_for_review(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_publish_creates_version(self):
        self.hp.submit_for_review(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.publish(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_unpublish_creates_version(self):
        self.hp.publish(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.unpublish(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)

    def test_reject_creates_version(self):
        self.hp.submit_for_review(user=self.user)
        initial_count = len(self.hp.get_versions())
        self.hp.reject_review(user=self.user)
        self.assertGreater(len(self.hp.get_versions()), initial_count)


class PageCacheTest(TestCase):
    """Test Page model caching behavior."""

    def setUp(self):
        cache.clear()
        self.page = Page.objects.create(
            title="Cached Page", slug="cached-page", status="published"
        )

    def tearDown(self):
        cache.clear()

    def test_get_published_by_slug_populates_cache(self):
        """First call populates cache, second call returns cached version."""
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNone(cache.get(cache_key))

        result = Page.get_published_by_slug("cached-page")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.page.pk)

        # Verify it's in cache now
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.pk, self.page.pk)

    def test_get_published_by_slug_returns_none_for_draft(self):
        """Draft page is not returned by get_published_by_slug."""
        Page.objects.create(title="Draft", slug="draft-slug", status="draft")
        self.assertIsNone(Page.get_published_by_slug("draft-slug"))

    def test_get_published_by_slug_returns_none_for_nonexistent(self):
        """Nonexistent slug returns None."""
        self.assertIsNone(Page.get_published_by_slug("nonexistent"))

    def test_save_invalidates_cache(self):
        """Saving a page invalidates its cache entry."""
        # Populate cache
        Page.get_published_by_slug("cached-page")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNotNone(cache.get(cache_key))

        # Save page -> cache invalidated
        self.page.title = "Updated Title"
        self.page.save()
        self.assertIsNone(cache.get(cache_key))

    def test_delete_invalidates_cache(self):
        """Deleting a page invalidates its cache entry."""
        # Populate cache
        Page.get_published_by_slug("cached-page")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.cached-page"
        self.assertIsNotNone(cache.get(cache_key))

        # Delete page -> cache invalidated
        self.page.delete()
        self.assertIsNone(cache.get(cache_key))

    def test_publish_invalidates_cache(self):
        """Publishing a page invalidates cache (via save)."""
        draft = Page.objects.create(title="Draft", slug="draft-cache", status="draft")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.draft-cache"

        # Attempt to get (should return None and not cache)
        Page.get_published_by_slug("draft-cache")

        # Publish -> cache cleared
        draft.publish()
        # Now it should be findable
        result = Page.get_published_by_slug("draft-cache")
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, draft.pk)


class HomePageCacheTest(TestCase):
    """Test HomePage caching behavior."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_get_active_populates_cache(self):
        """First call populates cache."""
        hp = HomePage.objects.create(name="Active", status="published", is_active=True)
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

        result = HomePage.get_active()
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, hp.pk)

        # Verify cache populated
        cached = cache.get(HOMEPAGE_CACHE_KEY)
        self.assertIsNotNone(cached)

    def test_get_active_returns_none_for_draft(self):
        """Draft home page is not returned by get_active."""
        HomePage.objects.create(name="Draft", status="draft", is_active=False)
        self.assertIsNone(HomePage.get_active())

    def test_save_invalidates_cache(self):
        """Saving a home page invalidates cache."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        hp.name = "Updated"
        hp.save()
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_delete_invalidates_cache(self):
        """Deleting a home page invalidates cache."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        hp.delete()
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_unpublish_invalidates_cache(self):
        """Unpublishing clears cache and get_active returns None."""
        hp = HomePage.objects.create(name="Test", status="published", is_active=True)
        HomePage.get_active()  # Populate cache

        hp.unpublish()
        result = HomePage.get_active()
        self.assertIsNone(result)


class PageComponentCacheInvalidationTest(TestCase):
    """Test that saving a PageComponent invalidates parent cache."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_component_save_invalidates_page_cache(self):
        """Saving a component invalidates the parent Page cache."""
        page = Page.objects.create(title="Parent", slug="parent-page", status="published")
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.parent-page"

        # Populate cache
        Page.get_published_by_slug("parent-page")
        self.assertIsNotNone(cache.get(cache_key))

        # Create component -> parent cache invalidated
        PageComponent.objects.create(
            name="Comp", page=page, component_type="html", order=1, html_content="<p>Content</p>"
        )
        self.assertIsNone(cache.get(cache_key))

    def test_component_save_invalidates_homepage_cache(self):
        """Saving a component invalidates the parent HomePage cache."""
        hp = HomePage.objects.create(name="Home", status="published", is_active=True)

        # Populate cache
        HomePage.get_active()
        self.assertIsNotNone(cache.get(HOMEPAGE_CACHE_KEY))

        # Create component -> parent cache invalidated
        PageComponent.objects.create(
            name="HP Comp", home_page=hp, component_type="html", order=1, html_content="<p>Content</p>"
        )
        self.assertIsNone(cache.get(HOMEPAGE_CACHE_KEY))

    def test_component_update_invalidates_page_cache(self):
        """Updating a component invalidates the parent Page cache."""
        page = Page.objects.create(title="Parent", slug="parent-upd", status="published")
        comp = PageComponent.objects.create(
            name="Update Comp", page=page, component_type="html", order=1, html_content="<p>Old</p>"
        )
        cache_key = f"{PAGE_CACHE_KEY_PREFIX}.slug.parent-upd"

        # Populate cache
        Page.get_published_by_slug("parent-upd")
        self.assertIsNotNone(cache.get(cache_key))

        # Update component
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
