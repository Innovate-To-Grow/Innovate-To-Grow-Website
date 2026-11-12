"""People and addresses shared by the switch-primary admin tests (all made up)."""

import datetime

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail

Member = get_user_model()


def add_email(member, address, email_type, *, verified=True, subscribe=True, days_ago=0):
    row = ContactEmail.objects.create(
        member=member, email_address=address, email_type=email_type, verified=verified, subscribe=subscribe
    )
    ContactEmail.objects.filter(pk=row.pk).update(created_at=timezone.now() - datetime.timedelta(days=days_ago))
    row.refresh_from_db()
    return row


def switch_url(member, contact=None) -> str:
    url = reverse("admin:authn_member_switch_primary_email", args=[member.pk])
    return f"{url}?to={contact.pk}" if contact is not None else url


def change_url(member) -> str:
    return reverse("admin:authn_member_change", args=[member.pk])


def types(member) -> dict:
    return dict(ContactEmail.objects.filter(member=member).values_list("email_address", "email_type"))


def history(obj) -> list[str]:
    return list(
        LogEntry.objects.filter(content_type=ContentType.objects.get_for_model(type(obj)), object_id=str(obj.pk))
        .order_by("action_time")
        .values_list("change_message", flat=True)
    )


class SwitchFixture(TestCase):
    """The I2G Master, a staff helper with the Members app, a staff member without it, and Jane (a regular member)
    with a verified primary, a verified secondary and an unverified, unsubscribed "other" address."""

    @classmethod
    def setUpTestData(cls):
        cls.master = Member.objects.create_superuser(password="StrongPass123!", first_name="Ada", last_name="Master")
        add_email(cls.master, "master@example.com", "primary")
        cls.helper = Member.objects.create_user(
            first_name="Hal", last_name="Helper", is_active=True, is_staff=True, admin_apps=["authn"]
        )
        cls.helper_primary = add_email(cls.helper, "hal@example.com", "primary", days_ago=9)
        cls.helper_backup = add_email(cls.helper, "hal.home@example.com", "secondary", days_ago=8)
        cls.outsider = Member.objects.create_user(
            first_name="Olga", last_name="Outsider", is_active=True, is_staff=True, admin_apps=["cms"]
        )
        cls.staffer = Member.objects.create_user(first_name="Sam", last_name="Staff", is_active=True, is_staff=True)
        cls.staffer_primary = add_email(cls.staffer, "sam@example.com", "primary", days_ago=9)
        cls.staffer_backup = add_email(cls.staffer, "sam.home@example.com", "secondary", days_ago=8)
        cls.jane = Member.objects.create_user(first_name="Jane", last_name="Doe", is_active=True)
        cls.primary = add_email(cls.jane, "jane@example.com", "primary", days_ago=30)
        cls.secondary = add_email(cls.jane, "jane.work@example.com", "secondary", days_ago=20)
        cls.unverified = add_email(
            cls.jane, "jane.old@example.com", "other", verified=False, subscribe=False, days_ago=10
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.master)

    def tearDown(self):
        cache.clear()

    def apply(self, member, contact, *, confirm="", fingerprint=None, follow=False):
        """POST the confirmation form exactly as the page rendered it (its fingerprint), unless one is given."""
        if fingerprint is None:
            fingerprint = self.client.get(switch_url(member, contact)).context["fingerprint"]
        data = {"to": str(contact.pk), "fingerprint": fingerprint, "confirm": confirm}
        return self.client.post(switch_url(member), data, follow=follow)
