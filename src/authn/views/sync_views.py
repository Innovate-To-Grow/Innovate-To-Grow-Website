"""
API views for Google Sheets sync operations.
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from events.models import Event

from ..services.google_sheets_sync import get_sync_service

logger = logging.getLogger(__name__)


def check_api_key(request) -> bool:
    """
    Check if the request has a valid API key.
    """
    api_key = request.META.get('HTTP_X_API_KEY') or request.query_params.get('api_key')
    expected_key = getattr(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', None) or getattr(settings, 'EVENTS_API_KEY', '')
    
    if not expected_key:
        # If no API key is configured, allow access (for development)
        return True
    
    return api_key == expected_key


class SyncToSheetAPIView(APIView):
    """
    POST endpoint to sync database → Google Sheet.
    
    Query params:
        - tab: 'members', 'prospects', or 'event'
        - event_slug: Required if tab='event'
    """
    
    def post(self, request):
        if not check_api_key(request):
            return Response(
                {'error': 'Invalid or missing API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        tab = request.query_params.get('tab', 'members').lower()
        event_slug = request.query_params.get('event_slug')
        
        try:
            sync_service = get_sync_service()
            
            # Ensure sheet structure exists
            sync_service.ensure_sheet_structure()
            
            if tab == 'members':
                result = sync_service.sync_members_to_sheet()
            elif tab == 'prospects':
                result = sync_service.sync_prospects_to_sheet()
            elif tab == 'event':
                if not event_slug:
                    return Response(
                        {'error': 'event_slug is required when tab=event'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                try:
                    event = Event.objects.get(slug=event_slug)
                except Event.DoesNotExist:
                    return Response(
                        {'error': f'Event with slug {event_slug} not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                result = sync_service.sync_event_to_sheet(event)
            else:
                return Response(
                    {'error': f'Invalid tab: {tab}. Must be members, prospects, or event'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Error in sync to sheet: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SyncFromSheetAPIView(APIView):
    """
    POST endpoint to sync Google Sheet → database.
    
    Query params:
        - tab: 'members', 'prospects', or 'event'
        - event_slug: Required if tab='event'
    """
    
    def post(self, request):
        if not check_api_key(request):
            return Response(
                {'error': 'Invalid or missing API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        tab = request.query_params.get('tab', 'members').lower()
        event_slug = request.query_params.get('event_slug')
        
        try:
            sync_service = get_sync_service()
            
            if tab == 'members':
                result = sync_service.sync_members_from_sheet()
            elif tab == 'prospects':
                result = sync_service.sync_prospects_from_sheet()
            elif tab == 'event':
                if not event_slug:
                    return Response(
                        {'error': 'event_slug is required when tab=event'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                try:
                    event = Event.objects.get(slug=event_slug)
                except Event.DoesNotExist:
                    return Response(
                        {'error': f'Event with slug {event_slug} not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                result = sync_service.sync_event_from_sheet(event)
            else:
                return Response(
                    {'error': f'Invalid tab: {tab}. Must be members, prospects, or event'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as e:
            logger.error(f"Error in sync from sheet: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FullSyncAPIView(APIView):
    """
    POST endpoint for full bidirectional sync.
    Syncs both directions for all tabs.
    """
    
    def post(self, request):
        if not check_api_key(request):
            return Response(
                {'error': 'Invalid or missing API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        try:
            sync_service = get_sync_service()
            
            # Ensure sheet structure
            sync_service.ensure_sheet_structure()
            
            results = {
                'members_to_sheet': sync_service.sync_members_to_sheet(),
                'members_from_sheet': sync_service.sync_members_from_sheet(),
                'prospects_to_sheet': sync_service.sync_prospects_to_sheet(),
                'prospects_from_sheet': sync_service.sync_prospects_from_sheet(),
            }
            
            # Sync all events
            events = Event.objects.all()
            event_results = {}
            for event in events:
                event_results[event.slug] = {
                    'to_sheet': sync_service.sync_event_to_sheet(event),
                    'from_sheet': sync_service.sync_event_from_sheet(event),
                }
            results['events'] = event_results
            
            # Calculate overall success
            all_success = all(
                r['success'] for r in [
                    results['members_to_sheet'],
                    results['members_from_sheet'],
                    results['prospects_to_sheet'],
                    results['prospects_from_sheet'],
                ]
            )
            
            return Response(results, status=status.HTTP_200_OK if all_success else status.HTTP_207_MULTI_STATUS)
        
        except Exception as e:
            logger.error(f"Error in full sync: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
