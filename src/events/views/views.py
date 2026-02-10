"""
Views for Event Management System.

Includes sync endpoint (POST) for Google Sheets and read endpoint (GET) for frontend.
"""

import re
from datetime import UTC, datetime

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import APIKeyAuthentication, APIKeyPermission
from ..models import Event, Presentation, Program, SpecialAward, Track, TrackWinner
from ..serializers import EventReadSerializer, EventSheetExportSerializer, EventSyncSerializer


def _parse_iso8601_datetime(value):
    """Parse ISO-8601 datetime and normalize to UTC."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    parsed = datetime.fromisoformat(normalized)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, UTC)

    return parsed.astimezone(UTC)


class EventSyncAPIView(APIView):
    """
    POST endpoint for syncing event data from Google Sheets.

    Requires X-API-Key header for authentication.
    Performs atomic transaction: deletes existing event data and recreates from payload.
    Conditionally processes basic_info, schedule, and winners based on payload keys.
    """

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]
    serializer_class = EventSyncSerializer

    def post(self, request):
        """
        Process sync payload and update event data atomically.

        Expected JSON structure:
        {
            "basic_info": {...},  # Optional
            "schedule": [...],    # Optional
            "winners": {...}      # Optional
        }
        """
        serializer = EventSyncSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data

        # Perform atomic transaction
        try:
            with transaction.atomic():
                # Get or create a single event (assuming single event system)
                # If multiple events are needed, we'd need to identify by event_name/date
                event = Event.objects.first()

                # If no event exists, create one (will be populated by basic_info if provided)
                if not event:
                    if "basic_info" not in validated_data:
                        return Response(
                            {"error": "No event exists and basic_info not provided."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    basic_info = validated_data["basic_info"]
                    event = Event.objects.create(
                        event_name=basic_info["event_name"],
                        event_date=basic_info["event_date"],
                        event_time=basic_info["event_time"],
                        upper_bullet_points=basic_info.get("upper_bullet_points", []),
                        lower_bullet_points=basic_info.get("lower_bullet_points", []),
                        is_published=True,  # Assume published if synced
                    )
                else:
                    # Update basic_info if provided
                    if "basic_info" in validated_data:
                        basic_info = validated_data["basic_info"]
                        event.event_name = basic_info["event_name"]
                        event.event_date = basic_info["event_date"]
                        event.event_time = basic_info["event_time"]
                        event.upper_bullet_points = basic_info.get("upper_bullet_points", [])
                        event.lower_bullet_points = basic_info.get("lower_bullet_points", [])
                        event.is_published = True
                        event.save()

                # Process expo_table if provided
                if "expo_table" in validated_data:
                    expo_data = validated_data["expo_table"]
                    # Extract room from header row (time="Room:")
                    room = None
                    valid_rows = []
                    for row in expo_data:
                        # Check if this is a header row (time="Room:")
                        if row.get("time") == "Room:":
                            room = row.get("description", "")
                        # Only include rows with both time and description (skip header rows)
                        elif row.get("time") and row.get("time") != "Room:" and row.get("description"):
                            # Format time if it's a date string
                            time_str = row.get("time", "")
                            # If time is a date string, extract just the time portion with AM/PM
                            if "GMT" in time_str or ("T" in time_str and len(time_str) > 10):
                                try:
                                    # Try to parse various date formats
                                    time_str_clean = time_str.replace(" GMT", "").split(" (")[0]
                                    date_obj = datetime.fromisoformat(time_str_clean.replace("Z", "+00:00"))
                                    # Format as "H:MM AM/PM" (12-hour format)
                                    hour = date_obj.hour
                                    minute = date_obj.minute
                                    am_pm = "AM" if hour < 12 else "PM"
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                                except Exception:
                                    # If parsing fails, try to extract time from string and add AM/PM
                                    time_match = re.search(r"(\d{1,2}):(\d{2})", time_str)
                                    if time_match:
                                        hour = int(time_match.group(1))
                                        minute = int(time_match.group(2))
                                        am_pm = "AM" if hour < 12 else "PM"
                                        hour_12 = hour if hour <= 12 else hour - 12
                                        if hour_12 == 0:
                                            hour_12 = 12
                                        time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            # If time doesn't have AM/PM, add it
                            elif time_str and not re.search(r"\s*(AM|PM|am|pm)", time_str):
                                time_match = re.search(r"(\d{1,2}):(\d{2})", time_str)
                                if time_match:
                                    hour = int(time_match.group(1))
                                    minute = int(time_match.group(2))
                                    am_pm = "AM" if hour < 12 else "PM"
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"

                            valid_rows.append(
                                {
                                    "time": time_str,
                                    "room": room or row.get("room", ""),
                                    "description": row.get("description", ""),
                                }
                            )
                    event.expo_table = valid_rows
                    event.save()

                # Process reception_table if provided
                if "reception_table" in validated_data:
                    reception_data = validated_data["reception_table"]
                    # Extract room from header row (time="Room:")
                    room = None
                    valid_rows = []
                    for row in reception_data:
                        # Check if this is a header row (time="Room:")
                        if row.get("time") == "Room:":
                            room = row.get("description", "")
                        # Only include rows with both time and description (skip header rows)
                        elif row.get("time") and row.get("time") != "Room:" and row.get("description"):
                            # Format time if it's a date string
                            time_str = row.get("time", "")
                            # If time is a date string, extract just the time portion with AM/PM
                            if "GMT" in time_str or ("T" in time_str and len(time_str) > 10):
                                try:
                                    # Try to parse various date formats
                                    time_str_clean = time_str.replace(" GMT", "").split(" (")[0]
                                    date_obj = datetime.fromisoformat(time_str_clean.replace("Z", "+00:00"))
                                    # Format as "H:MM AM/PM" (12-hour format)
                                    hour = date_obj.hour
                                    minute = date_obj.minute
                                    am_pm = "AM" if hour < 12 else "PM"
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                                except Exception:
                                    # If parsing fails, try to extract time from string and add AM/PM
                                    time_match = re.search(r"(\d{1,2}):(\d{2})", time_str)
                                    if time_match:
                                        hour = int(time_match.group(1))
                                        minute = int(time_match.group(2))
                                        am_pm = "AM" if hour < 12 else "PM"
                                        hour_12 = hour if hour <= 12 else hour - 12
                                        if hour_12 == 0:
                                            hour_12 = 12
                                        time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            # If time doesn't have AM/PM, add it
                            elif time_str and not re.search(r"\s*(AM|PM|am|pm)", time_str):
                                time_match = re.search(r"(\d{1,2}):(\d{2})", time_str)
                                if time_match:
                                    hour = int(time_match.group(1))
                                    minute = int(time_match.group(2))
                                    am_pm = "AM" if hour < 12 else "PM"
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"

                            valid_rows.append(
                                {
                                    "time": time_str,
                                    "room": room or row.get("room", ""),
                                    "description": row.get("description", ""),
                                }
                            )
                    event.reception_table = valid_rows
                    event.save()

                # Process schedule (full replace)
                if "schedule" in validated_data:
                    # Delete all existing programs (cascades to tracks and presentations)
                    event.programs.all().delete()

                    # Create new schedule hierarchy
                    for program_data in validated_data["schedule"]:
                        program = Program.objects.create(
                            event=event,
                            program_name=program_data["program_name"],
                            order=0,  # Could be enhanced to include order from payload
                        )

                        for track_data in program_data["tracks"]:
                            track = Track.objects.create(
                                program=program,
                                track_name=track_data["track_name"],
                                room=track_data["room"],
                                start_time=track_data.get("start_time"),
                                order=0,  # Could be enhanced to include order from payload
                            )

                            for presentation_data in track_data["presentations"]:
                                # Handle Break entries - allow null/empty team fields
                                team_id = presentation_data.get("team_id", "") or None
                                team_name = presentation_data.get("team_name", "") or None
                                organization = presentation_data.get("organization", "") or None

                                Presentation.objects.create(
                                    track=track,
                                    order=presentation_data["order"],
                                    team_id=team_id if team_id else None,
                                    team_name=team_name if team_name else None,
                                    project_title=presentation_data["project_title"],
                                    organization=organization if organization else None,
                                )

                # Process winners (full replace)
                if "winners" in validated_data:
                    winners_data = validated_data["winners"]

                    # Delete all existing winners
                    event.track_winners.all().delete()
                    event.special_award_winners.all().delete()

                    # Create track winners
                    if "track_winners" in winners_data:
                        for winner_data in winners_data["track_winners"]:
                            TrackWinner.objects.create(
                                event=event,
                                track_name=winner_data["track_name"],
                                winner_name=winner_data["winner_name"],
                            )

                    # Create special awards
                    if "special_awards" in winners_data:
                        for award_data in winners_data["special_awards"]:
                            SpecialAward.objects.create(
                                event=event,
                                program_name=award_data["program_name"],
                                award_winner=award_data["award_winner"],
                            )

                # Ensure updated_at watermark always advances after a sync payload.
                event.save(update_fields=["updated_at"])

                # Return success response
                return Response(
                    {
                        "status": "success",
                        "message": "Event data synced successfully.",
                        "event_uuid": str(event.event_uuid),
                    },
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            # Transaction will rollback automatically
            return Response(
                {"error": f"Failed to sync event data: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EventRetrieveAPIView(APIView):
    """
    GET endpoint for retrieving event data for frontend.

    Returns the most recent published event, or the most recent event if none are published.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Retrieve the current event."""
        # Try to get published event first
        event = Event.objects.filter(is_published=True).first()

        # If no published event, get the most recent one
        if not event:
            event = Event.objects.first()

        if not event:
            return Response({"error": "No event found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = EventReadSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)


class EventSheetExportAPIView(APIView):
    """
    GET endpoint for exporting live event data in sheet-friendly format.

    Requires X-API-Key authentication.
    Supports:
    - mode=full
    - mode=delta&since=<ISO8601>
    """

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [APIKeyPermission]

    def get(self, request):
        mode = (request.query_params.get("mode") or "full").strip().lower()
        if mode not in {"full", "delta"}:
            return Response(
                {"error": "Invalid mode. Expected 'full' or 'delta'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        since_dt = None
        if mode == "delta":
            since_raw = request.query_params.get("since")
            if not since_raw:
                return Response(
                    {"error": "Missing required 'since' query parameter for delta mode."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                since_dt = _parse_iso8601_datetime(since_raw)
            except ValueError:
                return Response(
                    {"error": "Invalid 'since' value. Expected ISO-8601 datetime."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        event = (
            Event.objects.filter(is_live=True)
            .prefetch_related(
                Prefetch(
                    "programs",
                    queryset=Program.objects.order_by("order", "id").prefetch_related(
                        Prefetch(
                            "tracks",
                            queryset=Track.objects.order_by("order", "id").prefetch_related(
                                Prefetch("presentations", queryset=Presentation.objects.order_by("order", "id"))
                            ),
                        )
                    ),
                ),
                Prefetch("track_winners", queryset=TrackWinner.objects.order_by("created_at", "id")),
                Prefetch("special_award_winners", queryset=SpecialAward.objects.order_by("created_at", "id")),
            )
            .order_by("-updated_at", "-created_at")
            .first()
        )

        if not event:
            return Response({"error": "No live event found."}, status=status.HTTP_404_NOT_FOUND)

        watermark = event.updated_at
        delta_changed = mode == "full" or watermark > since_dt

        serializer = EventSheetExportSerializer(
            event,
            context={
                "mode": mode,
                "delta_changed": delta_changed,
                "generated_at": timezone.now(),
                "watermark": watermark,
            },
        )

        return Response(serializer.data, status=status.HTTP_200_OK)
