from django.test import TestCase

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
            "/projects/all/?page=2",
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
