from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage


class CMSBlockCleanTests(TestCase):
    def setUp(self):
        self.page = CMSPage.objects.create(slug="block-test", route="/block-test", title="Block Test", status="draft")

    def test_block_full_clean_valid(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=0, data={"heading": "Hello"})
        block.full_clean()

    def test_block_full_clean_invalid_data(self):
        block = CMSBlock(page=self.page, block_type="rich_text", sort_order=0, data={})
        with self.assertRaises(ValidationError):
            block.full_clean()

    def test_block_str_with_admin_label(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=1, admin_label="Main Banner")
        self.assertEqual(str(block), "Main Banner (#1)")

    def test_block_str_without_admin_label(self):
        block = CMSBlock(page=self.page, block_type="hero", sort_order=0)
        self.assertEqual(str(block), "Hero Banner (#0)")

    def test_block_delete_independent_of_page(self):
        b1 = CMSBlock.objects.create(page=self.page, block_type="hero", sort_order=0, data={})
        CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=1, data={"body_html": "<p>Hi</p>"})
        self.assertEqual(CMSBlock.objects.filter(page=self.page).count(), 2)

        b1.delete()
        self.assertEqual(CMSBlock.objects.filter(page=self.page).count(), 1)
