"""
Views for Event Management System.

Includes sync endpoint (POST) for Google Sheets and read endpoint (GET) for frontend.
"""

from django.db import transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from ..models import Event, Program, Track, Presentation, TrackWinner, SpecialAward
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
            "basic_info": {...},  # Optional
            "schedule": [...],    # Optional
            "winners": {...}      # Optional
        }
        """
        serializer = EventSyncSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data

        # Perform atomic transaction
        try:
            with transaction.atomic():
                # Get or create a single event (assuming single event system)
                # If multiple events are needed, we'd need to identify by event_name/date
                event = Event.objects.first()

                # If no event exists, create one (will be populated by basic_info if provided)
                if not event:
                    if 'basic_info' not in validated_data:
                        return Response(
                            {'error': 'No event exists and basic_info not provided.'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    basic_info = validated_data['basic_info']
                    event = Event.objects.create(
                        event_name=basic_info['event_name'],
                        event_date=basic_info['event_date'],
                        event_time=basic_info['event_time'],
                        upper_bullet_points=basic_info.get('upper_bullet_points', []),
                        lower_bullet_points=basic_info.get('lower_bullet_points', []),
                        is_published=True,  # Assume published if synced
                    )
                else:
                    # Update basic_info if provided
                    if 'basic_info' in validated_data:
                        basic_info = validated_data['basic_info']
                        event.event_name = basic_info['event_name']
                        event.event_date = basic_info['event_date']
                        event.event_time = basic_info['event_time']
                        event.upper_bullet_points = basic_info.get('upper_bullet_points', [])
                        event.lower_bullet_points = basic_info.get('lower_bullet_points', [])
                        event.is_published = True
                        event.save()

                # Process schedule (full replace)
                if 'schedule' in validated_data:
                    # Delete all existing programs (cascades to tracks and presentations)
                    event.programs.all().delete()

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
                                order=0,  # Could be enhanced to include order from payload
                            )

                            for presentation_data in track_data['presentations']:
                                # Handle Break entries - allow null/empty team fields
                                team_id = presentation_data.get('team_id', '') or None
                                team_name = presentation_data.get('team_name', '') or None
                                organization = presentation_data.get('organization', '') or None
                                
                                Presentation.objects.create(
                                    track=track,
                                    order=presentation_data['order'],
                                    team_id=team_id if team_id else None,
                                    team_name=team_name if team_name else None,
                                    project_title=presentation_data['project_title'],
                                    organization=organization if organization else None,
                                )

                # Process winners (full replace)
                if 'winners' in validated_data:
                    winners_data = validated_data['winners']

                    # Delete all existing winners
                    event.track_winners.all().delete()
                    event.special_awards.all().delete()

                    # Create track winners
                    if 'track_winners' in winners_data:
                        for winner_data in winners_data['track_winners']:
                            TrackWinner.objects.create(
                                event=event,
                                track_name=winner_data['track_name'],
                                winner_name=winner_data['winner_name'],
                            )

                    # Create special awards
                    if 'special_awards' in winners_data:
                        for award_data in winners_data['special_awards']:
                            SpecialAward.objects.create(
                                event=event,
                                program_name=award_data['program_name'],
                                award_winner=award_data['award_winner'],
                            )

                # Return success response
                return Response(
                    {
                        'status': 'success',
                        'message': 'Event data synced successfully.',
                        'event_uuid': str(event.event_uuid),
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
            return Response(
                {'error': 'No event found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = EventReadSerializer(event)
        return Response(serializer.data, status=status.HTTP_200_OK)

