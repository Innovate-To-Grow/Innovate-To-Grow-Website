import json

from cms.app_routes import APP_ROUTES
from cms.models import CMSPage


def build_route_editor_context():
    """Return route-editor JSON with app routes taking precedence over CMS routes."""
    app_routes = list(APP_ROUTES)
    app_route_urls = {route["url"] for route in app_routes}
    cms_pages = list(CMSPage.objects.filter(status="published").order_by("title").values("route", "title"))
    cms_routes = [{"url": page["route"], "title": page["title"]} for page in cms_pages if page["route"] not in app_route_urls]
    return {
        "app_routes_json": json.dumps(app_routes),
        "cms_routes_json": json.dumps(cms_routes),
    }
