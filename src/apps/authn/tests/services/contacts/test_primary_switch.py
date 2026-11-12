"""``switch_primary_email``: the existing swap service, plus clear refusals, a stale check and what changed."""

import datetime
import uuid
from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.account.recovery import members_with_sign_in_contact
from apps.authn.services.contacts import primary_switch as service
from apps.authn.services.contacts.primary_switch import (
    NOT_FOUND,
    NOT_VERIFIED,
    STALE,
    StaleSwitch,
    SwitchRefused,
    current_primary,
    describe,
    fingerprint,
    log_switch,
    member_emails,
    plan_primary_switch,
    switch_primary_email,
)

Member = get_user_model()


def add_email(member, address, email_type, *, verified=True, subscribe=True, days_ago=0):
    row = ContactEmail.objects.create(
        member=member, email_address=address, email_type=email_type, verified=verified, subscribe=subscribe
    )
    # Distinct, explicit creation times: the service demotes the newest secondary.
    ContactEmail.objects.filter(pk=row.pk).update(created_at=timezone.now() - datetime.timedelta(days=days_ago))
    row.refresh_from_db()
    return row


def types(member) -> dict:
    return dict(ContactEmail.objects.filter(member=member).values_list("email_address", "email_type"))


class SwitchPrimaryEmailTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(password="x", first_name="Ada", last_name="Admin")
        self.jane = Member.objects.create_user(first_name="Jane", last_name="Doe", is_active=True)
        self.primary = add_email(self.jane, "jane@example.com", "primary", days_ago=30)
        self.secondary = add_email(self.jane, "jane.work@example.com", "secondary", days_ago=20)
        self.other = add_email(self.jane, "jane.old@example.com", "other", days_ago=10)

    def test_a_verified_secondary_swaps_with_the_primary(self):
        result = switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk)

        self.assertEqual(
            types(self.jane),
            {"jane@example.com": "secondary", "jane.work@example.com": "primary", "jane.old@example.com": "other"},
        )
        self.assertEqual(result.primary.pk, self.secondary.pk)
        self.assertEqual(result.previous.pk, self.primary.pk)
        self.assertTrue(result.changed)
        self.assertEqual(
            {(change.contact.email_address, change.before, change.after) for change in result.changes},
            {("jane@example.com", "primary", "secondary"), ("jane.work@example.com", "secondary", "primary")},
        )

    def test_an_other_address_moves_the_secondary_aside(self):
        result = switch_primary_email(member=self.jane, contact_email_id=str(self.other.pk))

        self.assertEqual(
            types(self.jane),
            {"jane@example.com": "secondary", "jane.work@example.com": "other", "jane.old@example.com": "primary"},
        )
        self.assertEqual(len(result.changes), 3)

    def test_subscriptions_and_verification_never_change(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(subscribe=False)
        before = list(ContactEmail.objects.filter(member=self.jane).values_list("pk", "verified", "subscribe"))

        switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk)

        after = list(ContactEmail.objects.filter(member=self.jane).values_list("pk", "verified", "subscribe"))
        self.assertCountEqual(before, after)

    def test_the_current_primary_is_a_no_op(self):
        result = switch_primary_email(member=self.jane, contact_email_id=self.primary.pk)

        self.assertFalse(result.changed)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_an_unverified_address_is_refused_with_what_to_do(self):
        ContactEmail.objects.filter(pk=self.secondary.pk).update(verified=False)

        with self.assertRaisesMessage(SwitchRefused, NOT_VERIFIED.format(address="jane.work@example.com")):
            switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")
        self.assertIn("account page", NOT_VERIFIED)

    def test_another_members_address_is_refused(self):
        john = Member.objects.create_user(first_name="John", last_name="Roe")
        johns = add_email(john, "john@example.com", "secondary")

        for target in (johns.pk, "not-a-uuid", ""):
            with self.subTest(target=target), self.assertRaisesMessage(SwitchRefused, NOT_FOUND):
                switch_primary_email(member=self.jane, contact_email_id=target)
        self.assertEqual(types(john), {"john@example.com": "secondary"})

    def test_a_stale_page_changes_nothing(self):
        seen = fingerprint(self.jane, member_emails(self.jane))
        ContactEmail.objects.filter(pk=self.other.pk).update(subscribe=False)

        with self.assertRaisesMessage(StaleSwitch, STALE):
            switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk, seen=seen)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_the_page_seen_is_accepted(self):
        seen = fingerprint(self.jane, member_emails(self.jane))

        result = switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk, seen=seen)

        self.assertEqual(result.primary.email_type, "primary")

    def test_the_fingerprint_covers_the_account_and_every_address_flag(self):
        seen = fingerprint(self.jane, member_emails(self.jane))
        variants = [
            {"is_staff": True},
            {"is_superuser": True},
            {"is_active": False},
        ]
        for change in variants:
            with self.subTest(change=change):
                member = Member.objects.get(pk=self.jane.pk)
                for name, value in change.items():
                    setattr(member, name, value)
                self.assertNotEqual(fingerprint(member, member_emails(member)), seen)
        for field, value in (("verified", False), ("subscribe", False), ("email_type", "secondary")):
            with self.subTest(field=field):
                emails = member_emails(self.jane)
                setattr(emails[-1], field, value)
                self.assertNotEqual(fingerprint(self.jane, emails), seen)
        add_email(self.jane, "jane.new@example.com", "other")
        self.assertNotEqual(fingerprint(self.jane, member_emails(self.jane)), seen)

    def test_with_an_actor_the_history_commits_or_rolls_back_with_the_switch(self):
        result = switch_primary_email(
            member=self.jane, contact_email_id=self.secondary.pk, actor=self.admin, via="test"
        )

        self.assertEqual(LogEntry.objects.filter(user=self.admin).count(), 1 + len(result.changes))
        with patch.object(LogEntry.objects, "log_actions", side_effect=DatabaseError("history unavailable")):
            with self.assertRaises(DatabaseError):
                switch_primary_email(member=self.jane, contact_email_id=self.primary.pk, actor=self.admin, via="test")
        self.assertEqual(types(self.jane)["jane.work@example.com"], "primary")

    def test_an_address_unverified_meanwhile_by_a_bulk_action_is_refused(self):
        # "Mark selected emails as unverified" updates rows without the member lock, so the target can lose Verified
        # after it was read; the existing service's own check under its row lock refuses it, and nothing changes.
        real = service.make_contact_email_primary

        def unverified_meanwhile(*, member, contact_email_id):
            ContactEmail.objects.filter(pk=contact_email_id).update(verified=False)
            return real(member=member, contact_email_id=contact_email_id)

        with patch.object(service, "make_contact_email_primary", side_effect=unverified_meanwhile):
            with self.assertRaisesMessage(SwitchRefused, "Verify this email before setting it as primary."):
                switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk)
        self.assertEqual(types(self.jane)["jane@example.com"], "primary")

    def test_a_member_with_no_primary_gets_one(self):
        ContactEmail.objects.filter(pk=self.primary.pk).delete()

        result = switch_primary_email(member=self.jane, contact_email_id=self.other.pk)

        self.assertIsNone(result.previous)
        # With no old primary, the service moves no secondary aside.
        self.assertEqual(types(self.jane), {"jane.work@example.com": "secondary", "jane.old@example.com": "primary"})
        self.assertEqual(describe(result), "Primary email set to jane.old@example.com (the member had none).")


class PlanMatchesTheServiceTests(TestCase):
    """The confirmation page's preview is exactly what the service then does."""

    def scenario(self, rows, target_address):
        member = Member.objects.create_user(first_name="Pat", last_name="Plan")
        created = {}
        for index, (address, email_type, verified) in enumerate(rows):
            created[address] = add_email(member, address, email_type, verified=verified, days_ago=50 - index)
        emails = member_emails(member)
        target = next(email for email in emails if email.email_address == target_address)
        planned = {(change.contact.pk, change.before, change.after) for change in plan_primary_switch(emails, target)}
        result = switch_primary_email(member=member, contact_email_id=target.pk)
        done = {(change.contact.pk, change.before, change.after) for change in result.changes}
        return planned, done

    def test_every_shape(self):
        shapes = {
            "secondary to primary": (
                [("a@example.org", "primary", True), ("b@example.org", "secondary", True)],
                "b@example.org",
            ),
            "other to primary, secondary aside": (
                [
                    ("a@example.org", "primary", True),
                    ("b@example.org", "secondary", True),
                    ("c@example.org", "other", True),
                ],
                "c@example.org",
            ),
            "two legacy secondaries": (
                [
                    ("a@example.org", "primary", True),
                    ("b@example.org", "secondary", True),
                    ("c@example.org", "secondary", False),
                    ("d@example.org", "other", True),
                ],
                "d@example.org",
            ),
            "no primary": ([("b@example.org", "secondary", True), ("c@example.org", "other", True)], "c@example.org"),
            "already primary": (
                [("a@example.org", "primary", True), ("b@example.org", "secondary", True)],
                "a@example.org",
            ),
        }
        for name, (rows, target) in shapes.items():
            with self.subTest(name):
                ContactEmail.objects.all().delete()
                planned, done = self.scenario(rows, target)
                self.assertEqual(planned, done)

    def test_two_secondaries_with_the_same_timestamp(self):
        # Legacy data can hold two secondaries created at the same instant: the preview and the service must still
        # pick the same one to move aside (the higher id, as the service's ``-created_at, -pk`` order does).
        member = Member.objects.create_user(first_name="Tia", last_name="Tie")
        add_email(member, "a@example.org", "primary", days_ago=50)
        low, high = (
            ContactEmail.objects.create(
                id=uuid.UUID(int=value), member=member, email_address=address, email_type="secondary", verified=True
            )
            for value, address in ((1, "b@example.org"), (2**128 - 1, "c@example.org"))
        )
        ContactEmail.objects.filter(pk__in=[low.pk, high.pk]).update(created_at=timezone.now() - datetime.timedelta(5))
        target = add_email(member, "d@example.org", "other", days_ago=1)
        emails = member_emails(member)
        planned = {(change.contact.pk, change.before, change.after) for change in plan_primary_switch(emails, target)}

        done = {
            (change.contact.pk, change.before, change.after)
            for change in switch_primary_email(member=member, contact_email_id=target.pk).changes
        }

        self.assertEqual(planned, done)
        self.assertIn((high.pk, "secondary", "other"), done)

    def test_current_primary_is_none_without_one(self):
        self.assertIsNone(current_primary([]))


class SwitchHistoryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(password="x", first_name="Ada", last_name="Admin")
        self.jane = Member.objects.create_user(first_name="Jane", last_name="Doe")
        self.primary = add_email(self.jane, "jane@example.com", "primary", days_ago=30)
        self.secondary = add_email(self.jane, "jane.work@example.com", "secondary", days_ago=20)
        self.other = add_email(self.jane, "jane.old@example.com", "other", days_ago=10)

    def entries(self, obj):
        return LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(type(obj)), object_id=str(obj.pk)
        ).order_by("action_time")

    def test_one_line_on_the_member_and_one_on_each_changed_address(self):
        result = switch_primary_email(member=self.jane, contact_email_id=self.other.pk)

        with self.assertLogs("apps.authn.services.contacts.primary_switch", level="INFO") as logs:
            log_switch(self.admin, result, via="Switch primary email on the member page")

        summary = (
            "Primary email switched from jane@example.com to jane.old@example.com: jane@example.com is now the "
            "secondary; jane.work@example.com is now other. (Switch primary email on the member page)"
        )
        member_entry = self.entries(self.jane).get()
        self.assertEqual(member_entry.action_flag, CHANGE)
        self.assertEqual(member_entry.user_id, self.admin.pk)
        self.assertEqual(member_entry.change_message, summary)
        self.assertEqual(
            self.entries(self.secondary).get().change_message,
            f"Email type changed from secondary to other. {summary}",
        )
        self.assertEqual(
            self.entries(self.primary).get().change_message, f"Email type changed from primary to secondary. {summary}"
        )
        self.assertEqual(
            self.entries(self.other).get().change_message, f"Email type changed from other to primary. {summary}"
        )
        # The application log names ids only, never an address.
        self.assertNotIn("@", " ".join(logs.output))
        self.assertIn(str(self.jane.pk), " ".join(logs.output))

    def test_nothing_is_written_when_nothing_changed(self):
        result = switch_primary_email(member=self.jane, contact_email_id=self.primary.pk)

        log_switch(self.admin, result, via="test")

        self.assertFalse(LogEntry.objects.exists())

    def test_describe_a_plain_swap(self):
        result = switch_primary_email(member=self.jane, contact_email_id=self.secondary.pk)

        self.assertEqual(
            describe(result),
            "Primary email switched from jane@example.com to jane.work@example.com: jane@example.com is now the "
            "secondary.",
        )


class MembersWithSignInContactTests(TestCase):
    def test_a_verified_email_or_phone_counts(self):
        by_email = Member.objects.create_user(first_name="E", last_name="Mail")
        by_phone = Member.objects.create_user(first_name="P", last_name="Hone")
        neither = Member.objects.create_user(first_name="N", last_name="One")
        add_email(by_email, "e@example.com", "primary")
        add_email(neither, "n@example.com", "primary", verified=False)
        ContactPhone.objects.create(member=by_phone, phone_number="2095550100", verified=True)
        ContactPhone.objects.create(member=neither, phone_number="2095550101", verified=False)

        self.assertEqual(
            members_with_sign_in_contact([by_email.pk, by_phone.pk, neither.pk, None]), {by_email.pk, by_phone.pk}
        )
        self.assertEqual(members_with_sign_in_contact([]), set())
        self.assertEqual(members_with_sign_in_contact([None]), set())
