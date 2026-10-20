import importlib

from django.apps import apps as global_apps
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.cms.models import CMSBlock, CMSPage
from apps.cms.models.content.cms.block_types import validate_block_data
from apps.cms.services.routing.route_redirects import page_route_conflicts

migration = importlib.import_module("apps.cms.migrations.0023_acknowledgement_cms_page")


class AcknowledgementPageMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        # The test database already ran the migration; start each test without the page.
        CMSPage.objects.filter(route=migration.ROUTE).delete()

    def test_the_route_belongs_to_the_cms(self):
        _, conflicts = page_route_conflicts(migration.ROUTE)
        self.assertEqual(conflicts, [])

    def test_seeded_blocks_pass_block_validation(self):
        for block in migration.BLOCKS:
            try:
                validate_block_data(block["block_type"], block["data"])
            except ValidationError as exc:  # pragma: no cover - the assertion message is the point
                self.fail(f"{block['admin_label']}: {exc}")

    def test_creates_the_published_page_served_by_the_cms_api(self):
        migration.create_page(global_apps, None)

        page = CMSPage.objects.get(route=migration.ROUTE)
        self.assertEqual((page.slug, page.title, page.status), ("acknowledgement", "Partners & Sponsors", "published"))
        self.assertIsNotNone(page.published_at)
        self.assertEqual(
            list(page.blocks.values_list("block_type", flat=True)),
            ["rich_text", "rich_text", "cta_group", "rich_text"],
        )

        response = APIClient().get("/cms/pages/acknowledgement/")
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["title"], "Partners & Sponsors")
        self.assertEqual(body["blocks"][0]["data"]["heading_level"], 1)
        self.assertIn("i2g@ucmerced.edu", body["blocks"][3]["data"]["body_html"])

    def test_leaves_an_existing_page_alone(self):
        page = CMSPage.objects.create(slug="sponsors", route=migration.ROUTE, title="Our sponsors", status="draft")

        migration.create_page(global_apps, None)

        self.assertEqual(CMSPage.objects.filter(route=migration.ROUTE).count(), 1)
        page.refresh_from_db()
        self.assertEqual(page.title, "Our sponsors")
        self.assertFalse(page.blocks.exists())

    def test_reverse_removes_the_page_only_while_unchanged(self):
        migration.create_page(global_apps, None)
        migration.remove_page(global_apps, None)
        self.assertFalse(CMSPage.objects.filter(route=migration.ROUTE).exists())

        migration.create_page(global_apps, None)
        page = CMSPage.objects.get(route=migration.ROUTE)
        CMSBlock.objects.create(
            page=page,
            block_type="sponsor_year",
            sort_order=1,
            data={"year": "2026", "sponsors": [{"name": "Acme"}]},
        )
        migration.remove_page(global_apps, None)
        self.assertTrue(CMSPage.objects.filter(route=migration.ROUTE).exists())
