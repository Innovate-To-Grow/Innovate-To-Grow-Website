from django.core.exceptions import PermissionDenied
from django.http import FileResponse, JsonResponse

from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import SystemIntelligenceExport

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def export_download_view(request, export_id):
    """Stream a System Intelligence export back as an xlsx attachment.

    Authorizes against ``created_by`` so an admin only sees their own exports
    even if a download URL leaks (the URL space is unguessable but treat it as
    capability + auth, not capability alone). Superusers may download any
    export so the export admin listing is usable for housekeeping.
    """
    # admin_view only enforces is_staff; re-check the per-app model here.
    if not user_can_access_app(request.user, "system_intelligence"):
        raise PermissionDenied("You do not have permission to access System Intelligence.")
    exports = SystemIntelligenceExport.objects.all()
    if not request.user.is_superuser:
        exports = exports.filter(created_by=request.user)
    try:
        export = exports.get(id=export_id)
    except SystemIntelligenceExport.DoesNotExist:
        return JsonResponse({"error": "Export not found"}, status=404)
    if not export.file:
        return JsonResponse({"error": "Export file is missing on storage"}, status=410)
    response = FileResponse(
        export.file.open("rb"),
        as_attachment=True,
        filename=export.filename,
        content_type=XLSX_CONTENT_TYPE,
    )
    return response
