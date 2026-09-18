from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, RouteRedirect
from apps.cms.services.pages import duplicate_page


class DuplicatePageTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.page = CMSPage.objects.create(
            slug="fall-event",
            route="/fall-event",
            title="Fall Event",
            meta_description="Fall event details",
            page_css_class="event-page",
            page_css=".event-page h1 { color: red; }",
            sort_order=7,
            status="published",
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=1,
            admin_label="Body",
            data={"body_html": "<p>Body</p>"},
        )
        CMSBlock.objects.create(
            page=self.page,
            block_type="rich_text",
            sort_order=0,
            admin_label="Intro",
            data={"heading": "Hi", "body_html": "<p>Intro</p>"},
        )

    def test_copies_fields_and_blocks_as_a_new_draft(self):
        copy = duplicate_page(self.page)

        self.assertNotEqual(copy.pk, self.page.pk)
        self.assertEqual(copy.slug, "fall-event-copy")
        self.assertEqual(copy.route, "/fall-event-copy")
        self.assertEqual(copy.title, "Fall Event (Copy)")
        self.assertEqual(copy.meta_description, self.page.meta_description)
        self.assertEqual(copy.page_css_class, self.page.page_css_class)
        self.assertEqual(copy.page_css, self.page.page_css)
        self.assertEqual(copy.sort_order, self.page.sort_order)
        self.assertEqual(copy.status, "draft")
        self.assertIsNone(copy.published_at)

        copied_blocks = list(copy.blocks.order_by("sort_order"))
        self.assertEqual(
            [(b.block_type, b.sort_order, b.admin_label, b.data) for b in copied_blocks],
            [
                ("rich_text", 0, "Intro", {"heading": "Hi", "body_html": "<p>Intro</p>"}),
                ("rich_text", 1, "Body", {"body_html": "<p>Body</p>"}),
            ],
        )
        self.assertFalse({b.pk for b in copied_blocks} & set(self.page.blocks.values_list("pk", flat=True)))

    def test_source_page_and_blocks_are_untouched(self):
        duplicate_page(self.page)

        self.page.refresh_from_db()
        self.assertEqual(self.page.slug, "fall-event")
        self.assertEqual(self.page.route, "/fall-event")
        self.assertEqual(self.page.status, "published")
        self.assertEqual(self.page.blocks.count(), 2)
        self.assertEqual(CMSPage.objects.count(), 2)
        self.assertEqual(CMSBlock.objects.count(), 4)

    def test_repeated_duplication_increments_suffix(self):
        first = duplicate_page(self.page)
        second = duplicate_page(self.page)
        third = duplicate_page(first)

        self.assertEqual(
            (first.slug, first.route, first.title), ("fall-event-copy", "/fall-event-copy", "Fall Event (Copy)")
        )
        self.assertEqual(
            (second.slug, second.route, second.title),
            ("fall-event-copy-2", "/fall-event-copy-2", "Fall Event (Copy 2)"),
        )
        self.assertEqual(
            (third.slug, third.route, third.title),
            ("fall-event-copy-copy", "/fall-event-copy-copy", "Fall Event (Copy) (Copy)"),
        )

    def test_skips_suffix_when_only_the_route_is_taken(self):
        CMSPage.objects.create(slug="other", route="/fall-event-copy", title="Other", status="draft")

        copy = duplicate_page(self.page)

        self.assertEqual(copy.slug, "fall-event-copy-2")
        self.assertEqual(copy.route, "/fall-event-copy-2")

    def test_skips_suffix_when_only_the_slug_is_taken(self):
        CMSPage.objects.create(slug="fall-event-copy", route="/elsewhere", title="Other", status="draft")

        copy = duplicate_page(self.page)

        self.assertEqual(copy.slug, "fall-event-copy-2")
        self.assertEqual(copy.route, "/fall-event-copy-2")

    def test_skips_route_owned_by_a_redirect(self):
        RouteRedirect.objects.create(source_path="/fall-event-copy", destination_path="/fall-event", is_active=True)

        copy = duplicate_page(self.page)

        self.assertEqual(copy.route, "/fall-event-copy-2")

    def test_nested_route_suffixes_last_segment_only(self):
        page = CMSPage.objects.create(slug="nested", route="/events/2026/fall", title="Nested", status="draft")

        copy = duplicate_page(page)

        self.assertEqual(copy.route, "/events/2026/fall-copy")

    def test_root_route_falls_back_to_slug(self):
        home = CMSPage.objects.create(slug="home", route="/", title="Home", status="published")

        copy = duplicate_page(home)

        self.assertEqual(copy.slug, "home-copy")
        self.assertEqual(copy.route, "/home-copy")

    def test_long_values_are_trimmed_to_fit_max_length(self):
        long_slug = "s" * 200
        page = CMSPage.objects.create(slug=long_slug, route=f"/{'r' * 199}", title="t" * 300, status="draft")

        copy = duplicate_page(page)

        self.assertEqual(len(copy.slug), 200)
        self.assertTrue(copy.slug.endswith("-copy"))
        self.assertEqual(len(copy.route), 200)
        self.assertTrue(copy.route.endswith("-copy"))
        self.assertEqual(len(copy.title), 300)
        self.assertTrue(copy.title.endswith(" (Copy)"))

    def test_unfixable_route_conflict_raises_without_creating_anything(self):
        # Reserved prefixes stay reserved no matter which "-copy-N" suffix is tried.
        page = CMSPage.objects.create(slug="legacy-admin", route="/admin/legacy", title="Legacy", status="draft")

        with self.assertRaises(ValidationError) as ctx:
            duplicate_page(page)

        self.assertIn("reserved", " ".join(ctx.exception.messages))
        self.assertFalse(CMSPage.objects.filter(slug="legacy-admin-copy").exists())

    def test_copy_is_not_created_when_a_block_write_fails(self):
        CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=2, data={"body_html": "<p>x</p>"})
        original_create = CMSBlock.objects.create
        calls = {"count": 0}

        def failing_create(**kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("boom")
            return original_create(**kwargs)

        from unittest.mock import patch

        with patch.object(CMSBlock.objects, "create", side_effect=failing_create), self.assertRaises(RuntimeError):
            duplicate_page(self.page)

        self.assertFalse(CMSPage.objects.filter(slug="fall-event-copy").exists())
        self.assertEqual(CMSBlock.objects.count(), 3)
