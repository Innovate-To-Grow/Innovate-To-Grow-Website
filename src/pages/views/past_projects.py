"""
API views for Past Projects feature.
"""

import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from ..services.google_sheets import get_google_sheets_service
from ..models.past_projects import SharedProjectURL
from ..serializers.past_projects import (
    PastProjectSerializer,
    SharedProjectURLCreateSerializer,
    SharedProjectURLRetrieveSerializer,
)

logger = logging.getLogger(__name__)


class PastProjectsListAPIView(APIView):
    """
    GET endpoint for retrieving list of past projects from Google Sheets.
    
    Returns a JSON array of project objects with all project details.
    No authentication required (public data).
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Retrieve list of past projects from Google Sheets."""
        try:
            service = get_google_sheets_service()
            projects = service.fetch_past_projects()
            
            # Serialize the projects
            serializer = PastProjectSerializer(projects, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching past projects: {e}")
            return Response(
                {
                    "detail": "Unable to load past projects data. Please try again later.",
                    "error": str(e) if logger.level <= logging.DEBUG else None
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class SharedProjectURLCreateAPIView(APIView):
    """
    POST endpoint for creating a shared project URL.
    
    Accepts team names and team numbers, generates a UUID,
    and stores the data for later retrieval.
    
    CSRF exempt since this is a public API endpoint.
    """

    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        # Explicitly set CSRF exemption flag for DRF
        setattr(request, '_dont_enforce_csrf_checks', True)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        """Create a shared project URL."""
        serializer = SharedProjectURLCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = serializer.validated_data
        
        # #region agent log
        import json
        import os
        log_path = '/Users/avashadhikari/I2G/Innovate-To-Grow-Website/.cursor/debug.log'
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps({
                    'location': 'past_projects.py:84',
                    'message': 'SharedProjectURLCreateAPIView.post: validated_data received',
                    'data': {
                        'team_names_count': len(validated_data.get('team_names', [])),
                        'team_numbers_count': len(validated_data.get('team_numbers', [])),
                        'project_keys_count': len(validated_data.get('project_keys', [])),
                        'team_names': validated_data.get('team_names', [])[:5],
                        'team_numbers': validated_data.get('team_numbers', [])[:5],
                        'project_keys': validated_data.get('project_keys', [])[:3]
                    },
                    'timestamp': int(__import__('time').time() * 1000),
                    'sessionId': 'debug-session',
                    'runId': 'run1',
                    'hypothesisId': 'C'
                }) + '\n')
        except Exception:
            pass
        # #endregion
        
        # Create the shared URL
        shared_url = SharedProjectURL.objects.create(
            team_names=validated_data['team_names'],
            team_numbers=validated_data['team_numbers'],
            project_keys=validated_data.get('project_keys', [])
        )
        
        # #region agent log
        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps({
                    'location': 'past_projects.py:100',
                    'message': 'SharedProjectURLCreateAPIView.post: shared_url created',
                    'data': {
                        'uuid': str(shared_url.uuid),
                        'team_names_count': len(shared_url.team_names),
                        'team_numbers_count': len(shared_url.team_numbers),
                        'project_keys_count': len(shared_url.project_keys)
                    },
                    'timestamp': int(__import__('time').time() * 1000),
                    'sessionId': 'debug-session',
                    'runId': 'run1',
                    'hypothesisId': 'C'
                }) + '\n')
        except Exception:
            pass
        # #endregion
        
        # Return the UUID and full URL
        # Use frontend URL from Referer header, or fall back to setting/env var
        referer = request.META.get('HTTP_REFERER', '')
        
        # Extract frontend URL from referer (e.g., http://localhost:5173)
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            frontend_base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            # Fall back to environment variable or default
            from django.conf import settings
            frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
        
        full_url = f"{frontend_base}/past-projects/shared/{shared_url.uuid}"
        
        return Response(
            {
                "uuid": str(shared_url.uuid),
                "url": full_url
            },
            status=status.HTTP_201_CREATED
        )


class SharedProjectURLRetrieveAPIView(APIView):
    """
    GET endpoint for retrieving a shared project URL by UUID.
    
    Returns the team names and team numbers associated with the UUID.
    """

    permission_classes = [AllowAny]

    def get(self, request, uuid):
        """Retrieve shared URL data by UUID."""
        try:
            shared_url = SharedProjectURL.objects.get(uuid=uuid)
            
            # #region agent log
            import json
            import os
            log_path = '/Users/avashadhikari/I2G/Innovate-To-Grow-Website/.cursor/debug.log'
            try:
                with open(log_path, 'a') as f:
                    f.write(json.dumps({
                        'location': 'past_projects.py:128',
                        'message': 'SharedProjectURLRetrieveAPIView.get: shared_url retrieved',
                        'data': {
                            'uuid': str(uuid),
                            'team_names_count': len(shared_url.team_names),
                            'team_numbers_count': len(shared_url.team_numbers),
                            'project_keys_count': len(shared_url.project_keys) if hasattr(shared_url, 'project_keys') else 0,
                            'has_project_keys': hasattr(shared_url, 'project_keys'),
                            'team_names': shared_url.team_names[:5],
                            'team_numbers': shared_url.team_numbers[:5],
                            'project_keys': (shared_url.project_keys[:3] if hasattr(shared_url, 'project_keys') and shared_url.project_keys else [])
                        },
                        'timestamp': int(__import__('time').time() * 1000),
                        'sessionId': 'debug-session',
                        'runId': 'run1',
                        'hypothesisId': 'D'
                    }) + '\n')
            except Exception:
                pass
            # #endregion
            
            # Check if expired
            if shared_url.expires_at and shared_url.expires_at < shared_url.created_at:
                return Response(
                    {"detail": "This shared URL has expired."},
                    status=status.HTTP_410_GONE
                )
            
            serializer = SharedProjectURLRetrieveSerializer(shared_url)
            
            # #region agent log
            try:
                with open(log_path, 'a') as f:
                    f.write(json.dumps({
                        'location': 'past_projects.py:150',
                        'message': 'SharedProjectURLRetrieveAPIView.get: serializer data',
                        'data': {
                            'serialized_data': serializer.data
                        },
                        'timestamp': int(__import__('time').time() * 1000),
                        'sessionId': 'debug-session',
                        'runId': 'run1',
                        'hypothesisId': 'D'
                    }) + '\n')
            except Exception:
                pass
            # #endregion
            
            return Response(serializer.data, status=status.HTTP_200_OK)
            
        except SharedProjectURL.DoesNotExist:
            return Response(
                {"detail": "Shared URL not found. Please check the URL and try again."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrieving shared URL {uuid}: {e}")
            return Response(
                {"detail": "Unable to retrieve shared URL. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

