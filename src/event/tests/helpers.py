import datetime

from authn.models import ContactEmail, Member
from event.models import Event, Ticket


def make_member(email="test@example.com", **kwargs):
    # Accept and discard legacy 'username' kwarg for backward compatibility
    kwargs.pop("username", None)
    member = Member.objects.create_user(password="testpass123", **kwargs)
    ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
    return member


def make_event(name="Demo Day", date=None, **kwargs):
    defaults = {
        "name": name,
        "date": date or datetime.date(2025, 6, 15),
        "location": "Test Venue",
        "description": "A test event.",
    }
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


def make_ticket(event, name="General Admission", **kwargs):
    return Ticket.objects.create(event=event, name=name, **kwargs)


def make_superuser(email="admin@example.com"):
    user = Member.objects.create_superuser(password="testpass123")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user
