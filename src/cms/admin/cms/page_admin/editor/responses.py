"""Miscellaneous editor JSON responses."""

import json
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone

from cms.models import CMSPage
from cms.models.content.cms.cms_page import normalize_cms_route, validate_cms_route


def preview_store_response(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)
    token = uuid.uuid4().hex
    data["expires_at"] = (timezone.now() + timedelta(seconds=600)).isoformat()
    cache.set(f"cms:preview:{token}", data, timeout=600)
    return JsonResponse({"token": token})


def route_conflict_response(request):
    route = request.GET.get("route", "")
    page_id = request.GET.get("page_id")
    normalized_route = normalize_cms_route(route)
    try:
        normalized_route = validate_cms_route(normalized_route)
    except ValidationError as exc:
        return JsonResponse(
            {
                "normalized_route": normalized_route,
                "has_conflict": False,
                "is_valid": False,
                "message": exc.messages[0],
            }
        )

    conflict_qs = CMSPage.objects.filter(route=normalized_route)
    if page_id:
        conflict_qs = conflict_qs.exclude(pk=page_id)
    conflict = conflict_qs.values("title", "status").first()
    return JsonResponse(
        {
            "normalized_route": normalized_route,
            "has_conflict": bool(conflict),
            "is_valid": True,
            "message": f'Already used by "{conflict["title"]}" ({conflict["status"]}).' if conflict else "",
        }
    )
