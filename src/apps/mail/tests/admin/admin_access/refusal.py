"""Shared assertions: a signed-in member who is not an Admin is refused every custom Mail admin URL.

Every custom Mail admin URL is mounted through ``admin_site.admin_view``, which sends a signed-in member who is not
an Admin to the admin login (a 302) before the view runs. Each view also makes its own Admin check, in case it is
ever mounted without ``admin_view``; ``assert_refused_to_member`` exercises both.
"""

from urllib.parse import urlsplit

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.event.tests.helpers import make_admin


def make_member(email="member@example.com", **kwargs):
    """A regular (non-Admin) member with a verified primary email."""
    return make_admin(email=email, is_staff=False, **kwargs)


def assert_refused_to_member(case, url, member, method="get", *, view_check=True, **kwargs):
    """``member`` (not an Admin) is sent to the admin login, and the view's own check refuses it as well."""
    case.client.force_login(member)
    response = getattr(case.client, method)(url, **kwargs)
    case.assertEqual(response.status_code, 302, f"a member should be redirected from {url} ({method})")
    case.assertTrue(response["Location"].startswith(reverse("admin:login")), response["Location"])
    if view_check:
        match = resolve(urlsplit(url).path)
        request = getattr(RequestFactory(), method)(url, **kwargs)
        request.user = member
        with case.assertRaises(PermissionDenied):
            match.func.__wrapped__(request, *match.args, **match.kwargs)
    return response
