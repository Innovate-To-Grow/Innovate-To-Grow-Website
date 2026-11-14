import datetime
import uuid

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.account.recovery import members_with_sign_in_contact
from apps.authn.services.contacts.primary_switch import (
    current_primary,
    describe,
    log_switch,
    member_emails,
    plan_primary_switch,
    switch_primary_email,
)
from apps.authn.tests.services.contacts.test_primary_switch import Member, add_email


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
