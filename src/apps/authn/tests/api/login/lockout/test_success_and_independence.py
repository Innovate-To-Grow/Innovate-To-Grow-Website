from apps.authn.models import ContactEmail
from apps.authn.tests.api.login.lockout.test_login_lockout import EMAIL, PASSWORD, PHONE, LoginLockoutTestCase, Member
from apps.authn.tests.clock import SECONDS_LEFT_IN_SHORT_WINDOW


class SuccessAndIndependenceTests(LoginLockoutTestCase):
    def test_a_successful_login_clears_the_failure_count(self):
        self.assertEqual(self.fail_times(9), [400] * 9)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

        self.assertEqual(self.fail_times(10), [400] * 10)  # would have been locked without the clear
        self.assertLocked(self.login())

    def test_a_successful_login_clears_the_daily_count_too(self):
        for _ in range(2):
            self.assertEqual(self.fail_times(9), [400] * 9)
            self.clock.advance(15 * 60)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

        for _ in range(2):
            self.assertEqual(self.fail_times(9), [400] * 9)
            self.clock.advance(15 * 60)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

    def test_different_identifiers_are_independent(self):
        self.lock(EMAIL)

        self.assertLocked(self.login(EMAIL, PASSWORD))
        self.assertEqual(self.login(PHONE, PASSWORD).status_code, 200)
        self.assertEqual(self.login("someone-else@example.com").status_code, 400)

    def test_one_identifier_failing_never_touches_the_password_of_another_account(self):
        self.lock(PHONE)

        self.assertEqual(self.login(EMAIL, PASSWORD).status_code, 200)

    def test_phone_formats_share_one_budget(self):
        formats = ["2095551234", "(209) 555-1234", "+1 209 555 1234", "12095551234", "209-555-1234"]
        statuses = [self.login(formats[index % len(formats)]).status_code for index in range(10)]

        self.assertEqual(statuses, [400] * 10)
        for spelling in formats:
            with self.subTest(spelling=spelling):
                self.assertLocked(self.login(spelling, PASSWORD))

    def test_email_case_and_spaces_share_one_budget(self):
        variants = ["student@example.com", "Student@Example.com", "  STUDENT@EXAMPLE.COM ", "student@EXAMPLE.com"]
        statuses = [self.login(variants[index % len(variants)]).status_code for index in range(10)]

        self.assertEqual(statuses, [400] * 10)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertLocked(self.login(variant, PASSWORD))

    def test_unicode_lookalike_of_an_email_shares_its_budget(self):
        """PostgreSQL ``UPPER()`` resolves ``ſ`` and ``ı`` to ``s`` and ``i``: they must not restart the count."""
        target = "sims.pinar@example.com"
        lookalike = "ſims.pınar@example.com"
        self.assertEqual(self.fail_times(5, target), [400] * 5)
        self.assertEqual(self.fail_times(5, lookalike), [400] * 5)

        self.assertLocked(self.login(target))
        self.assertLocked(self.login(lookalike))


class NoEnumerationOracleTests(LoginLockoutTestCase):
    def setUp(self):
        super().setUp()
        inactive = Member.objects.create_user(password=PASSWORD, is_active=False)
        ContactEmail.objects.create(
            member=inactive, email_address="gone@example.com", email_type="primary", verified=True
        )
        unverified = Member.objects.create_user(password=PASSWORD, is_active=True)
        ContactEmail.objects.create(
            member=unverified, email_address="pending@example.com", email_type="primary", verified=False
        )
        self.identifiers = {
            "existing email": EMAIL,
            "existing phone": PHONE,
            "unknown email": "nobody@example.com",
            "unknown phone": "2025550000",
            "inactive account": "gone@example.com",
            "unverified email": "pending@example.com",
            "not an email or a phone": "just some text",
        }

    def test_locked_responses_are_byte_identical_for_every_kind_of_identifier(self):
        seen = {}
        for label, identifier in self.identifiers.items():
            with self.subTest(identifier=label):
                self.assertEqual(self.fail_times(10, identifier), [400] * 10)
                response = self.login(identifier, PASSWORD)
                seen[label] = (
                    response.status_code,
                    response.content,
                    response["Retry-After"],
                    response["Content-Type"],
                )

        self.assertEqual(len(set(seen.values())), 1, seen)
        self.assertLocked(self.login(EMAIL, PASSWORD), SECONDS_LEFT_IN_SHORT_WINDOW)

    def test_rejections_before_the_limit_are_byte_identical_too(self):
        contents = {label: self.login(identifier).content for label, identifier in self.identifiers.items()}

        self.assertEqual(len(set(contents.values())), 1, contents)

    def test_the_threshold_is_the_same_for_every_kind_of_identifier(self):
        for label, identifier in self.identifiers.items():
            with self.subTest(identifier=label):
                self.assertEqual(self.fail_times(9, identifier), [400] * 9)
                self.assertEqual(self.login(identifier).status_code, 400)
                self.assertEqual(self.login(identifier).status_code, 429)

    def test_daily_lock_is_also_identical_for_known_and_unknown_identifiers(self):
        responses = {}
        for identifier in (EMAIL, "nobody@example.com"):
            for _ in range(3):
                self.assertEqual(self.fail_times(10, identifier), [400] * 10)
                self.clock.advance(15 * 60)
            responses[identifier] = self.login(identifier, PASSWORD)
            self.clock.advance(-3 * 15 * 60)

        first, second = responses.values()
        self.assertLocked(first)
        self.assertEqual(
            (first.status_code, first.content, first["Retry-After"]),
            (second.status_code, second.content, second["Retry-After"]),
        )
