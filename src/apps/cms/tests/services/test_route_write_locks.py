"""Deterministic lock-protocol tests for CMS route writers."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase

from apps.cms.models import CMSPage
from apps.cms.services.routing import route_write_locks


class RouteLockNameTests(SimpleTestCase):
    def test_route_lock_names_are_unique_and_deterministically_sorted(self):
        self.assertEqual(
            route_write_locks.ordered_route_lock_names(("/z", None, "/a", "/z", "")),
            ("/a", "/z"),
        )

    def test_advisory_lock_ids_are_stable_and_route_specific(self):
        first = route_write_locks._route_advisory_lock_id("/same")
        self.assertEqual(first, route_write_locks._route_advisory_lock_id("/same"))
        self.assertNotEqual(first, route_write_locks._route_advisory_lock_id("/different"))

    def test_redirect_write_locks_routes_then_page_then_redirect_rows(self):
        events = []
        redirect = SimpleNamespace(
            source_path="/source",
            destination_path="/destination",
            pk=uuid4(),
            _state=SimpleNamespace(adding=False),
        )

        def acquire_routes(routes):
            ordered = route_write_locks.ordered_route_lock_names(routes)
            events.append(("routes", ordered))
            return ordered

        def lock_pages(paths):
            events.append(("pages", tuple(paths)))
            return ()

        def lock_redirects(**kwargs):
            events.append(("redirects", kwargs))
            return ()

        with (
            patch.object(route_write_locks.transaction, "atomic", return_value=nullcontext()),
            patch.object(route_write_locks, "_acquire_route_advisory_locks", side_effect=acquire_routes),
            patch.object(route_write_locks, "_lock_destination_pages", side_effect=lock_pages),
            patch.object(route_write_locks, "_lock_related_redirects", side_effect=lock_redirects),
        ):
            with route_write_locks.lock_route_redirect_write(redirect):
                events.append(("body", None))

        self.assertEqual([name for name, _value in events], ["routes", "pages", "redirects", "body"])
        self.assertEqual(events[0][1], ("/destination", "/source"))
        self.assertEqual(events[1][1], ("/destination",))


class CMSPageWriteLockOrderTests(TestCase):
    def test_page_write_locks_routes_then_page_then_redirect_rows(self):
        page = CMSPage.objects.create(
            slug="lock-order",
            route="/lock-order",
            title="Lock Order",
            status="published",
        )
        redirect_id = uuid4()
        events = []

        def discover(routes):
            events.append(("discover", route_write_locks.ordered_route_lock_names(routes)))
            return [(redirect_id, "/legacy-lock-order", page.route)]

        def acquire_routes(routes):
            ordered = route_write_locks.ordered_route_lock_names(routes)
            events.append(("routes", ordered))
            return ordered

        def lock_page(candidate):
            events.append(("page", candidate.pk))
            return SimpleNamespace(route=page.route)

        def lock_redirects(**kwargs):
            events.append(("redirects", kwargs))
            return (redirect_id,)

        with (
            patch.object(route_write_locks, "_related_redirect_route_values", side_effect=discover),
            patch.object(route_write_locks, "_acquire_route_advisory_locks", side_effect=acquire_routes),
            patch.object(route_write_locks, "_lock_cms_page_instance", side_effect=lock_page),
            patch.object(route_write_locks, "_lock_related_redirects", side_effect=lock_redirects),
        ):
            with route_write_locks.lock_cms_page_write(page, candidate_route=page.route) as snapshot:
                events.append(("body", snapshot))

        self.assertEqual(
            [name for name, _value in events],
            ["discover", "routes", "discover", "page", "redirects", "body"],
        )
        self.assertEqual(events[1][1], ("/legacy-lock-order", "/lock-order"))
        self.assertEqual(snapshot.persisted_route, page.route)
        self.assertEqual(snapshot.redirect_ids, (redirect_id,))
