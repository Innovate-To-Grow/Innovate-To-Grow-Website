from django.core.exceptions import ValidationError

from apps.cms.models import CMSBlock, CMSEmbedWidget
from apps.cms.models.content.cms.block_types import (
    BLOCK_SCHEMAS,
    normalize_block_data_for_storage,
    validate_block_data,
)
from apps.cms.tests.models.blocks.test_embed_widget_block_validation import _EmbedWidgetBlockValidationCase
from apps.event.models import CurrentProjectSchedule


class EmbedWidgetBlockValidationTests(_EmbedWidgetBlockValidationCase):
    def test_embed_widget_accepts_aspect_ratio_without_height(self):
        validate_block_data(
            "embed_widget",
            {"slug": "schedule-embed", "aspect_ratio": "4:3"},
        )

    def test_embed_widget_accepts_positive_height_without_aspect_ratio(self):
        validate_block_data(
            "embed_widget",
            {"slug": "schedule-embed", "height": 720},
        )

    def test_embed_widget_height_upper_bound_enforced(self):
        validate_block_data("embed_widget", {"slug": "schedule-embed", "height": 5000})
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", {"slug": "schedule-embed", "height": 5001})

    def test_embed_widget_schedule_id_is_an_optional_schema_key(self):
        self.assertIn("schedule_id", BLOCK_SCHEMAS["embed_widget"]["optional"])

    def test_embed_widget_accepts_existing_schedule_id(self):
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        validate_block_data("embed_widget", {"slug": "schedule-embed", "schedule_id": str(schedule.pk)})

    def test_embed_widget_accepts_blank_schedule_id(self):
        validate_block_data("embed_widget", {"slug": "schedule-embed", "schedule_id": ""})
        validate_block_data("embed_widget", {"slug": "schedule-embed", "schedule_id": None})

    def test_embed_widget_rejects_unknown_schedule_id(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data(
                "embed_widget",
                {"slug": "schedule-embed", "schedule_id": "00000000-0000-0000-0000-000000000000"},
            )
        self.assertIn("No schedule found", str(ctx.exception))

    def test_embed_widget_rejects_malformed_schedule_id(self):
        schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        hex32 = schedule.pk.hex
        # Only the canonical hyphenated spelling is accepted — the SPA reads the
        # same shape off the iframe URL, and not every write path normalizes.
        for bad in ("not-a-uuid", 123, ["x"], {"id": "x"}, hex32, f"{{{schedule.pk}}}", f"urn:uuid:{schedule.pk}"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError) as ctx:
                validate_block_data("embed_widget", {"slug": "schedule-embed", "schedule_id": bad})
            self.assertIn("must be a schedule UUID", str(ctx.exception))

    def test_embed_widget_ignores_schedule_id_on_non_schedule_widget(self):
        # Mirrors CMSEmbedWidget._clean_schedule: a widget re-pointed away from a
        # schedule route must not make every page embedding it fail to save.
        schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        CMSEmbedWidget.objects.create(widget_type="app_route", app_route="/news", slug="news-embed")
        data = {"slug": "news-embed", "schedule_id": str(schedule.pk)}
        validate_block_data("embed_widget", data)
        self.assertNotIn("schedule_id", normalize_block_data_for_storage("embed_widget", data))

    def test_embed_widget_ignores_schedule_id_on_blocks_widget(self):
        schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        CMSEmbedWidget.objects.create(widget_type="blocks", page=self.page, slug="blocks-embed", block_sort_orders=[])
        data = {"slug": "blocks-embed", "schedule_id": str(schedule.pk)}
        validate_block_data("embed_widget", data)
        self.assertNotIn("schedule_id", normalize_block_data_for_storage("embed_widget", data))

    def test_embed_widget_validation_hits_the_schedule_table_once_per_block(self):
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        data = {"slug": "schedule-embed", "schedule_id": str(schedule.pk), "hidden_sections": ["schedule_header"]}
        with self.assertNumQueries(2):  # one widget lookup + one schedule existence check
            normalize_block_data_for_storage("embed_widget", data)

    def test_embed_widget_clean_canonicalizes_schedule_id_for_storage(self):
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        block = CMSBlock(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "schedule_id": f"  {str(schedule.pk).upper()}  "},
        )

        block.full_clean()

        self.assertEqual(block.data["schedule_id"], str(schedule.pk))

    def test_embed_widget_clean_drops_blank_schedule_id_for_storage(self):
        block = CMSBlock(
            page=self.page,
            block_type="embed_widget",
            sort_order=0,
            data={"slug": "schedule-embed", "schedule_id": ""},
        )

        block.full_clean()

        self.assertNotIn("schedule_id", block.data)

    def test_embed_widget_rejects_schedule_id_after_schedule_deleted(self):
        # Re-validation on the next page save must surface a dangling reference
        # rather than let the block keep pointing at a schedule that 404s.
        schedule = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        data = {"slug": "schedule-embed", "schedule_id": str(schedule.pk)}
        validate_block_data("embed_widget", data)
        schedule.delete()
        with self.assertRaises(ValidationError):
            validate_block_data("embed_widget", data)
