"""Coverage for scam_detector.domains (IDN / homograph / typosquat helpers)."""

from django.test import SimpleTestCase

from apps.mail.services.scam_detector.domains import (
    _levenshtein,
    brand_lookalike,
    email_domain,
    has_non_ascii,
    is_punycode,
    registrable_domain,
    skeleton,
    suspicious_idn_reason,
)

BRANDS = ["amazon", "paypal", "apple", "wells fargo"]


class EmailDomainTests(SimpleTestCase):
    def test_extracts_domain(self):
        self.assertEqual(email_domain("Alice@Example.COM"), "example.com")

    def test_no_at_sign_returns_empty(self):
        self.assertEqual(email_domain("not-an-email"), "")

    def test_empty_returns_empty(self):
        self.assertEqual(email_domain(""), "")


class RegistrableDomainTests(SimpleTestCase):
    def test_strips_subdomains(self):
        self.assertEqual(registrable_domain("mail.corp.amazon.com"), "amazon.com")

    def test_single_label(self):
        self.assertEqual(registrable_domain("localhost"), "localhost")


class PunycodeAndAsciiTests(SimpleTestCase):
    def test_is_punycode_true(self):
        self.assertTrue(is_punycode("xn--80ak6aa92e.com"))

    def test_is_punycode_false(self):
        self.assertFalse(is_punycode("amazon.com"))

    def test_has_non_ascii(self):
        self.assertTrue(has_non_ascii("exаmple.com"))
        self.assertFalse(has_non_ascii("example.com"))


class SuspiciousIdnReasonTests(SimpleTestCase):
    def test_empty_domain_none(self):
        self.assertIsNone(suspicious_idn_reason(""))

    def test_punycode_reason(self):
        self.assertIn("punycode", suspicious_idn_reason("xn--pple-43d.com"))

    def test_non_ascii_reason(self):
        self.assertIn("non-ASCII", suspicious_idn_reason("exаmple.com"))

    def test_clean_domain_none(self):
        self.assertIsNone(suspicious_idn_reason("example.com"))


class SkeletonTests(SimpleTestCase):
    def test_collapses_confusables(self):
        self.assertEqual(skeleton("amaz0n"), "amazon")

    def test_strips_combining_marks(self):
        self.assertEqual(skeleton("café"), "cafe")


class LevenshteinTests(SimpleTestCase):
    def test_equal(self):
        self.assertEqual(_levenshtein("abc", "abc"), 0)

    def test_empty_first(self):
        self.assertEqual(_levenshtein("", "abc"), 3)

    def test_empty_second(self):
        self.assertEqual(_levenshtein("abc", ""), 3)

    def test_one_edit(self):
        self.assertEqual(_levenshtein("amazom", "amazon"), 1)


class BrandLookalikeTests(SimpleTestCase):
    def test_empty_label_none(self):
        self.assertIsNone(brand_lookalike("", BRANDS))

    def test_exact_brand_is_legit(self):
        self.assertIsNone(brand_lookalike("amazon.com", BRANDS))

    def test_confusable_skeleton_flagged(self):
        self.assertIn("imitates", brand_lookalike("amaz0n.com", BRANDS))

    def test_typosquat_within_one_edit(self):
        self.assertIn("resembles", brand_lookalike("paypai.com", BRANDS))

    def test_unrelated_domain_none(self):
        self.assertIsNone(brand_lookalike("example.com", BRANDS))

    def test_multiword_and_nonalnum_brands_skipped(self):
        # "wells fargo" (space) and "pay-pal" (hyphen) cannot map onto a domain label.
        self.assertIsNone(brand_lookalike("randomsite.com", ["", "wells fargo", "pay-pal"]))
