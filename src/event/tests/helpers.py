import datetime

from authn.models import ContactEmail, Member
from event.models import Event, EventRegistration, Ticket


def make_member(email="test@example.com", **kwargs):
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


def make_registration(member, event, ticket, **kwargs):
    return EventRegistration.objects.create(member=member, event=event, ticket=ticket, **kwargs)


def make_superuser(email="admin@example.com"):
    user = Member.objects.create_superuser(password="testpass123")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


def sample_tracks_records():
    return [
        {"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"},
        {"Track": 2, "Room": "Cypress", "Class": "CEE", "Topic": "Environment"},
        {"Track": 3, "Room": "COB 105", "Class": "CSE", "Topic": "Tim Berners-Lee"},
    ]


def sample_projects_records():
    return [
        {
            "Track": 1,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CAP",
            "Team#": "CAP-101",
            "Team Name": "Alpha",
            "Project Title": "Smart Farm",
            "Organization": "Agri Corp",
            "Industry": "Ag",
            "Abstract": "A smart farming project.",
            "Student Names": "Ada, Ben",
            "Name Title": "Mentor - Lead",
        },
        {
            "Track": 1,
            "Order": 2,
            "Year-Semester": "2025-1 Spring",
            "Class": "CAP",
            "Project Title": "Break",
        },
        {
            "Track": 3,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CSE",
            "Team#": "CSE-201",
            "Team Name": "Delta",
            "Project Title": "Campus Navigator",
            "Organization": "UC Merced",
            "Industry": "Education",
            "Abstract": "A route finder for students.",
            "Student Names": "Carol, Dan",
            "Name Title": "Faculty - Sponsor",
        },
        {
            "Track": 2,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CEE",
            "Team#": "CEE-999",
            "Team Name": "River Works",
            "Project Title": "Flood Mapper",
            "Organization": "County Office",
            "Industry": "Government",
        },
    ]
