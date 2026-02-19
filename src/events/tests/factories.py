"""
Shared test factories and helpers for events tests.
"""

from datetime import UTC, time

from django.utils import timezone

from ..models import Event, Presentation, Program, SpecialAward, Track, TrackWinner


def iso_utc(value):
    """Convert a datetime to an ISO 8601 UTC string with Z suffix."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def create_live_event():
    """Create a fully populated live event with programs, tracks, presentations, and awards."""
    event = Event.objects.create(
        event_name="Fall 2026 I2G Event",
        event_date_time=timezone.now(),
        slug="fall-2026-i2g-event",
        is_published=True,
        is_live=True,
        upper_bullet_points=["Upper 1", "Upper 2"],
        lower_bullet_points=["Lower 1"],
        expo_table=[
            {"time": "Room:", "room": "", "description": "Conference Center"},
            {"time": "9:00 AM", "room": "Conference Center", "description": "Registration"},
        ],
        reception_table=[
            {"time": "Room:", "room": "", "description": "Conference Center"},
            {"time": "5:00 PM", "room": "Conference Center", "description": "Reception"},
        ],
    )

    program_b = Program.objects.create(event=event, program_name="Program B", order=2)
    program_a = Program.objects.create(event=event, program_name="Program A", order=1)

    track_a2 = Track.objects.create(
        program=program_a,
        track_name="Track A2",
        room="GLCR 160",
        start_time=time(13, 0),
        order=2,
    )
    track_a1 = Track.objects.create(
        program=program_a,
        track_name="Track A1",
        room="GLCR 155",
        start_time=time(13, 0),
        order=1,
    )

    Presentation.objects.create(
        track=track_a1,
        order=2,
        team_id=None,
        team_name=None,
        project_title="Break",
        organization="Break",
        abstract="",
    )
    Presentation.objects.create(
        track=track_a1,
        order=1,
        team_id="A-101",
        team_name="Team A101",
        project_title="Project Alpha",
        organization="Org Alpha",
        abstract="Alpha abstract",
    )
    Presentation.objects.create(
        track=track_a2,
        order=1,
        team_id="A-201",
        team_name="Team A201",
        project_title="Project Beta",
        organization="Org Beta",
        abstract="Beta abstract",
    )

    track_b1 = Track.objects.create(
        program=program_b,
        track_name="Track B1",
        room="GLCR 150",
        start_time=time(13, 30),
        order=1,
    )
    Presentation.objects.create(
        track=track_b1,
        order=1,
        team_id="B-101",
        team_name="Team B101",
        project_title="Project Gamma",
        organization="Org Gamma",
        abstract=None,
    )

    TrackWinner.objects.create(event=event, track_name="Track A1", winner_name="Team A101")
    SpecialAward.objects.create(event=event, program_name="Program A", award_winner="Team A201")

    return event
