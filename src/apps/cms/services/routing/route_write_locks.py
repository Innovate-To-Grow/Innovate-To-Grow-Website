"""Cross-table serialization for CMS page and route-redirect writes.

Every supported mapping/page mutation follows the same order:

1. stable advisory locks for every involved route (PostgreSQL),
2. CMS page rows,
3. RouteRedirect rows ordered by source path and primary key.

The advisory locks cover routes that do not yet have a database row and close
the create-vs-update gap that row locks alone cannot represent.  SQLite keeps
the same transaction/revalidation flow but has no cross-connection row locks.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q


@dataclass(frozen=True)
class CMSPageWriteSnapshot:
    persisted_route: str | None
    locked_routes: tuple[str, ...]
    redirect_ids: tuple[object, ...]


def ordered_route_lock_names(routes: Iterable[str | None]) -> tuple[str, ...]:
    """Return the one deterministic route-lock order used by every writer."""

    return tuple(sorted({str(route) for route in routes if route}))


def _route_advisory_lock_id(route: str) -> int:
    digest = hashlib.blake2b(f"cms-route-write:{route}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


def _acquire_route_advisory_locks(routes: Iterable[str | None]) -> tuple[str, ...]:
    ordered_routes = ordered_route_lock_names(routes)
    if connection.vendor != "postgresql":
        return ordered_routes

    with connection.cursor() as cursor:
        for route in ordered_routes:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_route_advisory_lock_id(route)])
    return ordered_routes


def _lock_destination_pages(destination_paths: Iterable[str]) -> tuple[object, ...]:
    from apps.cms.models import CMSPage

    paths = ordered_route_lock_names(destination_paths)
    if not paths:
        return ()
    return tuple(
        CMSPage.objects.select_for_update().filter(route__in=paths).order_by("route", "pk").values_list("pk", flat=True)
    )


def _lock_cms_page_instance(page):
    """Lock and return a persisted page instance in the shared row order."""

    if not page.pk or page._state.adding:
        return None
    return type(page).objects.select_for_update().filter(pk=page.pk).only("pk", "route").order_by("route", "pk").first()


def _related_redirect_query(*, source_paths: Iterable[str], destination_paths: Iterable[str]):
    source_paths = ordered_route_lock_names(source_paths)
    destination_paths = ordered_route_lock_names(destination_paths)
    query = Q()
    if source_paths:
        query |= Q(source_path__in=source_paths)
    if destination_paths:
        query |= Q(destination_path__in=destination_paths)
    return query


def _lock_related_redirects(
    *,
    source_paths: Iterable[str] = (),
    destination_paths: Iterable[str] = (),
    redirect_ids: Iterable[object] = (),
) -> tuple[object, ...]:
    from apps.cms.models import RouteRedirect

    query = _related_redirect_query(source_paths=source_paths, destination_paths=destination_paths)
    redirect_ids = tuple(redirect_ids)
    if redirect_ids:
        query |= Q(pk__in=redirect_ids)
    if not query:
        return ()
    return tuple(
        RouteRedirect.objects.select_for_update()
        .filter(query)
        .order_by("source_path", "pk")
        .values_list("pk", flat=True)
    )


def _related_redirect_route_values(routes: Iterable[str]) -> list[tuple[object, str, str]]:
    from apps.cms.models import RouteRedirect

    route_names = ordered_route_lock_names(routes)
    if not route_names:
        return []
    query = _related_redirect_query(source_paths=route_names, destination_paths=route_names)
    return list(
        RouteRedirect.objects.filter(query)
        .order_by("source_path", "pk")
        .values_list("pk", "source_path", "destination_path")
    )


@contextmanager
def lock_route_redirect_write(redirect) -> Iterator[None]:
    """Lock a RouteRedirect candidate's page and graph neighborhood."""

    source_path = redirect.source_path
    destination_path = redirect.destination_path
    redirect_ids = () if redirect._state.adding else (redirect.pk,)

    with transaction.atomic():
        _acquire_route_advisory_locks((source_path, destination_path))
        _lock_destination_pages((destination_path,))
        _lock_related_redirects(
            source_paths=(source_path, destination_path),
            destination_paths=(source_path,),
            redirect_ids=redirect_ids,
        )
        yield


@contextmanager
def lock_cms_page_write(page, *, candidate_route: str | None = None) -> Iterator[CMSPageWriteSnapshot]:
    """Lock a CMS page plus redirects that own or target its old/new route."""

    with transaction.atomic():
        initial_persisted_route = None
        if page.pk and not page._state.adding:
            initial_persisted_route = type(page).objects.filter(pk=page.pk).values_list("route", flat=True).first()

        page_routes = ordered_route_lock_names((initial_persisted_route, candidate_route or page.route))
        initial_redirects = _related_redirect_route_values(page_routes)
        related_route_names = {
            route
            for _pk, source_path, destination_path in initial_redirects
            for route in (source_path, destination_path)
        }
        locked_routes = _acquire_route_advisory_locks((*page_routes, *related_route_names))

        current_redirects = _related_redirect_route_values(page_routes)
        current_route_names = {
            route
            for _pk, source_path, destination_path in current_redirects
            for route in (source_path, destination_path)
        }
        if not current_route_names.issubset(set(locked_routes)):
            raise ValidationError("Route mappings changed concurrently; reload the page and retry.")

        locked_page = _lock_cms_page_instance(page)
        if page.pk and not page._state.adding:
            locked_route = locked_page.route if locked_page else None
            if locked_route != initial_persisted_route:
                raise ValidationError("CMS page route changed concurrently; reload the page and retry.")
            if locked_page is None:
                raise ValidationError("CMS page was deleted concurrently; reload the page and retry.")

        redirect_ids = _lock_related_redirects(
            source_paths=page_routes,
            destination_paths=page_routes,
        )
        yield CMSPageWriteSnapshot(
            persisted_route=locked_page.route if locked_page else None,
            locked_routes=locked_routes,
            redirect_ids=redirect_ids,
        )
