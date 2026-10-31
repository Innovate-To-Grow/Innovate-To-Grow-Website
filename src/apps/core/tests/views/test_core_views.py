import json
from datetime import UTC, datetime
from xml.etree import ElementTree

from django.test import RequestFactory, TestCase
from django.test.utils import override_settings

from apps.cms.models import CMSBlock, CMSPage
from apps.core.views import custom_404
from apps.projects.models import Project, Semester

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
APP_ROUTE_LOCATIONS = [
    "https://i2g.ucmerced.edu/news",
    "https://i2g.ucmerced.edu/schedule",
    "https://i2g.ucmerced.edu/current-projects",
    "https://i2g.ucmerced.edu/presenting-teams",
    "https://i2g.ucmerced.edu/past-projects",
    "https://i2g.ucmerced.edu/all-projects",
]


class RobotsTxtTest(TestCase):
    def test_returns_text_plain(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_disallows_everything_else(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        self.assertIn("User-agent: *", content)
        self.assertEqual(content.splitlines()[-1], "Disallow: /")

    def test_allows_the_reads_public_pages_render_from(self):
        rules = self._rules()

        for path in (
            "/layout/",
            "/health/",
            "/cms/pages/about/",
            "/cms/embed-hosts/",
            "/event/schedule/",
            "/projects/archive/?page=2",
            "/projects/5970763b-cf7c-40d6-a87c-96916e0ea695/",
        ):
            with self.subTest(path=path):
                self.assertTrue(self._allowed(rules, path))

    def test_keeps_private_and_unused_endpoints_out(self):
        rules = self._rules()

        for path in (
            "/admin/",
            "/authn/profile/",
            "/assistant/chat/",
            "/projects/past-shares/0f0f0f0f-1111-4222-8333-444444444444/",
            "/projects/past-ai-search/",
            "/projects/past-all/",
            "/projects/past/?page=2",
        ):
            with self.subTest(path=path):
                self.assertFalse(self._allowed(rules, path))

    def test_first_matching_rule_reads_the_same_as_the_longest(self):
        rules = self._rules()

        for path in (
            "/projects/archive/",
            "/projects/5970763b-cf7c-40d6-a87c-96916e0ea695/",
            "/projects/past-shares/0f0f0f0f-1111-4222-8333-444444444444/",
            "/projects/past-ai-search/",
            "/projects/past-all/",
            "/projects/past/?page=2",
            "/admin/",
        ):
            with self.subTest(path=path):
                first_match = next((allow for allow, prefix in rules if path.startswith(prefix)), True)
                self.assertEqual(first_match, self._allowed(rules, path))

    def _rules(self):
        content = self.client.get("/robots.txt").content.decode()
        rules = []
        for line in content.splitlines():
            directive, _, value = line.partition(": ")
            if directive in {"Allow", "Disallow"}:
                rules.append((directive == "Allow", value))
        return rules

    @staticmethod
    def _allowed(rules, path):
        # Google's precedence: the longest matching rule wins, and Allow wins a tie.
        matches = [(len(prefix), allow) for allow, prefix in rules if path.startswith(prefix)]
        return max(matches)[1] if matches else True


def failing_sitemap_provider():
    raise RuntimeError("provider down")


@override_settings(FRONTEND_URL="https://i2g.ucmerced.edu")
class SitemapXmlTest(TestCase):
    def setUp(self):
        # Migration cms.0023 seeds the /acknowledgement page; these tests start from no CMS pages.
        CMSPage.objects.all().delete()

    def sitemap_locations(self, response):
        root = ElementTree.fromstring(response.content)
        return [node.text for node in root.findall(f"{SITEMAP_NS}url/{SITEMAP_NS}loc")]

    def test_returns_valid_xml(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
        root = ElementTree.fromstring(response.content)
        self.assertEqual(root.tag, f"{SITEMAP_NS}urlset")

    def test_includes_published_cms_pages_with_frontend_urls(self):
        CMSPage.objects.create(slug="home", route="/", title="Home", status="published")
        CMSPage.objects.create(slug="about", route="/about", title="About", status="published")

        response = self.client.get("/sitemap.xml")

        self.assertEqual(
            self.sitemap_locations(response),
            [
                "https://i2g.ucmerced.edu/",
                "https://i2g.ucmerced.edu/about",
                *APP_ROUTE_LOCATIONS,
            ],
        )

    def test_excludes_unpublished_cms_pages(self):
        CMSPage.objects.create(slug="published", route="/published", title="Published", status="published")
        CMSPage.objects.create(slug="draft", route="/draft", title="Draft", status="draft")
        CMSPage.objects.create(slug="archived", route="/archived", title="Archived", status="archived")

        response = self.client.get("/sitemap.xml")

        self.assertEqual(self.sitemap_locations(response), ["https://i2g.ucmerced.edu/published", *APP_ROUTE_LOCATIONS])

    def test_uses_latest_block_update_for_lastmod(self):
        old = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        new = datetime(2026, 1, 2, 15, 30, 45, tzinfo=UTC)
        page = CMSPage.objects.create(slug="content", route="/content", title="Content", status="published")
        block = CMSBlock.objects.create(page=page, block_type="hero", sort_order=0, data={})
        CMSPage.objects.filter(pk=page.pk).update(published_at=old, updated_at=old)
        CMSBlock.objects.filter(pk=block.pk).update(updated_at=new)

        response = self.client.get("/sitemap.xml")

        self.assertIn("<lastmod>2026-01-02T15:30:45Z</lastmod>", response.content.decode())

    def test_app_route_with_a_cms_page_is_listed_once(self):
        CMSPage.objects.create(slug="news", route="/news", title="News", status="published")

        locations = self.sitemap_locations(self.client.get("/sitemap.xml"))

        self.assertEqual(locations.count("https://i2g.ucmerced.edu/news"), 1)

    def test_lists_published_archive_projects_with_lastmod(self):
        published = Semester.objects.create(year=2025, season=1, is_published=True)
        hidden = Semester.objects.create(year=2026, season=1, is_published=False)
        project = Project.objects.create(semester=published, project_title="Solar Kiln", team_number="1")
        hidden_project = Project.objects.create(semester=hidden, project_title="Hidden", team_number="2")
        Project.objects.filter(pk=project.pk).update(updated_at=datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC))

        response = self.client.get("/sitemap.xml")

        content = response.content.decode()
        self.assertIn(
            f"<loc>https://i2g.ucmerced.edu/past-projects/project/{project.pk}</loc>\n"
            "    <lastmod>2026-03-04T05:06:07Z</lastmod>",
            content,
        )
        self.assertNotIn(str(hidden_project.pk), content)

    @override_settings(SITEMAP_ENTRY_PROVIDERS=("apps.core.tests.views.test_core_views.failing_sitemap_provider",))
    def test_a_failing_provider_leaves_the_rest_of_the_sitemap(self):
        with self.assertLogs("apps.cms.views.sitemap", level="ERROR"):
            response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sitemap_locations(response), APP_ROUTE_LOCATIONS)

    def test_without_pages_lists_only_the_app_routes(self):
        response = self.client.get("/sitemap.xml")
        root = ElementTree.fromstring(response.content)
        self.assertEqual(root.tag, f"{SITEMAP_NS}urlset")
        self.assertEqual(self.sitemap_locations(response), APP_ROUTE_LOCATIONS)


class CanonicalFrontendBaseTest(TestCase):
    def test_falls_back_to_request_host_when_no_frontend_url(self):
        from apps.cms.views.sitemap import _canonical_frontend_base

        request = RequestFactory().get("/sitemap.xml")
        with override_settings(FRONTEND_URL=""):
            base = _canonical_frontend_base(request)
        # build_absolute_uri("/") on testserver, trailing slash stripped.
        self.assertEqual(base, "http://testserver")

    def test_sitemap_uses_request_host_without_frontend_url(self):
        CMSPage.objects.create(slug="home", route="/", title="Home", status="published")
        with override_settings(FRONTEND_URL=""):
            response = self.client.get("/sitemap.xml")
        self.assertIn("<loc>http://testserver/</loc>", response.content.decode())


class SitemapLastmodTest(TestCase):
    def test_returns_empty_when_no_timestamps(self):
        from apps.cms.views.sitemap import _sitemap_lastmod

        class _FakePage:
            updated_at = None
            published_at = None
            latest_block_updated_at = None

        self.assertEqual(_sitemap_lastmod(_FakePage()), "")


class Custom404Test(TestCase):
    def test_returns_404_status(self):
        factory = RequestFactory()
        request = factory.get("/nonexistent")
        response = custom_404(request, exception=None)
        self.assertEqual(response.status_code, 404)

    def test_unknown_api_path_returns_json(self):
        request = RequestFactory().get("/projects/no-such-endpoint/")
        response = custom_404(request, exception=None)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content), {"detail": "Not found."})

    def test_unknown_admin_path_keeps_the_admin_page(self):
        request = RequestFactory().get("/admin/no-such-page/")
        response = custom_404(request, exception=None)
        self.assertEqual(response.status_code, 404)
        self.assertIn("text/html", response["Content-Type"])


class RootIndexTest(TestCase):
    def test_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
