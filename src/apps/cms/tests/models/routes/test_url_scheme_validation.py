from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.cms.models import CMSEmbedAllowedHost
from apps.cms.models.content.cms.block_types import (
    validate_block_data,
)
from apps.cms.services.sanitization.embed_hosts import invalidate_cache as invalidate_embed_host_cache


class URLSchemeValidationTests(TestCase):
    """Tests for javascript:/data: URL rejection in link_list, navigation_grid, contact_info blocks."""

    def test_link_list_rejects_javascript_url(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("link_list", {"items": [{"label": "XSS", "url": "javascript:alert(1)"}]})
        self.assertIn("unsafe scheme", str(ctx.exception))

    def test_link_list_rejects_data_url(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "link_list", {"items": [{"label": "XSS", "url": "data:text/html,<script>alert(1)</script>"}]}
            )

    def test_link_list_accepts_safe_urls(self):
        safe_items = [
            {"label": "HTTPS", "url": "https://example.com"},
            {"label": "HTTP", "url": "http://example.com"},
            {"label": "Relative", "url": "/about"},
            {"label": "Fragment", "url": "#section"},
            {"label": "Mailto", "url": "mailto:test@example.com"},
            {"label": "Tel", "url": "tel:+1234567890"},
            {"label": "DotRelative", "url": "./page"},
        ]
        validate_block_data("link_list", {"items": safe_items})

    def test_navigation_grid_rejects_javascript_url(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("navigation_grid", {"items": [{"title": "XSS", "url": "javascript:alert(1)"}]})
        self.assertIn("unsafe scheme", str(ctx.exception))

    def test_navigation_grid_accepts_safe_urls(self):
        validate_block_data("navigation_grid", {"items": [{"title": "Safe", "url": "https://example.com"}]})

    def test_contact_info_url_type_rejects_javascript(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data(
                "contact_info", {"items": [{"label": "Site", "type": "url", "value": "javascript:alert(1)"}]}
            )
        self.assertIn("unsafe scheme", str(ctx.exception))

    def test_contact_info_url_type_accepts_safe_urls(self):
        validate_block_data(
            "contact_info", {"items": [{"label": "Site", "type": "url", "value": "https://example.com"}]}
        )

    def test_contact_info_email_type_skips_url_validation(self):
        validate_block_data(
            "contact_info", {"items": [{"label": "Email", "type": "email", "value": "test@example.com"}]}
        )

    def test_contact_info_phone_type_skips_url_validation(self):
        validate_block_data("contact_info", {"items": [{"label": "Phone", "type": "phone", "value": "+1234567890"}]})


class EmbedBlockValidationTests(TestCase):
    def setUp(self):
        CMSEmbedAllowedHost.objects.all().delete()
        CMSEmbedAllowedHost.objects.create(hostname="docs.google.com")
        CMSEmbedAllowedHost.objects.create(hostname="*.youtube.com")
        invalidate_embed_host_cache()

    def tearDown(self):
        invalidate_embed_host_cache()

    def test_embed_requires_src(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {})

    def test_embed_rejects_non_https(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed", {"src": "http://docs.google.com/forms/d/e/xyz/viewform"})
        self.assertIn("https", str(ctx.exception))

    def test_embed_rejects_disallowed_host(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_block_data("embed", {"src": "https://evil.example.com/widget"})
        self.assertIn("allowlist", str(ctx.exception))

    def test_embed_allows_exact_host(self):
        validate_block_data("embed", {"src": "https://docs.google.com/forms/d/e/xyz/viewform"})

    def test_embed_wildcard_matches_subdomain(self):
        validate_block_data("embed", {"src": "https://www.youtube.com/embed/abc123"})

    def test_embed_wildcard_does_not_match_sibling_domain(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://fakeyoutube.com/embed/abc"})

    def test_embed_bad_aspect_ratio_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "embed",
                {"src": "https://docs.google.com/a", "aspect_ratio": "sixteen-by-nine"},
            )

    def test_embed_invalid_height_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": "tall"})
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": -10})

    def test_embed_unknown_sandbox_token_rejected(self):
        with self.assertRaises(ValidationError):
            validate_block_data(
                "embed",
                {"src": "https://docs.google.com/a", "sandbox": "allow-scripts allow-top-navigation"},
            )

    def test_embed_accepts_all_valid_optionals(self):
        validate_block_data(
            "embed",
            {
                "src": "https://docs.google.com/forms/d/xyz/viewform",
                "heading": "Sign-up form",
                "title": "RSVP form",
                "aspect_ratio": "16:9",
                "height": 720,
                "sandbox": "allow-scripts allow-same-origin allow-forms",
                "allow": "fullscreen; clipboard-read",
                "allowfullscreen": True,
            },
        )

    def test_embed_height_upper_bound_enforced(self):
        validate_block_data("embed", {"src": "https://docs.google.com/a", "height": 5000})
        with self.assertRaises(ValidationError):
            validate_block_data("embed", {"src": "https://docs.google.com/a", "height": 5001})

    def test_embed_empty_sandbox_falls_back_to_default(self):
        # An empty string in the `sandbox` field means "use frontend default";
        # the validator must treat it as acceptable, not as unknown tokens.
        validate_block_data("embed", {"src": "https://docs.google.com/a", "sandbox": ""})

    def test_embed_whitespace_only_sandbox_normalized_to_empty(self):
        # Whitespace-only input used to pass validation but be rendered as a
        # present-but-empty sandbox attribute (most restrictive policy),
        # silently breaking scripts/forms/popups. Validator must strip and
        # treat it as blank so the frontend falls back to the default.
        data = {"src": "https://docs.google.com/a", "sandbox": "   "}
        validate_block_data("embed", data)
        self.assertEqual(data["sandbox"], "")

    def test_embed_sandbox_leading_trailing_whitespace_trimmed(self):
        data = {"src": "https://docs.google.com/a", "sandbox": "  allow-scripts allow-forms  "}
        validate_block_data("embed", data)
        self.assertEqual(data["sandbox"], "allow-scripts allow-forms")
