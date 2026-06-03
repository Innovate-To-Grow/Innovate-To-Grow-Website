"""Every static marketing page should render (HTTP 200) with no template errors.

Routes are discovered dynamically from the URL map, so this stays correct as
pages are added or removed. Parameterised (``<...>``) routes and the
Sheets-backed data routes are excluded here and covered in
``test_data_routes.py``.
"""

import pytest

from project import app as flask_app

_DATA_PREFIXES = ("/static", "/api/", "/past-projects")


def _renderable_get_routes():
    paths = set()
    for rule in flask_app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        if rule.arguments:  # skip routes that require URL params
            continue
        path = str(rule)
        if any(path.startswith(prefix) for prefix in _DATA_PREFIXES):
            continue
        paths.add(path)
    return sorted(paths)


RENDERABLE_ROUTES = _renderable_get_routes()


def test_route_discovery_found_many_pages():
    # Guard against the discovery silently matching nothing. Kept as a low
    # floor since the legacy archive is being progressively decommissioned.
    assert len(RENDERABLE_ROUTES) > 5


@pytest.mark.parametrize("path", RENDERABLE_ROUTES)
def test_marketing_page_renders(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} returned {resp.status_code}"
    assert resp.data, f"{path} rendered an empty body"
