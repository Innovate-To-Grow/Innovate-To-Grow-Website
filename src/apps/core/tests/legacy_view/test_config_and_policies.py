from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.legacy_view.config import gateway_request_is_trusted, get_gateway_config, legacy_view_enabled
from apps.core.legacy_view.policies import (
    InvalidLegacyPath,
    PathDecision,
    canonicalize_legacy_path,
    classify_legacy_path,
    filter_query_string,
)

SECRET = "a-random-cloudfront-origin-value-with-32-characters"
GATEWAY_SETTINGS = {
    "LEGACY_VIEW_ENABLED": True,
    "LEGACY_ORIGIN_URL": "http://172.31.69.63:8080",
    "LEGACY_VIEWER_URL": "https://d111111abcdef8.cloudfront.net",
    "LEGACY_ORIGIN_HEADER_NAME": "X-I2G-Legacy-Origin-Secret",
    "LEGACY_ORIGIN_HEADER_VALUE": SECRET,
    "LEGACY_CONNECT_TIMEOUT_SECONDS": "2.5",
    "LEGACY_READ_TIMEOUT_SECONDS": 12,
}


@override_settings(**GATEWAY_SETTINGS)
class LegacyGatewayConfigTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_loads_pinned_private_origin_and_cloudfront_viewer(self):
        config = get_gateway_config()

        self.assertEqual(config.origin.hostname, "172.31.69.63")
        self.assertEqual(config.origin.port, 8080)
        self.assertEqual(config.viewer_base_url, "https://d111111abcdef8.cloudfront.net")
        self.assertEqual(config.connect_timeout_seconds, 2.5)
        self.assertEqual(config.read_timeout_seconds, 12)

    def test_shared_origin_header_must_match(self):
        trusted = self.factory.get("/legacy-view/about", headers={"X-I2G-Legacy-Origin-Secret": SECRET})
        wrong = self.factory.get("/legacy-view/about", headers={"X-I2G-Legacy-Origin-Secret": f"{SECRET}x"})
        missing = self.factory.get("/legacy-view/about")

        self.assertTrue(gateway_request_is_trusted(trusted))
        self.assertFalse(gateway_request_is_trusted(wrong))
        self.assertFalse(gateway_request_is_trusted(missing))

    @override_settings(LEGACY_VIEW_ENABLED="false")
    def test_string_false_feature_flag_fails_closed(self):
        request = self.factory.get("/", headers={"X-I2G-Legacy-Origin-Secret": SECRET})
        self.assertFalse(legacy_view_enabled())
        self.assertFalse(gateway_request_is_trusted(request))

    @override_settings(LEGACY_ORIGIN_URL="http://169.254.169.254/latest/meta-data")
    def test_rejects_any_origin_other_than_pinned_legacy_ip(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway_config()

    @override_settings(LEGACY_VIEWER_URL="https://legacy.i2g.ucmerced.edu")
    def test_rejects_non_cloudfront_viewer_url(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway_config()

    @override_settings(LEGACY_ORIGIN_HEADER_VALUE="short")
    def test_rejects_short_shared_secret(self):
        request = self.factory.get("/", headers={"X-I2G-Legacy-Origin-Secret": "short"})
        self.assertFalse(gateway_request_is_trusted(request))
        with self.assertRaises(ImproperlyConfigured):
            get_gateway_config()


class LegacyPathPolicyTest(SimpleTestCase):
    def test_allows_only_audited_information_static_and_safe_apis(self):
        self.assertIs(classify_legacy_path("/about"), PathDecision.ALLOW)
        self.assertIs(classify_legacy_path("/FAQs"), PathDecision.ALLOW)
        self.assertIs(classify_legacy_path("/api/schedule-data"), PathDecision.ALLOW)
        self.assertIs(classify_legacy_path("/static/images/i2glogo.png"), PathDecision.ALLOW)
        self.assertIs(
            classify_legacy_path("/past-projects/123e4567-e89b-12d3-a456-426614174000"),
            PathDecision.ALLOW,
        )

    def test_explicitly_blocks_admin_write_registration_and_tracking_routes(self):
        blocked_paths = (
            "/admin",
            "/admin/login",
            "/event/edit/1",
            "/membership/join",
            "/signup",
            "/confirm/token",
            "/update/token",
            "/event-registration/spring/token",
            "/project-submission",
            "/tracking_pixel/member@example.com.png",
            "/static/admin/selections.css",
            "/static/js/js-siteimprove.js",
        )
        for path in blocked_paths:
            with self.subTest(path=path):
                self.assertIs(classify_legacy_path(path), PathDecision.BLOCK)

    def test_unknown_route_fails_closed(self):
        self.assertIs(classify_legacy_path("/api/not-audited"), PathDecision.UNKNOWN)
        self.assertIs(classify_legacy_path("/new-route"), PathDecision.UNKNOWN)

    def test_canonicalizer_rejects_encoded_traversal_and_ambiguous_separators(self):
        for path in ("%252e%252e/admin", "foo\\bar", "foo//bar", "hello%00world"):
            with self.subTest(path=path), self.assertRaises(InvalidLegacyPath):
                canonicalize_legacy_path(path)

    def test_canonicalizer_decodes_before_policy_check(self):
        path = canonicalize_legacy_path("%61dmin/login")
        self.assertEqual(path, "/admin/login")
        self.assertIs(classify_legacy_path(path), PathDecision.BLOCK)

    def test_query_filter_drops_codes_and_unknown_fields(self):
        self.assertEqual(
            filter_query_string("page=2&code=do-not-forward&search=capstone&page=3&token=nope"),
            "page=2&search=capstone&page=3",
        )


@override_settings(**GATEWAY_SETTINGS)
class LegacyGatewayConfigValidationTest(SimpleTestCase):
    @override_settings(LEGACY_VIEW_ENABLED=False)
    def test_disabled_feature_flag_refuses_to_build_config(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "disabled"):
            get_gateway_config()

    def test_missing_required_urls_are_rejected(self):
        for name in ("LEGACY_ORIGIN_URL", "LEGACY_VIEWER_URL"):
            with self.subTest(name=name), override_settings(**{name: "  "}):
                with self.assertRaisesMessage(ImproperlyConfigured, f"{name} must be set"):
                    get_gateway_config()

    def test_non_numeric_timeouts_are_rejected(self):
        for name in ("LEGACY_CONNECT_TIMEOUT_SECONDS", "LEGACY_READ_TIMEOUT_SECONDS"):
            for value in ("soon", None):
                with self.subTest(name=name, value=value), override_settings(**{name: value}):
                    with self.assertRaisesMessage(ImproperlyConfigured, f"{name} must be a number."):
                        get_gateway_config()

    def test_out_of_range_timeouts_are_rejected(self):
        cases = (
            ("LEGACY_CONNECT_TIMEOUT_SECONDS", 0),
            ("LEGACY_CONNECT_TIMEOUT_SECONDS", 30.5),
            ("LEGACY_READ_TIMEOUT_SECONDS", 121),
        )
        for name, value in cases:
            with self.subTest(name=name, value=value), override_settings(**{name: value}):
                with self.assertRaisesMessage(ImproperlyConfigured, f"{name} must be between"):
                    get_gateway_config()

    @override_settings(LEGACY_ORIGIN_URL="http://172.31.69.63:not-a-port")
    def test_unparseable_origin_port_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "LEGACY_ORIGIN_URL is invalid."):
            get_gateway_config()

    @override_settings(LEGACY_VIEWER_URL="https://d111111abcdef8.cloudfront.net:not-a-port")
    def test_unparseable_viewer_port_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "LEGACY_VIEWER_URL is invalid."):
            get_gateway_config()


class LegacyPathPolicyEdgeCaseTest(SimpleTestCase):
    def test_canonicalizer_rejects_non_string_and_overlong_paths(self):
        for path in (None, b"/about", "a" * 2049):
            with self.subTest(path=type(path)), self.assertRaises(InvalidLegacyPath):
                canonicalize_legacy_path(path)

    def test_canonicalizer_rejects_more_than_three_layers_of_encoding(self):
        with self.assertRaisesMessage(InvalidLegacyPath, "excessive encoding"):
            canonicalize_legacy_path("static%252525252Fadmin")

    def test_query_filter_drops_query_with_too_many_fields(self):
        self.assertEqual(filter_query_string("page=1&" * 51), "")

    def test_query_filter_drops_overlong_query(self):
        self.assertEqual(filter_query_string("page=" + "1" * 2048), "")
