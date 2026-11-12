"""Live member matching (roles, case duplicates) and the text-only suggestions."""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.tests.services.email_monitoring.helpers import monitoring_settings
from apps.mail.models import BouncedAddress
from apps.mail.services.email_monitoring.addresses.matching import match_address, match_addresses
from apps.mail.services.email_monitoring.addresses.suggestions import suggest

from .helpers import add_email, make_person, make_row

Role = BouncedAddress.Role
Suggestion = BouncedAddress.Suggestion


class MatchingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_each_role_is_read_live(self):
        member = make_person("primary@example.org")
        add_email(member, "second@example.org", email_type="secondary")
        add_email(member, "other@example.org", email_type="other")
        ContactEmail.objects.create(member=None, email_address="orphan@example.org", email_type="other")

        matches = match_addresses(
            ["primary@example.org", "second@example.org", "other@example.org", "orphan@example.org", "none@example.org"]
        )

        roles = {address: match.role for address, match in matches.items()}
        self.assertEqual(
            roles,
            {
                "primary@example.org": Role.PRIMARY,
                "second@example.org": Role.SECONDARY,
                "other@example.org": Role.OTHER,
                "orphan@example.org": Role.UNLINKED,
                "none@example.org": Role.NONE,
            },
        )
        self.assertEqual(matches["primary@example.org"].member, member)
        self.assertIsNone(matches["orphan@example.org"].member)
        self.assertEqual(match_address("").role, Role.NONE)

    def test_one_address_in_two_letter_cases_is_ambiguous_and_names_every_owner(self):
        first = make_person("Twin@Example.org", first="Ann")
        second = make_person("twin@example.org", first="Bob")

        match = match_address("twin@example.org")

        self.assertEqual(match.role, Role.AMBIGUOUS)
        self.assertIsNone(match.contact)
        self.assertIsNone(match.member)
        self.assertEqual({owner.pk for owner in match.owners}, {first.pk, second.pk})

    def test_cached_links_follow_the_live_match(self):
        row = make_row("cached@example.org")
        self.assertEqual(row.role, Role.NONE)
        member = make_person("cached@example.org")

        from apps.mail.services.email_monitoring.addresses.matching import refresh_cached_links

        changed = refresh_cached_links([row])

        row.refresh_from_db()
        self.assertEqual(changed, 1)
        self.assertEqual((row.role, row.member_id), (Role.PRIMARY, member.pk))
        self.assertEqual(refresh_cached_links([row]), 0)


class SuggestionTests(TestCase):
    def setUp(self):
        cache.clear()

    def _row(self, **values) -> BouncedAddress:
        now = timezone.now()
        defaults = {"address": "s@example.org", "first_bounce_at": now, "last_bounce_at": now}
        return BouncedAddress(**{**defaults, **values})

    def test_the_suggestions_follow_the_plan_in_order(self):
        old = timezone.now() - timedelta(days=8)
        cases = [
            ({"complaint_count": 1, "category_counts": {"hard": 2}}, Suggestion.UNSUBSCRIBE),
            ({"category_counts": {"hard": 1, "transient": 5}}, Suggestion.UNDELIVERABLE),
            ({"ses_permanent_count": 1}, Suggestion.UNDELIVERABLE),
            ({"category_counts": {"mailbox_disabled": 1, "spam_rejected": 1}}, Suggestion.REPLACE),
            ({"category_counts": {"transient": 3}, "first_bounce_at": old}, Suggestion.CONSIDER),
            (
                {
                    "category_counts": {"mailbox_full": 1, "unknown": 1},
                    "ses_transient_count": 1,
                    "first_bounce_at": old,
                },
                Suggestion.CONSIDER,
            ),
            ({"ses_undetermined_count": 3, "first_bounce_at": old}, Suggestion.CONSIDER),
            ({"category_counts": {"transient": 3}}, ""),  # repeated, but not over a week
            ({"category_counts": {"transient": 2}, "first_bounce_at": old}, ""),  # over a week, not repeated enough
            ({"category_counts": {"relay_denied": 3, "transient": 1}, "first_bounce_at": old}, Suggestion.RELAY),
            ({"category_counts": {"spam_rejected": 2, "policy_rejected": 1}}, Suggestion.REPUTATION),
            ({"category_counts": {"policy_rejected": 2}}, Suggestion.POLICY),
            ({"category_counts": {"delayed": 4}}, ""),
            ({"category_counts": {"hard": 1}, "suppressed_at": timezone.now()}, ""),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertEqual(suggest(self._row(**values)), expected)

    def test_a_temporary_failure_alone_never_suggests_marking_the_address_undeliverable(self):
        for category in ("transient", "mailbox_full", "unknown", "spam_rejected", "relay_denied", "policy_rejected"):
            with self.subTest(category=category):
                self.assertNotIn(
                    suggest(self._row(category_counts={category: 1})),
                    (Suggestion.UNDELIVERABLE, Suggestion.REPLACE, Suggestion.CONSIDER),
                )

    def test_relay_and_reputation_suggestions_point_at_our_sending_not_the_address(self):
        for suggestion in (Suggestion.RELAY, Suggestion.REPUTATION, Suggestion.POLICY):
            with self.subTest(suggestion=suggestion):
                self.assertIn("not the address", suggestion.label)
                self.assertFalse(self._row(suggestion=suggestion).suggests_address_action)
        self.assertIn("route and authorisation", Suggestion.RELAY.label)
        self.assertIn("reputation, authentication and content", Suggestion.REPUTATION.label)
        self.assertTrue(self._row(suggestion=Suggestion.REPLACE).suggests_address_action)

    def test_the_repeated_failure_thresholds_are_settings(self):
        row = self._row(category_counts={"transient": 2}, first_bounce_at=timezone.now() - timedelta(days=2))

        with monitoring_settings(address_soft_bounce_repeats=2, address_soft_bounce_days=1):
            self.assertEqual(suggest(row), Suggestion.CONSIDER)
        with monitoring_settings(address_soft_bounce_repeats=3, address_soft_bounce_days=1):
            self.assertEqual(suggest(row), "")
