"""
Views for Event Management System.

Includes sync endpoint (POST) for Google Sheets and read endpoint (GET) for frontend.
"""

import re
from datetime import datetime
from django.db import transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from ..models import Event, Program, Track, Presentation, TrackWinner
from ..serializers import EventSyncSerializer, EventReadSerializer
from ..authentication import APIKeyAuthentication, APIKeyPermission


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
            "slug": "fall-2025-expo",  # Required
            "is_live": true,           # Optional, defaults to False
            "basic_info": {...},       # Optional
            "schedule": [...],         # Optional
            "winners": {...}           # Optional
        }
        """
        serializer = EventSyncSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data
        slug = validated_data.get('slug')
        is_live = validated_data.get('is_live', False)

        # Perform atomic transaction
        try:
            with transaction.atomic():
                # Live Switch Logic: If is_live is True, clear other live events first
                if is_live:
                    Event.objects.filter(is_live=True).update(is_live=False)

                # Atomic Upsert: Use update_or_create based on slug
                if 'basic_info' not in validated_data:
                    return Response(
                        {'error': 'basic_info is required for event creation/update.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                basic_info = validated_data['basic_info']
                event, created = Event.objects.update_or_create(
                    slug=slug,
                    defaults={
                        'event_name': basic_info['event_name'],
                        'event_date': basic_info['event_date'],
                        'event_time': basic_info['event_time'],
                        'upper_bullet_points': basic_info.get('upper_bullet_points', []),
                        'lower_bullet_points': basic_info.get('lower_bullet_points', []),
                        'is_published': True,  # Assume published if synced
                        'is_live': is_live,
                    }
                )

                # Process expo_table if provided
                if 'expo_table' in validated_data:
                    expo_data = validated_data['expo_table']
                    # Extract room from header row (time="Room:")
                    room = None
                    valid_rows = []
                    for row in expo_data:
                        # Check if this is a header row (time="Room:")
                        if row.get('time') == 'Room:':
                            room = row.get('description', '')
                        # Only include rows with both time and description (skip header rows)
                        elif row.get('time') and row.get('time') != 'Room:' and row.get('description'):
                            # Format time if it's a date string
                            time_str = row.get('time', '')
                            # If time is a date string, extract just the time portion with AM/PM
                            if 'GMT' in time_str or ('T' in time_str and len(time_str) > 10):
                                try:
                                    # Try to parse various date formats
                                    time_str_clean = time_str.replace(' GMT', '').split(' (')[0]
                                    date_obj = datetime.fromisoformat(time_str_clean.replace('Z', '+00:00'))
                                    # Format as "H:MM AM/PM" (12-hour format)
                                    hour = date_obj.hour
                                    minute = date_obj.minute
                                    am_pm = 'AM' if hour < 12 else 'PM'
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                                except Exception:
                                    # If parsing fails, try to extract time from string and add AM/PM
                                    time_match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                                    if time_match:
                                        hour = int(time_match.group(1))
                                        minute = int(time_match.group(2))
                                        am_pm = 'AM' if hour < 12 else 'PM'
                                        hour_12 = hour if hour <= 12 else hour - 12
                                        if hour_12 == 0:
                                            hour_12 = 12
                                        time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            # If time doesn't have AM/PM, add it
                            elif time_str and not re.search(r'\s*(AM|PM|am|pm)', time_str):
                                time_match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                                if time_match:
                                    hour = int(time_match.group(1))
                                    minute = int(time_match.group(2))
                                    am_pm = 'AM' if hour < 12 else 'PM'
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            
                            valid_rows.append({
                                'time': time_str,
                                'room': room or row.get('room', ''),
                                'description': row.get('description', '')
                            })
                    event.expo_table = valid_rows
                    event.save()

                # Process reception_table if provided
                if 'reception_table' in validated_data:
                    reception_data = validated_data['reception_table']
                    # Extract room from header row (time="Room:")
                    room = None
                    valid_rows = []
                    for row in reception_data:
                        # Check if this is a header row (time="Room:")
                        if row.get('time') == 'Room:':
                            room = row.get('description', '')
                        # Only include rows with both time and description (skip header rows)
                        elif row.get('time') and row.get('time') != 'Room:' and row.get('description'):
                            # Format time if it's a date string
                            time_str = row.get('time', '')
                            # If time is a date string, extract just the time portion with AM/PM
                            if 'GMT' in time_str or ('T' in time_str and len(time_str) > 10):
                                try:
                                    # Try to parse various date formats
                                    time_str_clean = time_str.replace(' GMT', '').split(' (')[0]
                                    date_obj = datetime.fromisoformat(time_str_clean.replace('Z', '+00:00'))
                                    # Format as "H:MM AM/PM" (12-hour format)
                                    hour = date_obj.hour
                                    minute = date_obj.minute
                                    am_pm = 'AM' if hour < 12 else 'PM'
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                                except Exception:
                                    # If parsing fails, try to extract time from string and add AM/PM
                                    time_match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                                    if time_match:
                                        hour = int(time_match.group(1))
                                        minute = int(time_match.group(2))
                                        am_pm = 'AM' if hour < 12 else 'PM'
                                        hour_12 = hour if hour <= 12 else hour - 12
                                        if hour_12 == 0:
                                            hour_12 = 12
                                        time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            # If time doesn't have AM/PM, add it
                            elif time_str and not re.search(r'\s*(AM|PM|am|pm)', time_str):
                                time_match = re.search(r'(\d{1,2}):(\d{2})', time_str)
                                if time_match:
                                    hour = int(time_match.group(1))
                                    minute = int(time_match.group(2))
                                    am_pm = 'AM' if hour < 12 else 'PM'
                                    hour_12 = hour if hour <= 12 else hour - 12
                                    if hour_12 == 0:
                                        hour_12 = 12
                                    time_str = f"{hour_12}:{minute:02d} {am_pm}"
                            
                            valid_rows.append({
                                'time': time_str,
                                'room': room or row.get('room', ''),
                                'description': row.get('description', '')
                            })
                    event.reception_table = valid_rows
                    event.save()

                # Process schedule (full replace with deep clean)
                if 'schedule' in validated_data:
                    # Deep Clean Sync: Delete all existing related objects for this event
                    event.programs.all().delete()  # Cascades to tracks and presentations

                    # Create new schedule hierarchy
                    for program_data in validated_data['schedule']:
                        program = Program.objects.create(
                            event=event,
                            program_name=program_data['program_name'],
                            order=0,  # Could be enhanced to include order from payload
                        )

                        for track_data in program_data['tracks']:
                            track = Track.objects.create(
                                program=program,
                                track_name=track_data['track_name'],
                                room=track_data['room'],
                                start_time=track_data.get('start_time'),
                                order=0,  # Could be enhanced to include order from payload
                            )

                            for presentation_data in track_data['presentations']:
                                # Handle Break entries - allow null/empty team fields
                                team_id = presentation_data.get('team_id', '') or None
                                team_name = presentation_data.get('team_name', '') or None
                                organization = presentation_data.get('organization', '') or None
                                abstract = presentation_data.get('abstract', '') or None
                                
                                Presentation.objects.create(
                                    track=track,
                                    order=presentation_data['order'],
                                    team_id=team_id if team_id else None,
                                    team_name=team_name if team_name else None,
                                    project_title=presentation_data['project_title'],
                                    organization=organization if organization else None,
                                    abstract=abstract if abstract else None,
                                )

                # Process winners (full replace with deep clean)
                if 'winners' in validated_data:
                    winners_data = validated_data['winners']

                    # Deep Clean Sync: Delete all existing track winners for this event
                    event.track_winners.all().delete()

                    # Create track winners
                    if 'track_winners' in winners_data:
                        for winner_data in winners_data['track_winners']:
                            TrackWinner.objects.create(
                                event=event,
                                track_name=winner_data['track_name'],
                                winner_name=winner_data['winner_name'],
                            )

                    # Update special awards (simple string array)
                    if 'special_awards' in winners_data:
                        event.special_awards = winners_data['special_awards']
                        event.save()

                # Return success response
                return Response(
                    {
                        'status': 'success',
                        'message': 'Event data synced successfully.',
                        'event_uuid': str(event.event_uuid),
                        'slug': event.slug,
                        'is_live': event.is_live,
                    },
                    status=status.HTTP_200_OK
                )

        except Exception as e:
            # Transaction will rollback automatically
            return Response(
                {'error': f'Failed to sync event data: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EventRetrieveAPIView(APIView):
    """
    GET endpoint for retrieving the live event data for frontend.

    Returns the single event where is_live=True, or 404 with friendly message.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Retrieve the live event."""
        event = Event.objects.filter(is_live=True).first()

        if not event:
            return Response(
                {'detail': 'No active event scheduled'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventReadSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)


class EventArchiveRetrieveAPIView(APIView):
    """
    GET endpoint for retrieving archived event data by slug.

    Returns a specific event by slug, or 404 if not found.
    """

    permission_classes = [AllowAny]

    def get(self, request, slug):
        """Retrieve event by slug."""
        try:
            event = Event.objects.get(slug=slug)
        except Event.DoesNotExist:
            return Response(
                {'detail': 'Event not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventReadSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PastEventsListAPIView(APIView):
    """
    GET endpoint for retrieving list of past events.

    Returns a list of all events where is_live=False, ordered by event_date (most recent first).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Retrieve list of past events."""
        past_events = Event.objects.filter(is_live=False).order_by('-event_date')
        
        events_list = [
            {
                'slug': event.slug,
                'event_name': event.event_name,
                'event_date': event.event_date.isoformat(),
            }
            for event in past_events
        ]

        return Response(events_list, status=status.HTTP_200_OK)

