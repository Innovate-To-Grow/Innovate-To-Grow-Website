"""IP geolocation lookup view for analytics admin."""

import ipaddress

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from apps.core.access import user_can_access_app

IP_GEO_CACHE_PREFIX = "ip_geo:"
IP_GEO_CACHE_TTL = 86400


def ip_geo_lookup_view(request):
    """Look up geolocation for an IP address, cached for 24 hours."""
    import requests as http_requests

    # ``admin_view`` only enforces is_staff, and this is a module-level function
    # (no ModelAdmin ``self``), so re-check per-app access directly: page-view IPs
    # are visitor PII and the lookup hits an external geolocation service.
    if not user_can_access_app(request.user, "cms"):
        raise PermissionDenied("You do not have permission to access page-view analytics.")

    ip = request.GET.get("ip", "").strip()
    if not ip:
        return JsonResponse({"error": "No IP provided"}, status=400)

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return JsonResponse({"error": "Invalid IP address"}, status=400)

    cache_key = f"{IP_GEO_CACHE_PREFIX}{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse(cached)

    try:
        resp = http_requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,message,country,regionName,city,zip,lat,lon,isp,org,as"},
            timeout=5,
        )
        data = resp.json()
    except Exception:
        return JsonResponse({"error": "Geolocation service unavailable"}, status=502)

    if data.get("status") == "fail":
        result = {"error": data.get("message", "Lookup failed"), "ip": ip}
    else:
        result = {
            "ip": ip,
            "country": data.get("country", ""),
            "region": data.get("regionName", ""),
            "city": data.get("city", ""),
            "zip": data.get("zip", ""),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "isp": data.get("isp", ""),
            "org": data.get("org", ""),
            "as": data.get("as", ""),
        }
        cache.set(cache_key, result, IP_GEO_CACHE_TTL)

    return JsonResponse(result)
