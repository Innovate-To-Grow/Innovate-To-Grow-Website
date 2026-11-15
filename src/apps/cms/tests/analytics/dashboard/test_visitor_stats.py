from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.cms.admin.analytics.page_view.admin import PageViewAdmin
from apps.cms.admin.analytics.page_view.stats import compute_dashboard_stats
from apps.cms.models import PageView
from apps.cms.services.analytics import flush_sync
from apps.cms.tests.analytics.pageviews.test_pageview_visitor import CAMPUS_IP, Member


class VisitorStatsTests(TestCase):
    def setUp(self):
        cache.clear()
        flush_sync()
        PageView.objects.all().delete()

    @staticmethod
    def daily_visitors(stats):
        """The non-empty days of the seven-day visitor series, oldest first."""
        return [count for count in stats["last_7_days_visitors"] if count]

    def test_campus_visitors_behind_one_ip_are_counted_separately(self):
        for visitor in ("visitor-a", "visitor-a", "visitor-b", "visitor-c", "visitor-c"):
            PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id=visitor)

        stats = compute_dashboard_stats()

        self.assertEqual(stats["total_views"], 5)
        self.assertEqual(stats["unique_visitors"], 3)
        self.assertEqual(self.daily_visitors(stats), [3])

    def test_rows_without_a_visitor_id_keep_counting_by_ip(self):
        # Recorded before the frontend sent an id: two addresses, three rows.
        PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.create(path="/", ip_address="198.51.100.2")
        # New rows: two campus visitors behind one address, one of them twice.
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-b")
        # One visitor seen from two networks is still one visitor.
        PageView.objects.create(path="/", ip_address="203.0.113.9", visitor_id="visitor-b")

        stats = compute_dashboard_stats()

        self.assertEqual(stats["unique_visitors"], 4)
        self.assertEqual(self.daily_visitors(stats), [4])

    def test_a_row_with_neither_id_nor_ip_is_not_a_visitor(self):
        PageView.objects.create(path="/", ip_address=None)
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="visitor-a")

        stats = compute_dashboard_stats()

        self.assertEqual(stats["total_views"], 2)
        self.assertEqual(stats["unique_visitors"], 1)

    def test_daily_visitors_use_the_same_key(self):
        now = timezone.now()
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="today-a")
        PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id="today-b")
        for visitor in ("old-a", "old-b", "old-c"):
            older = PageView.objects.create(path="/", ip_address=CAMPUS_IP, visitor_id=visitor)
            PageView.objects.filter(pk=older.pk).update(timestamp=now - timedelta(days=2))
        legacy = PageView.objects.create(path="/", ip_address="198.51.100.1")
        PageView.objects.filter(pk=legacy.pk).update(timestamp=now - timedelta(days=2))

        stats = compute_dashboard_stats()

        self.assertEqual(self.daily_visitors(stats), [4, 2])
        self.assertEqual(stats["unique_visitors"], 6)


class VisitorAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        flush_sync()
        PageView.objects.all().delete()
        self.admin_user = Member.objects.create_superuser(password="testpass123", first_name="A", last_name="Admin")
        ContactEmail.objects.create(
            member=self.admin_user, email_address="visitor-admin@example.com", email_type="primary", verified=True
        )
        self.client.login(username="visitor-admin@example.com", password="testpass123")

    def test_the_detail_page_shows_the_visitor_id_next_to_the_ip_address(self):
        page_view = PageView.objects.create(
            path="/about", ip_address=CAMPUS_IP, visitor_id="3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f"
        )

        response = self.client.get(reverse("admin:cms_pageview_change", args=[page_view.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3f2b8c1e-5d4a-4f6b-9c7d-0a1b2c3d4e5f")
        self.assertContains(response, CAMPUS_IP)
        visitor_fields = dict(PageViewAdmin.fieldsets)["Visitor"]["fields"]
        self.assertEqual(visitor_fields.index("visitor_id"), visitor_fields.index("ip_address") + 1)
        self.assertIn("visitor_id", PageViewAdmin.readonly_fields)

    def test_page_views_can_be_searched_by_visitor_id(self):
        PageView.objects.create(path="/wanted", ip_address=CAMPUS_IP, visitor_id="visitor-wanted")
        PageView.objects.create(path="/other", ip_address=CAMPUS_IP, visitor_id="visitor-other")

        response = self.client.get(reverse("admin:cms_pageview_changelist"), {"q": "visitor-wanted"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row.path for row in response.context["cl"].result_list], ["/wanted"])
