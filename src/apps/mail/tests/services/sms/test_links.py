"""SMS short links: what a token is (random, short, stored as a digest), who gets a personal one, and what opening
one does (a single sign-in, a counted redirect, or a refusal that says nothing about its owner)."""

from django.test import SimpleTestCase, override_settings

from apps.mail.redirects import is_strict_internal_path
from apps.mail.services.sms import links

PHONE = "+12095550101"


def token_of(url):
    return url.rsplit("/l/", 1)[1]


@override_settings(FRONTEND_URL="https://i2g.example.edu/")
class LinkShapeTests(SimpleTestCase):
    def test_a_link_is_the_short_path_and_a_128_bit_token(self):
        url = links.link_url("abc")
        self.assertEqual(url, "https://i2g.example.edu/l/abc")
        self.assertEqual(len(links.example_link()), len("https://i2g.example.edu/l/") + 22)

    def test_sign_in_paths_return_to_the_destination(self):
        self.assertEqual(links.sign_in_path("/account"), "/login")
        self.assertEqual(links.sign_in_path("/subscribe"), "/login?returnTo=/subscribe")
        self.assertEqual(
            links.sign_in_path("/event-registration?event=demo&x=1"),
            "/login?returnTo=/event-registration%3Fevent%3Ddemo%26x%3D1",
        )
        # A space is no page of this site (the SPA refuses it too).
        self.assertEqual(links.sign_in_path("/event-registration?event=demo day"), "/login")
        self.assertEqual(links.sign_in_path("//evil.example"), "/login")
        self.assertEqual(links.sign_in_path("/" + "x" * 300), "/login")

    def test_event_pages_quote_the_slug(self):
        event = type("Event", (), {"slug": "fall/2026 demo"})()
        self.assertEqual(links.event_page_path(event), "/event-registration?event=fall%2F2026%20demo")


class StrictPathTests(SimpleTestCase):
    def test_only_pages_of_this_site_pass(self):
        for path in ("/account", "/event-registration?event=fall-demo", "/login?returnTo=/subscribe"):
            with self.subTest(path=path):
                self.assertTrue(is_strict_internal_path(path))
        for path in (
            "",
            "account",
            "//evil.example",
            "/\\evil.example",
            "/a\\b",
            "/a b",
            "/a\tb",
            "/%2Fevil.example",
            "/x%5cy",
            "/x%0Ay",
            "https://evil.example",
            "/x\x7f",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_strict_internal_path(path))
        self.assertEqual(links.sign_in_path("/\\evil.example"), "/login")
