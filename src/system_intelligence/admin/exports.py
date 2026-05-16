from django.http import FileResponse, JsonResponse

from system_intelligence.models import SystemIntelligenceExport

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def export_download_view(request, export_id):
    """Stream a System Intelligence export back as an xlsx attachment.

    Authorizes against ``created_by`` so an admin only sees their own exports
    even if a download URL leaks (the URL space is unguessable but treat it as
    capability + auth, not capability alone).
    """
    try:
        export = SystemIntelligenceExport.objects.get(id=export_id, created_by=request.user)
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
