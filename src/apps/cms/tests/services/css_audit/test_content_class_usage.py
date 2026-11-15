from django.core.cache import cache
from django.test import TestCase

from apps.cms.models import CMSBlock, CMSPage, FooterContent
from apps.cms.services.styles.audit import (
    content_class_usage,
)


class ContentClassUsageTests(TestCase):
    def setUp(self):
        cache.clear()
        CMSPage.objects.all().delete()
        FooterContent.objects.all().delete()
        self.zeta = CMSPage.objects.create(slug="zeta", route="/zeta", title="Zeta")
        self.alpha = CMSPage.objects.create(slug="alpha", route="/alpha", title="Alpha")

    def test_lists_every_block_page_wrapper_and_active_footer(self):
        CMSBlock.objects.create(
            page=self.zeta, block_type="rich_text", sort_order=0, data={"body_html": "<p class=wrap>z</p>"}
        )
        CMSBlock.objects.create(
            page=self.alpha,
            block_type="faq_list",
            sort_order=1,
            data={"items": [{"answer_html": '<p class="wrap wrap">a</p>'}]},
        )
        CMSBlock.objects.create(
            page=self.alpha, block_type="rich_text", sort_order=0, data={"body_html": "<b class='wrap'>b</b>"}
        )
        self.zeta.page_css_class = "wrap  wrap"
        self.zeta.save()
        FooterContent.objects.create(
            name="Main", slug="main", content={"contact_html": "<b class=wrap>x</b>"}, is_active=True
        )

        usage = content_class_usage()

        # Blocks by route then sort order, then page wrappers, then footers; one use per place.
        self.assertEqual(
            usage["wrap"],
            [
                {"source": "block:rich_text", "where": "/alpha"},
                {"source": "block:faq_list", "where": "/alpha"},
                {"source": "block:rich_text", "where": "/zeta"},
                {"source": "page_css_class", "where": "/zeta"},
                {"source": "footer", "where": "footer:main"},
            ],
        )

    def test_blocks_of_every_page_status_are_scanned(self):
        for status in ("published", "archived"):
            page = CMSPage.objects.create(slug=status, route=f"/{status}", title=status, status=status)
            CMSBlock.objects.create(page=page, block_type="rich_text", data={"body_html": "<p class=any>x</p>"})
        CMSBlock.objects.create(page=self.zeta, block_type="rich_text", data={"body_html": "<p class=any>x</p>"})

        self.assertEqual([use["where"] for use in content_class_usage()["any"]], ["/archived", "/published", "/zeta"])

    def test_page_css_class_splits_like_the_frontend_wrapper(self):
        # cmsPageClassName() splits on JavaScript's \s, which includes the no-break space.
        self.alpha.page_css_class = "one\u00a0two\tthree"
        self.alpha.save()

        usage = content_class_usage()

        self.assertEqual(set(usage), {"one", "two", "three"})
        self.assertEqual(usage["two"], [{"source": "page_css_class", "where": "/alpha"}])

    def test_footer_contact_and_column_html(self):
        FooterContent.objects.create(
            name="Main footer",
            slug="main",
            is_active=True,
            content={
                "contact_html": '<p class="footer-contact">UC Merced</p>',
                "columns": [{"title": "Links", "body_html": "<ul class=footer-list><li>x</li></ul>"}],
                "copyright": '<span class="not-html-key">c</span>',
            },
        )

        usage = content_class_usage()

        self.assertEqual(usage["footer-contact"], [{"source": "footer", "where": "footer:main"}])
        self.assertEqual(usage["footer-list"], [{"source": "footer", "where": "footer:main"}])
        self.assertNotIn("not-html-key", usage)

    def test_inactive_footers_are_not_scanned(self):
        FooterContent.objects.create(
            name="Old", slug="old", content={"contact_html": "<p class='shared only-old'>a</p>"}, is_active=False
        )
        FooterContent.objects.create(
            name="New", slug="new", content={"contact_html": "<p class=shared>b</p>"}, is_active=True
        )

        usage = content_class_usage()

        self.assertEqual(dict(usage), {"shared": [{"source": "footer", "where": "footer:new"}]})

    def test_no_active_footer_means_no_footer_uses(self):
        FooterContent.objects.create(name="Old", slug="old", content={"contact_html": "<p class=old>a</p>"})
        self.assertEqual(dict(content_class_usage()), {})

    def test_nothing_stored(self):
        self.assertEqual(dict(content_class_usage()), {})
