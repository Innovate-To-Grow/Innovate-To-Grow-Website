from django.contrib.admin.sites import AdminSite
from django.test import TestCase
from django.urls import reverse

from apps.cms.admin.cms.embed.widget import CMSEmbedWidgetAdmin, CMSEmbedWidgetAdminForm
from apps.cms.models import CMSBlock, CMSEmbedWidget, CMSPage
from apps.event.models import CurrentProjectSchedule


class CMSEmbedWidgetAdminDisplayTests(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        self.admin = CMSEmbedWidgetAdmin(CMSEmbedWidget, AdminSite())
        self.page = CMSPage.objects.create(slug="host", route="/host", title="Host Page", status="draft")
        self.schedule = CurrentProjectSchedule.objects.create(name="Demo Day")
        for i in range(2):
            CMSBlock.objects.create(page=self.page, block_type="rich_text", sort_order=i, data={})

    def test_form_init_seeds_app_route_initial_from_instance(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            slug="route-widget",
            app_route="/schedule",
        )
        form = CMSEmbedWidgetAdminForm(instance=widget)
        self.assertEqual(form.fields["app_route"].initial, "/schedule")

    def test_clean_returns_early_when_widget_type_missing(self):
        # Omitting widget_type yields cleaned widget_type None -> clean short-circuits.
        form = CMSEmbedWidgetAdminForm(
            data={
                "page": str(self.page.pk),
                "slug": "no-type",
                "admin_label": "",
                "block_sort_orders": "[0]",
                "app_route": "",
            }
        )
        # widget_type is required, so the form is invalid, but clean() still ran the
        # early-return branch and did not raise.
        self.assertFalse(form.is_valid())
        self.assertIn("widget_type", form.errors)
        # hidden_sections normalization was skipped (no hidden_sections error added).
        self.assertNotIn("hidden_sections", form.errors)

    def test_target_label_app_route_with_schedule(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            slug="sched-target",
            app_route="/schedule",
            schedule=self.schedule,
        )
        html = self.admin.target_label(widget)
        self.assertIn("/schedule", html)
        self.assertIn("Demo Day", html)

    def test_target_label_app_route_without_schedule(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            slug="news-target",
            app_route="/news",
        )
        html = self.admin.target_label(widget)
        self.assertIn("/news", html)
        self.assertIn("<code>", html)

    def test_target_label_blocks_widget_links_to_page(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="blocks-target", block_sort_orders=[0])
        html = self.admin.target_label(widget)
        self.assertIn("Host Page", html)
        self.assertIn(reverse("admin:cms_cmspage_change", args=[self.page.pk]), html)

    def test_target_label_blocks_widget_without_page_renders_dash(self):
        widget = CMSEmbedWidget(widget_type="blocks", slug="no-page")
        self.assertEqual(self.admin.target_label(widget), "—")

    def test_block_count_for_blocks_widget(self):
        widget = CMSEmbedWidget.objects.create(page=self.page, slug="count-blocks", block_sort_orders=[0, 1])
        self.assertEqual(self.admin.block_count(widget), 2)

    def test_block_count_for_app_route_widget(self):
        widget = CMSEmbedWidget.objects.create(
            widget_type="app_route",
            slug="count-app",
            app_route="/schedule",
        )
        self.assertEqual(self.admin.block_count(widget), "—")
