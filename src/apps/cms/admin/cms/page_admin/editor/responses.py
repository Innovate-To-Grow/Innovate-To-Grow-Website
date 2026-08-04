"""Miscellaneous editor JSON responses."""

import json
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone

from apps.cms.services.route_redirects import normalize_and_validate_cms_page_route, page_route_conflicts

# Compatibility hook retained for tests and callers that patch the editor's
# route validator.  The implementation now delegates to the shared domain
# validator used by CMS pages and RouteRedirect.
validate_cms_route = normalize_and_validate_cms_page_route


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
    try:
        route = validate_cms_route(route)
    except ValidationError as exc:
        return JsonResponse(
            {
                "normalized_route": route,
                "has_conflict": False,
                "is_valid": False,
                "message": exc.messages[0],
                "conflicts": [{"code": "invalid", "field": "route", "message": exc.messages[0]}],
            }
        )
    normalized_route, conflicts = page_route_conflicts(route, exclude_page_id=page_id)
    invalid = next((conflict for conflict in conflicts if conflict.code == "invalid"), None)
    return JsonResponse(
        {
            "normalized_route": normalized_route,
            "has_conflict": bool(conflicts) and invalid is None,
            "is_valid": invalid is None,
            "message": conflicts[0].message if conflicts else "",
            "conflicts": [
                {"code": conflict.code, "field": conflict.field, "message": conflict.message} for conflict in conflicts
            ],
        }
    )
