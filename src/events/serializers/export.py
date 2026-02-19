"""
Export serializers for Google Sheet sync pull endpoint.
"""

from datetime import UTC

from django.utils import timezone
from rest_framework import serializers

WORKSHEET_KEYS = (
    "event_basic",
    "event_bullets",
    "event_expo",
    "event_reception",
    "event_schedule",
    "event_track_winners",
    "event_special_awards",
)


def _to_utc_iso(value):
    """Convert datetime to ISO-8601 UTC string."""
    if value is None:
        return ""

    if timezone.is_naive(value):
        value = timezone.make_aware(value, UTC)

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _event_date_str(event):
    """Get event date string with compatibility fallback."""
    event_date = getattr(event, "event_date", None)
    if event_date is not None:
        if hasattr(event_date, "isoformat"):
            return event_date.isoformat()
        return str(event_date)

    if event.event_date_time:
        return event.event_date_time.date().isoformat()
    return ""


def _event_time_str(event):
    """Get event time string with compatibility fallback."""
    event_time = getattr(event, "event_time", None)
    if event_time is not None:
        if hasattr(event_time, "isoformat"):
            return event_time.isoformat()
        return str(event_time)

    if event.event_date_time:
        return event.event_date_time.time().replace(tzinfo=None).isoformat()
    return ""


def _empty_worksheets():
    """Return empty worksheet payload shape."""
    return {key: [] for key in WORKSHEET_KEYS}


class EventSheetExportSerializer(serializers.Serializer):
    """
    Build sheet-friendly export payload for one live event.

    Context required:
    - mode: full|delta
    - delta_changed: bool
    - generated_at: datetime
    - watermark: datetime
    """

    def to_representation(self, event):
        mode = self.context["mode"]
        delta_changed = self.context["delta_changed"]
        generated_at = self.context["generated_at"]
        watermark = self.context["watermark"]

        if not delta_changed:
            worksheets = _empty_worksheets()
        else:
            worksheets = self._build_worksheets(event)

        return {
            "meta": {
                "source": "i2g-db",
                "scope": "live_event",
                "mode": mode,
                "delta_changed": delta_changed,
                "generated_at": _to_utc_iso(generated_at),
                "watermark": _to_utc_iso(watermark),
                "event": {
                    "event_uuid": str(event.event_uuid),
                    "slug": event.slug,
                    "event_name": event.event_name,
                },
            },
            "worksheets": worksheets,
        }

    def _build_worksheets(self, event):
        worksheets = _empty_worksheets()

        worksheets["event_basic"] = [
            {
                "event_uuid": str(event.event_uuid),
                "event_slug": event.slug,
                "event_name": event.event_name,
                "event_date": _event_date_str(event),
                "event_time": _event_time_str(event),
                "is_published": bool(event.is_published),
                "is_live": bool(event.is_live),
                "updated_at": _to_utc_iso(event.updated_at),
            }
        ]

        event_bullets = []
        for index, content in enumerate(event.upper_bullet_points or [], start=1):
            event_bullets.append(
                {
                    "section": "upper",
                    "position": index,
                    "content_markdown": content,
                }
            )
        for index, content in enumerate(event.lower_bullet_points or [], start=1):
            event_bullets.append(
                {
                    "section": "lower",
                    "position": index,
                    "content_markdown": content,
                }
            )
        worksheets["event_bullets"] = event_bullets

        worksheets["event_expo"] = [
            {
                "position": index,
                "time": row.get("time", ""),
                "room": row.get("room", ""),
                "description": row.get("description", ""),
            }
            for index, row in enumerate(event.expo_table or [], start=1)
        ]

        worksheets["event_reception"] = [
            {
                "position": index,
                "time": row.get("time", ""),
                "room": row.get("room", ""),
                "description": row.get("description", ""),
            }
            for index, row in enumerate(event.reception_table or [], start=1)
        ]

        schedule_rows = []
        programs = event.programs.all().order_by("order", "id")
        for program in programs:
            tracks = program.tracks.all().order_by("order", "id")
            for track in tracks:
                presentations = track.presentations.all().order_by("order", "id")
                for presentation in presentations:
                    project_title = presentation.project_title or ""
                    organization = presentation.organization or ""
                    is_break = "break" in project_title.lower() or organization.lower() == "break"

                    schedule_rows.append(
                        {
                            "program_name": program.program_name,
                            "program_order": program.order,
                            "track_name": track.track_name,
                            "track_order": track.order,
                            "track_room": track.room,
                            "track_start_time": track.start_time.isoformat() if track.start_time else "",
                            "presentation_order": presentation.order,
                            "team_id": presentation.team_id or "",
                            "team_name": presentation.team_name or "",
                            "project_title": project_title,
                            "organization": organization,
                            "abstract": presentation.abstract or "",
                            "is_break": is_break,
                        }
                    )
        worksheets["event_schedule"] = schedule_rows

        track_winner_rows = []
        for index, winner in enumerate(event.track_winners.all().order_by("created_at", "id"), start=1):
            track_winner_rows.append(
                {
                    "position": index,
                    "track_name": winner.track_name,
                    "winner_name": winner.winner_name,
                }
            )
        worksheets["event_track_winners"] = track_winner_rows

        special_award_rows = []
        for index, award in enumerate(event.special_award_winners.all().order_by("created_at", "id"), start=1):
            special_award_rows.append(
                {
                    "position": index,
                    "program_name": award.program_name,
                    "award_winner": award.award_winner,
                }
            )
        worksheets["event_special_awards"] = special_award_rows

        return worksheets
