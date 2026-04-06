"""Tests for CMS block type validation across all 13 block types."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from cms.models import CMSBlock, CMSPage
from cms.models.content.cms.block_types import BLOCK_SCHEMAS, BLOCK_TYPE_KEYS, validate_block_data


class ValidateBlockDataTests(TestCase):
    def test_unknown_block_type_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("nonexistent", {})
        self.assertIn("Unknown block type", str(ctx.exception))

    def test_hero_valid_empty_data(self):
        """Hero has no required fields."""
        validate_block_data("hero", {})

    def test_hero_valid_with_optional_fields(self):
        validate_block_data("hero", {"heading": "Welcome", "subheading": "Hello", "image_url": "/img.jpg"})

    def test_rich_text_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("rich_text", {})

    def test_rich_text_valid(self):
        validate_block_data("rich_text", {"body_html": "<p>Content</p>"})

    def test_faq_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("faq_list", {})

    def test_faq_list_valid(self):
        validate_block_data("faq_list", {"items": [{"question": "Q1", "answer": "A1"}]})

    def test_link_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("link_list", {})

    def test_cta_group_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("cta_group", {})

    def test_image_text_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("image_text", {})

    def test_image_text_valid(self):
        validate_block_data("image_text", {"body_html": "<p>Text</p>", "image_url": "/img.jpg"})

    def test_notice_requires_body_html(self):
        with self.assertRaises(ValidationError):
            validate_block_data("notice", {})

    def test_contact_info_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("contact_info", {})

    def test_section_group_requires_sections(self):
        with self.assertRaises(ValidationError):
            validate_block_data("section_group", {})

    def test_table_requires_columns_and_rows(self):
        with self.assertRaises(ValidationError):
            validate_block_data("table", {})
        with self.assertRaises(ValidationError):
            validate_block_data("table", {"columns": ["Name"]})

    def test_table_valid(self):
        validate_block_data("table", {"columns": ["Name", "Value"], "rows": [["A", "1"]]})

    def test_numbered_list_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("numbered_list", {})

    def test_proposal_cards_requires_proposals(self):
        with self.assertRaises(ValidationError):
            validate_block_data("proposal_cards", {})

    def test_navigation_grid_requires_items(self):
        with self.assertRaises(ValidationError):
            validate_block_data("navigation_grid", {})

    def test_sponsor_year_requires_year_and_sponsors(self):
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {})
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {"year": "", "sponsors": []})
        with self.assertRaises(ValidationError):
            validate_block_data("sponsor_year", {"year": "2025", "sponsors": [{}]})

    def test_sponsor_year_valid(self):
        validate_block_data(
            "sponsor_year",
            {
                "year": "2025",
                "sponsors": [
                    {
                        "name": "Acme Labs",
                        "logo_url": "/media/cms/assets/acme.svg",
                        "website": "https://example.com",
                    }
                ],
            },
        )

    def test_all_block_types_have_schemas(self):
        """Every block type in BLOCK_TYPE_KEYS must have a corresponding schema."""
        for key in BLOCK_TYPE_KEYS:
            self.assertIn(key, BLOCK_SCHEMAS, f"Missing schema for block type '{key}'")


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
