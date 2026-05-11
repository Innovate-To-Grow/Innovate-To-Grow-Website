"""Asset manager responses for the CMS page editor."""

import os

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse

import cms.admin.cms.page_admin.editor as editor_api
from cms.models import CMSAsset
from cms.models.media import IMAGE_ASSET_EXTENSIONS


def _asset_extension(asset):
    _, ext = os.path.splitext(asset.file.name if asset.file else "")
    return ext.lstrip(".").lower()


def _requested_asset_type(request):
    asset_type = (request.GET.get("type") or request.POST.get("type") or "").strip().lower()
    return asset_type if asset_type == "image" else ""


def _image_asset_query():
    query = Q(file__iendswith=f".{IMAGE_ASSET_EXTENSIONS[0]}")
    for extension in IMAGE_ASSET_EXTENSIONS[1:]:
        query |= Q(file__iendswith=f".{extension}")
    return query


def _filter_assets_for_type(queryset, asset_type):
    if asset_type == "image":
        return queryset.filter(_image_asset_query())
    return queryset


def _asset_matches_type(asset, asset_type):
    if asset_type == "image":
        return _asset_extension(asset) in IMAGE_ASSET_EXTENSIONS
    return True


def _validation_error_payload(detail: str, errors: dict | list):
    return {"detail": detail, "errors": errors}


def serialize_asset(asset):
    extension = _asset_extension(asset)
    try:
        size = asset.file.size if asset.file else None
    except (OSError, ValueError):
        size = None
    return {
        "id": str(asset.pk),
        "name": asset.name,
        "file": asset.file.name if asset.file else "",
        "public_url": asset.public_url,
        "url": asset.public_url,
        "extension": extension,
        "is_image": extension in IMAGE_ASSET_EXTENSIONS,
        "size": size,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else "",
    }


def assets_list_response(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    query = request.GET.get("q", "").strip()
    asset_type = _requested_asset_type(request)
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 100))

    queryset = CMSAsset.objects.all().order_by("-updated_at", "name")
    queryset = _filter_assets_for_type(queryset, asset_type)
    if query:
        queryset = queryset.filter(name__icontains=query)

    total = queryset.count()
    assets = [serialize_asset(asset) for asset in queryset[:limit]]
    return JsonResponse({"assets": assets, "total": total})


def assets_upload_response(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    asset_type = _requested_asset_type(request)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"detail": "Select a file to upload."}, status=400)

    default_name = os.path.splitext(uploaded.name or "")[0] or uploaded.name or "CMS Asset"
    name = (request.POST.get("name") or default_name).strip()[:200] or "CMS Asset"
    asset = CMSAsset(name=name, file=uploaded)
    try:
        asset.full_clean()
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            errors = exc.message_dict
            msgs = [m for field_errors in errors.values() for m in field_errors]
        else:
            msgs = getattr(exc, "messages", None) or [str(exc)]
            errors = msgs
        detail = msgs[0] if msgs else "Validation error."
        editor_api.logger.info("Asset upload failed validation: %s", detail)
        return JsonResponse(_validation_error_payload(detail, errors), status=400)
    except Exception:
        editor_api.logger.exception("Unexpected error during asset validation")
        return JsonResponse({"detail": "An unexpected error occurred."}, status=500)
    if not _asset_matches_type(asset, asset_type):
        return JsonResponse({"detail": "Select an image asset for this field."}, status=400)

    try:
        asset.save()
    except Exception:
        editor_api.logger.exception("Unexpected error saving asset")
        return JsonResponse({"detail": "An unexpected error occurred."}, status=500)
    return JsonResponse({"asset": serialize_asset(asset)}, status=201)
