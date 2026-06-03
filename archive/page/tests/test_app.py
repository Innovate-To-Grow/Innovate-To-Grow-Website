"""App-level wiring tests: blueprints, context processor, removed features."""

import pytest


def test_only_home_blueprint_is_registered(app):
    assert set(app.blueprints) == {"home"}


def test_inject_event_returns_none(app):
    # The events/DB feature is gone; templates still reference `event`, so the
    # context processor must expose it as None rather than querying a database.
    from project import inject_event

    with app.app_context():
        assert inject_event() == {"event": None}


@pytest.mark.parametrize(
    "path",
    [
        "/events",
        "/membership/events",
        "/membership/event-registration/x/y",
        "/membership/otp",
        "/geo",
        "/admin",
        "/tracking_pixel/test.png",
    ],
)
def test_removed_feature_routes_are_gone(client, path):
    # Removed features should 404 (route no longer registered), never 500.
    assert client.get(path).status_code == 404


def test_404_handler_renders_template(client):
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert resp.data  # custom 404.html rendered (extends membership/layout.html)


def test_homepage_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.data
