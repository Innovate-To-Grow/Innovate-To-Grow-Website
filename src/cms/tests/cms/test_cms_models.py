from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from cms.models import CMSBlock, CMSPage


class CMSPageModelTest(TestCase):
    # noinspection PyPep8Naming,PyMethodMayBeStatic
    def setUp(self):
        cache.clear()

    def test_create_page_with_blocks(self):
        page = CMSPage.objects.create(
            slug="test-page",
            route="/test-page",
            title="Test Page",
            status="published",
        )
        block = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"heading": "Hello", "body_html": "<p>World</p>"},
        )
        self.assertEqual(page.blocks.count(), 1)
        self.assertEqual(block.block_type, "rich_text")

    def test_route_is_normalized_on_save(self):
        page = CMSPage.objects.create(
            slug="normalized-route",
            route="//event//live/",
            title="Normalized Route",
            status="draft",
        )
        self.assertEqual(page.route, "/event/live")

    def test_route_rejects_invalid_segments(self):
        page = CMSPage(slug="bad-route", route="/bad route", title="Bad Route")
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_published_at_auto_set(self):
        page = CMSPage.objects.create(
            slug="pub-test",
            route="/pub-test",
            title="Pub Test",
            status="published",
        )
        self.assertIsNotNone(page.published_at)

    def test_draft_no_published_at(self):
        page = CMSPage.objects.create(
            slug="draft-test",
            route="/draft-test",
            title="Draft Test",
            status="draft",
        )
        self.assertIsNone(page.published_at)

    def test_block_validation_missing_required(self):
        page = CMSPage.objects.create(
            slug="val-test",
            route="/val-test",
            title="Val Test",
            status="draft",
        )
        block = CMSBlock(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={},  # missing body_html
        )
        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_delete(self):
        page = CMSPage.objects.create(
            slug="soft-del",
            route="/soft-del",
            title="Soft Del",
            status="published",
        )
        page.delete()
        self.assertEqual(CMSPage.objects.filter(slug="soft-del").count(), 0)
