"""Fixtures for the Bounced addresses tests: members with contact emails, bounce reports, SES recipient logs, and a
request stand-in for the services that take one. Every address is synthetic (the repository is public)."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail, ContactPhone
from apps.core.tests.services.email_monitoring.helpers import make_bounce
from apps.mail.models import BouncedAddress, EmailCampaign, RecipientLog
from apps.mail.services.email_monitoring.addresses import aggregate
from apps.mail.services.email_monitoring.addresses.matching import refresh_cached_links
from apps.mail.services.email_monitoring.addresses.suggestions import suggest

Member = get_user_model()

__all__ = [
    "add_email",
    "count_now",
    "make_bounce",
    "make_campaign",
    "make_person",
    "make_row",
    "make_ses_log",
    "request_for",
    "settled",
]


def settled():
    """Count reports as soon as they are saved (the settle delay is for transactions that commit late)."""
    return override_settings(EMAIL_MONITORING={**settings.EMAIL_MONITORING, "address_settle_seconds": 0})


def count_now() -> dict:
    with settled():
        return aggregate.run()


def make_person(email="person@example.org", *, verified=True, first="Pat", last="Doe", phone=None, **kwargs):
    """An active member whose primary contact email is ``email``."""
    member = Member.objects.create_user(password="pass-12345", first_name=first, last_name=last, **kwargs)
    ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=verified)
    if phone is not None:
        ContactPhone.objects.create(member=member, phone_number=phone, verified=True)
    return member


def add_email(member, email, *, email_type="secondary", verified=False, subscribe=True):
    return ContactEmail.objects.create(
        member=member, email_address=email, email_type=email_type, verified=verified, subscribe=subscribe
    )


def make_campaign(name="Spring blast", **values):
    return EmailCampaign.objects.create(name=name, subject=name, body="<p>Hi</p>", status="sent", **values)


def make_ses_log(campaign, email, *, bounce_type="Permanent", complained=False, bounced=True, status=None, member=None):
    """A campaign recipient log as the SES event handlers leave it (``bounced=False, complained=False``: just sent)."""
    now = timezone.now()
    if status is None:
        status = "complained" if complained else ("bounced" if bounced else "sent")
    return RecipientLog.objects.create(
        campaign=campaign,
        member=member,
        email_address=email,
        status=status,
        provider="ses",
        sent_at=now - timedelta(minutes=5),
        bounced_at=now if bounced else None,
        bounce_type=bounce_type if bounced else "",
        diagnostic_code="smtp; 550 5.1.1 user unknown" if bounced else "",
        complained_at=now if complained else None,
    )


# The category a test's coarse count stands for, when the test gives no category counts.
COUNT_CATEGORIES = {
    "hard_count": "hard",
    "soft_count": "transient",
    "rejected_count": "policy_rejected",
    "delayed_count": "delayed",
    "unknown_count": "unknown",
}


def make_row(address="person@example.org", **values) -> BouncedAddress:
    """A counted address (as if one hard bounce had been counted), its links refreshed. Its category counts follow its
    coarse counts unless given."""
    now = timezone.now()
    defaults = {
        "hard_count": 1,
        "graph_first_at": now,
        "graph_last_at": now,
        "first_bounce_at": now,
        "last_bounce_at": now,
        "last_classification": "hard",
        "last_category": "hard",
        "last_status_code": "5.1.1",
        "last_reason": "Recipient mailbox does not exist",
    }
    merged = {**defaults, **values}
    merged.setdefault(
        "category_counts",
        {category: merged[field] for field, category in COUNT_CATEGORIES.items() if merged.get(field)},
    )
    row = BouncedAddress.objects.create(address=address, **merged)
    if "suggestion" not in values:
        row.suggestion = suggest(row)
        row.save(update_fields=["suggestion"])
    refresh_cached_links([row])
    return row


def request_for(user):
    request = RequestFactory().post("/")
    request.user = user
    return request
