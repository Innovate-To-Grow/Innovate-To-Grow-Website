"""
Media upload API views.

Provides endpoints for uploading files to the MediaAsset system,
used by the admin code editor for image uploads.
"""

import mimetypes

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..models import MediaAsset


@method_decorator([csrf_exempt, staff_member_required], name="dispatch")
class MediaUploadView(View):
    """
    Handle media file uploads from the admin interface.

    POST /api/pages/upload/
    - Accepts multipart form data with 'file' field
    - Creates MediaAsset record
    - Returns JSON with file URL
    """

    def post(self, request):
        """Handle file upload."""
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            return JsonResponse({"error": "No file provided"}, status=400)

        # Validate file type (images only for now)
        content_type = uploaded_file.content_type or ""
        if not content_type.startswith("image/"):
            # Try to guess from filename
            guessed_type, _ = mimetypes.guess_type(uploaded_file.name)
            if guessed_type and guessed_type.startswith("image/"):
                content_type = guessed_type
            else:
                return JsonResponse({"error": "Only image files are allowed"}, status=400)

        # Create MediaAsset
        asset = MediaAsset.objects.create(
            file=uploaded_file,
            original_name=uploaded_file.name,
            content_type=content_type,
            file_size=uploaded_file.size,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        return JsonResponse(
            {
                "success": True,
                "url": asset.url,
                "uuid": str(asset.uuid),
                "name": asset.original_name,
            }
        )


@method_decorator(staff_member_required, name="dispatch")
class MediaListView(View):
    """
    List all media assets for the media library browser.

    GET /api/pages/media/
    - Returns JSON list of all media assets
    - Supports pagination via ?page=1&limit=20
    """

    def get(self, request):
        """Return list of media assets."""
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 50))
        offset = (page - 1) * limit

        # Filter by type if specified
        content_type_filter = request.GET.get("type", "")

        queryset = MediaAsset.objects.all()
        if content_type_filter:
            queryset = queryset.filter(content_type__startswith=content_type_filter)

        total = queryset.count()
        assets = queryset[offset : offset + limit]

        return JsonResponse(
            {
                "assets": [
                    {
                        "uuid": str(asset.uuid),
                        "url": asset.url,
                        "name": asset.original_name,
                        "type": asset.content_type,
                        "size": asset.file_size,
                        "uploaded_at": asset.uploaded_at.isoformat(),
                        "is_image": asset.is_image,
                    }
                    for asset in assets
                ],
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": offset + limit < total,
            }
        )
