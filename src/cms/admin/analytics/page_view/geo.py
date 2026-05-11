"""IP geolocation lookup view for analytics admin."""

from django.core.cache import cache
from django.http import JsonResponse

IP_GEO_CACHE_PREFIX = "ip_geo:"
IP_GEO_CACHE_TTL = 86400


def ip_geo_lookup_view(request):
    """Look up geolocation for an IP address, cached for 24 hours."""
    import requests as http_requests

    ip = request.GET.get("ip", "").strip()
    if not ip:
        return JsonResponse({"error": "No IP provided"}, status=400)

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
