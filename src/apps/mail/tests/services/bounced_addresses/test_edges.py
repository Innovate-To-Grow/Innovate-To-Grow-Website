"""Edge paths of the Bounced addresses services: repeated campaign links, a busy counter, stale suggestions, members
without names, and refusals raised by the Members app's own services."""

from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from apps.authn.models import ContactEmail
from apps.authn.services.email.challenges import AuthChallengeInvalid
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.event.tests.helpers import make_superuser
from apps.mail.models import BounceAggregationState, BouncedAddress, BouncedAddressAction, BouncedAddressCampaign
from apps.mail.services.email_monitoring.addresses import actions, aggregate, audit
from apps.mail.services.email_monitoring.addresses.actions import ActionRefused
from apps.mail.services.email_monitoring.addresses.export import export_rows
from apps.mail.services.email_monitoring.addresses.listing import parse_listing

from .helpers import add_email, count_now, make_bounce, make_campaign, make_person, make_row, make_ses_log, settled
from .test_actions import apply

Action = BouncedAddressAction.Action


class CountingEdgeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_repeated_reports_for_one_campaign_share_a_link_that_turns_exact(self):
        blast = make_campaign("Blast")
        make_ses_log(blast, "rep@example.org", bounced=False)
        make_bounce(recipient="rep@example.org")  # unmatched: likely
        count_now()
        email = make_email(recipient="rep@example.org", campaign_id=blast.pk)
        make_bounce(recipient="rep@example.org", email=email, campaign_id=blast.pk)  # matched: exact

        count_now()

        link = BouncedAddressCampaign.objects.get(bounced_address__address="rep@example.org", source="graph")
        self.assertEqual((link.bounce_count, link.match), (2, BouncedAddressCampaign.Match.EXACT))

    def test_a_source_another_run_holds_is_skipped_without_waiting(self):
        make_bounce(recipient="busy@example.org")

        with settled(), patch.object(aggregate, "_locked_state", return_value=None):
            result = aggregate.run(wait=False)

        self.assertEqual((result["graph"], result["busy"]), (0, True))
        self.assertFalse(BouncedAddress.objects.exists())

    def test_refresh_all_corrects_a_stale_suggestion(self):
        row = make_row("stale@example.org", suggestion="policy")

        self.assertEqual(aggregate.refresh_all(), 1)

        row.refresh_from_db()
        self.assertEqual(row.suggestion, BouncedAddress.Suggestion.UNDELIVERABLE)

    def test_the_state_rows_name_their_source(self):
        count_now()

        self.assertEqual(
            sorted(str(state) for state in BounceAggregationState.objects.all()),
            ["Bounced-address counting: graph", "Bounced-address counting: ses"],
        )


class DisplayEdgeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_records_describe_themselves(self):
        row = make_row("str@example.org")
        link = BouncedAddressCampaign.objects.create(bounced_address=row, campaign_id=make_campaign().pk, source="ses")
        entry = BouncedAddressAction.objects.create(action=Action.REBUILD)

        self.assertEqual(str(row), "str@example.org")
        self.assertIn("(ses)", str(link))
        self.assertEqual(str(entry), "Rebuild counts from records: all addresses")
        self.assertEqual(row.resolution_label, "")

    def test_a_member_without_a_name_or_email_is_named_by_id(self):
        member = make_person("named@example.org", first="", last="")
        ContactEmail.objects.filter(member=member).delete()

        self.assertEqual(audit.person_label(member), str(member.pk))
        self.assertEqual(audit.person_label(None), "")

    def test_the_export_leaves_member_columns_blank_for_an_address_of_no_member(self):
        row = make_row("loose@example.org")

        content = export_rows(BouncedAddress.objects.filter(pk=row.pk))

        self.assertTrue(content.startswith(b"PK"))

    def test_an_unreadable_page_size_falls_back(self):
        self.assertEqual(parse_listing({"page_size": "lots"}).page_size, 50)


class RefusalEdgeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.master = make_superuser()

    def test_a_refusal_from_make_contact_email_primary_is_shown(self):
        member = make_person("old@example.org")
        verified = add_email(member, "new@example.org", email_type="other", verified=True)
        row = make_row("old@example.org")
        target = "apps.mail.services.email_monitoring.addresses.actions.make_contact_email_primary"

        with patch(target, side_effect=AuthChallengeInvalid("Contact email not found.")):
            for action in (Action.MAKE_PRIMARY, Action.DELETE_EMAIL):
                with self.subTest(action=action), self.assertRaises(ActionRefused):
                    apply(self.master, row, action, new_primary=str(verified.pk), confirm="old@example.org")

    def test_an_account_protected_by_other_records_is_not_deleted(self):
        member = make_person("kept@example.org")
        row = make_row("kept@example.org")
        protected = {"deleted": [], "model_count": [], "protected": ["a protected record"]}

        with patch("apps.mail.services.email_monitoring.addresses.actions.deletion_summary", return_value=protected):
            with self.assertRaisesMessage(ActionRefused, "deactivate it instead"):
                apply(self.master, row, Action.DELETE_ACCOUNT, confirm="kept@example.org")

        member.refresh_from_db()
        self.assertTrue(member.is_active)

    def test_a_database_or_validation_conflict_is_refused_with_nothing_changed(self):
        make_person("race@example.org")
        row = make_row("race@example.org")

        def conflicting(exc):
            def handler(request, target, values):
                BouncedAddress.objects.filter(pk=target.row.pk).update(status=BouncedAddress.Status.DISMISSED)
                raise exc

            return handler

        for exc, message in (
            (IntegrityError("duplicate"), "conflicts with another record"),
            (ValidationError("Enter a valid email address."), "Enter a valid email address."),
        ):
            with self.subTest(exc=type(exc).__name__):
                with patch.dict(actions.APPLY, {Action.UNSUBSCRIBE: conflicting(exc)}):
                    with self.assertRaisesMessage(ActionRefused, message):
                        apply(self.master, row, Action.UNSUBSCRIBE)
                row.refresh_from_db()
                self.assertEqual(row.status, BouncedAddress.Status.OPEN)
